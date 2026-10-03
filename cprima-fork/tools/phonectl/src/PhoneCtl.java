import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.UiAutomation;
import android.content.ClipData;
import android.graphics.Rect;
import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.os.HandlerThread;
import android.os.IBinder;
import android.view.InputDevice;
import android.view.KeyCharacterMap;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * phonectl: a utility that runs ON the phone, as the shell user, started with app_process. It is not an
 * app. The computer pushes its dex once. Every command answers with ONE JSON object, errors included
 * ({"ok":false,"error":"..."}): the data is JSON because the sidecar of a screenshot is JSON.
 *
 * Two ways to run it:
 *   one command per start:   app_process / PhoneCtl <command> <args...>   (the answer on standard output)
 *   as a server:             app_process / PhoneCtl serve <socket-name>
 *       It listens on a local (abstract) socket and answers JSON lines: a request is
 *       {"args":["tap","100","200"]} (and "inline":true for `shot`), the answer is one JSON line, followed
 *       by the picture's bytes when "png_bytes" says so. The UiAutomation connection is made once and kept,
 *       so a command costs a few milliseconds and not a process start. `quit` ends it.
 *
 * Commands:
 *   clip-set TEXT    put TEXT on the clipboard (a marker before a Copy)
 *   clip-get         read the clipboard: {"items":N,"text":"..."|null}
 *   shot DIR NAME    take DIR/NAME.png and answer with the facts of that moment (the phone's clock, the display,
 *                    the window in front, the windows: the status bar and the navigation bar are found among
 *                    them by their rectangles); the same JSON is left next to the picture as NAME.png.raw.json
 *   focus            the window with the focus (package/activity, or a system window's name) and whether the
 *                    lock screen shows; cached until a window event arrives (and for 1.5 s at most)
 *   env PACKAGE...   what the phone and the apps are: build, settings, default apps, and for each package its
 *                    version and the SHA-256 of its APK, computed here
 *   tree [windows]   the screen as a tree straight from UiAutomation, no wait for the screen to go idle
 *   tap X Y | swipe X1 Y1 X2 Y2 MS | long-press X Y MS | key NAME... | text TEXT    input, injected directly
 *   quit             (server) end
 *
 * Nothing here identifies a person: no serial number, no IMEI, no account. The firmware build id and
 * fingerprint are in their own object, "private".
 */
public class PhoneCtl {

    private static final String PACKAGE = "com.android.shell";
    private static final long IDLE_EXIT_MS = 10 * 60 * 1000L;

    // --- helpers ---------------------------------------------------------------------------------

    /** Run a shell command and return its output (stdout and stderr). The output goes through a pipe:
     *  wm and cmd cannot hand their output to a system service as a file. */
    private static String sh(String command) throws Exception {
        Process process = new ProcessBuilder("/system/bin/sh", "-c", command).redirectErrorStream(true).start();
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (InputStream in = process.getInputStream()) {
            byte[] buffer = new byte[8192];
            int n;
            while ((n = in.read(buffer)) > 0) {
                out.write(buffer, 0, n);
            }
        }
        process.waitFor();
        return out.toString("UTF-8").trim();
    }

    private static long nowNs() {
        Instant now = Instant.now();
        return now.getEpochSecond() * 1_000_000_000L + now.getNano();
    }

    private static String first(String pattern, String text) {
        Matcher m = Pattern.compile(pattern).matcher(text);
        return m.find() ? m.group(1) : null;
    }

    private static JSONObject rect(Rect r) throws Exception {
        return new JSONObject().put("rect", new JSONArray().put(r.left).put(r.top).put(r.right).put(r.bottom));
    }

    private static String quote(String s) {
        return "'" + s.replace("'", "'\\''") + "'";
    }

    // --- UiAutomation, connected once ------------------------------------------------------------

    private static UiAutomation automation;
    private static volatile long windowEvents = 0;  // counts window events: a cached focus is valid until one arrives

    /** UiAutomation, the way the uiautomator command makes one: a handler thread and a UiAutomationConnection.
     *  There is room for one such connection on the phone at a time: it is made on the first use and kept
     *  until the process ends (shutdown). */
    private static synchronized UiAutomation automation() throws Exception {
        if (automation != null) {
            return automation;
        }
        HandlerThread thread = new HandlerThread("phonectl-ui");
        thread.start();
        Class<?> connectionClass = Class.forName("android.app.UiAutomationConnection");
        Object connection = connectionClass.getConstructor().newInstance();
        Constructor<UiAutomation> constructor = UiAutomation.class.getDeclaredConstructor(
                android.os.Looper.class, Class.forName("android.app.IUiAutomationConnection"));
        constructor.setAccessible(true);
        UiAutomation created = constructor.newInstance(thread.getLooper(), connection);
        UiAutomation.class.getMethod("connect").invoke(created);
        AccessibilityServiceInfo info = created.getServiceInfo();
        info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        created.setServiceInfo(info);
        created.setOnAccessibilityEventListener(new UiAutomation.OnAccessibilityEventListener() {
            @Override
            public void onAccessibilityEvent(AccessibilityEvent event) {
                int type = event.getEventType();
                if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED || type == AccessibilityEvent.TYPE_WINDOWS_CHANGED) {
                    windowEvents++;
                }
            }
        });
        automation = created;
        return automation;
    }

    private static synchronized void shutdown() {
        if (automation != null) {
            try {
                UiAutomation.class.getMethod("disconnect").invoke(automation);
            } catch (Throwable ignored) {
                // the process ends right after; nothing more to do
            }
            automation = null;
        }
    }

    // --- clipboard -------------------------------------------------------------------------------

    private static Object clipboard() throws Exception {
        Class<?> serviceManager = Class.forName("android.os.ServiceManager");
        IBinder binder = (IBinder) serviceManager.getMethod("getService", String.class).invoke(null, "clipboard");
        if (binder == null) {
            throw new IllegalStateException("no clipboard service");
        }
        Class<?> stub = Class.forName("android.content.IClipboard$Stub");
        return stub.getMethod("asInterface", IBinder.class).invoke(null, binder);
    }

    private static Method method(Object service, String name) {
        for (Method candidate : service.getClass().getMethods()) {
            if (candidate.getName().equals(name)) {
                return candidate;
            }
        }
        throw new IllegalStateException("the clipboard service has no method " + name);
    }

    /** Arguments from the parameter types: ClipData -> the clip; the first String is the package, any other
     *  String (the attribution tag) is null; ints (the user id, on Android 14 also the device id) are 0. */
    private static Object[] arguments(Method method, ClipData clip) {
        Class<?>[] types = method.getParameterTypes();
        Object[] arguments = new Object[types.length];
        boolean packageGiven = false;
        for (int i = 0; i < types.length; i++) {
            if (types[i] == ClipData.class) {
                arguments[i] = clip;
            } else if (types[i] == String.class) {
                arguments[i] = packageGiven ? null : PACKAGE;
                packageGiven = true;
            } else if (types[i] == int.class) {
                arguments[i] = 0;
            } else {
                throw new IllegalStateException("unexpected parameter type " + types[i]);
            }
        }
        return arguments;
    }

    private static void clipSet(String text) throws Exception {
        Object service = clipboard();
        Method set = method(service, "setPrimaryClip");
        set.invoke(service, arguments(set, ClipData.newPlainText("phonectl", text)));
    }

    private static void clipGet(JSONObject answer) throws Exception {
        Object service = clipboard();
        Method get = method(service, "getPrimaryClip");
        ClipData clip = (ClipData) get.invoke(service, arguments(get, null));
        answer.put("items", clip == null ? 0 : clip.getItemCount());
        CharSequence text = clip != null && clip.getItemCount() > 0 ? clip.getItemAt(0).getText() : null;
        answer.put("text", text == null ? JSONObject.NULL : text.toString());
    }

    // --- window state: focus, rotation, lock screen ----------------------------------------------

    private static JSONObject cachedState;
    private static long cachedAtMs;
    private static long cachedEvents = -1;
    private static String displaySize;  // "wm size" and "wm density" do not change while the process runs
    private static String displayDensity;

    /** The window with the focus, the rotation and the lock screen, read from `dumpsys window` (about 100 ms
     *  on the phone, with no adb process around it). With `fresh` false the last answer is used until a window
     *  event arrives or 1.5 s have passed, whichever is first. */
    private static synchronized JSONObject windowState(boolean fresh) throws Exception {
        long now = System.currentTimeMillis();
        if (!fresh && cachedState != null && cachedEvents == windowEvents && now - cachedAtMs < 1500) {
            return cachedState;
        }
        long eventsBefore = windowEvents;
        String text = sh("dumpsys window | grep -E 'mCurrentFocus|mCurrentRotation|isKeyguardShowing'");
        String focus = first("mCurrentFocus=Window\\{\\S+ \\S+ ([^\\s}]+)", text);
        String rotation = first("mCurrentRotation=(?:ROTATION_)?(\\d+)", text);
        JSONObject state = new JSONObject()
                .put("focus", focus == null ? "?" : focus)
                .put("keyguard", text.contains("isKeyguardShowing=true"))
                .put("rotation", rotation == null ? JSONObject.NULL : Integer.parseInt(rotation) * 90);
        cachedState = state;
        cachedAtMs = System.currentTimeMillis();
        cachedEvents = eventsBefore;
        return state;
    }

    // --- screenshot and its facts ----------------------------------------------------------------

    private static void shot(JSONObject answer, String dir, String name) throws Exception {
        sh("mkdir -p " + quote(dir));
        String png = dir + "/" + name + ".png";
        long start = nowNs();
        sh("screencap -p " + quote(png));
        long screencapDone = nowNs();
        answer.put("png", png);
        answer.put("start_ns", start);
        answer.put("screencap_done_ns", screencapDone);

        if (displaySize == null) {
            displaySize = sh("wm size");
            displayDensity = sh("wm density");
        }
        String w = first("Physical size: (\\d+)x\\d+", displaySize);
        String h = first("Physical size: \\d+x(\\d+)", displaySize);
        int width = w == null ? 0 : Integer.parseInt(w);
        int height = h == null ? 0 : Integer.parseInt(h);
        answer.put("size", w == null ? JSONObject.NULL : new JSONArray().put(width).put(height));
        String d = first("Physical density: (\\d+)", displayDensity);
        answer.put("density", d == null ? JSONObject.NULL : Integer.parseInt(d));
        JSONObject state = windowState(true);
        answer.put("rotation", state.get("rotation"));
        answer.put("focus", state.getString("focus"));

        answer.put("status_bar", JSONObject.NULL);
        answer.put("navigation_bar", JSONObject.NULL);
        JSONArray windows = new JSONArray();
        try {
            List<AccessibilityWindowInfo> list = automation().getWindows();
            for (AccessibilityWindowInfo info : list) {
                Rect bounds = new Rect();
                info.getBoundsInScreen(bounds);
                AccessibilityNodeInfo root = info.getRoot();
                String pkg = root == null ? null : String.valueOf(root.getPackageName());
                JSONObject entry = rect(bounds).put("type", info.getType()).put("layer", info.getLayer())
                        .put("active", info.isActive()).put("focused", info.isFocused())
                        .put("package", pkg == null ? JSONObject.NULL : pkg)
                        .put("title", info.getTitle() == null ? JSONObject.NULL : info.getTitle().toString());
                windows.put(entry);
                boolean systemUi = "com.android.systemui".equals(pkg);
                boolean spansWidth = width > 0 && bounds.left == 0 && bounds.right == width;
                if (systemUi && spansWidth && bounds.top == 0 && bounds.height() > 0 && bounds.height() < 250
                        && answer.isNull("status_bar")) {
                    answer.put("status_bar", rect(bounds).put("height_px", bounds.height()));
                }
                if (systemUi && spansWidth && height > 0 && bounds.bottom == height && bounds.height() < 250
                        && bounds.top > height / 2 && answer.isNull("navigation_bar")) {
                    answer.put("navigation_bar", rect(bounds).put("height_px", bounds.height()));
                }
            }
            answer.put("windows", windows);
        } catch (Throwable problem) {
            Throwable cause = problem.getCause() != null ? problem.getCause() : problem;
            answer.put("windows", windows);
            answer.put("windows_error", cause.getClass().getName() + ": " + cause.getMessage());
        }
        answer.put("windows_done_ns", nowNs());
    }

    // --- the phone and the apps ------------------------------------------------------------------

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[65536];
            int n;
            while ((n = in.read(buffer)) > 0) {
                digest.update(buffer, 0, n);
            }
        }
        StringBuilder hex = new StringBuilder();
        for (byte b : digest.digest()) {
            hex.append(String.format("%02x", b));
        }
        return hex.toString();
    }

    private static void env(JSONObject answer, String[] packages) throws Exception {
        answer.put("time_ns", nowNs());
        JSONObject props = new JSONObject();
        String[] names = {"ro.product.manufacturer", "ro.product.brand", "ro.product.model", "ro.product.device",
                "ro.build.version.release", "ro.build.version.sdk", "ro.build.version.security_patch",
                "ro.product.cpu.abi", "persist.sys.locale", "ro.product.locale", "persist.sys.timezone"};
        for (String name : names) {
            props.put(name, sh("getprop " + name));
        }
        answer.put("props", props);
        answer.put("private", new JSONObject().put("ro.build.id", sh("getprop ro.build.id"))
                .put("ro.build.fingerprint", sh("getprop ro.build.fingerprint")));
        JSONObject settings = new JSONObject();
        String[][] keys = {{"system", "font_scale"}, {"system", "screen_off_timeout"}, {"global", "window_animation_scale"},
                {"global", "transition_animation_scale"}, {"global", "animator_duration_scale"},
                {"secure", "navigation_mode"}, {"secure", "default_input_method"}};
        for (String[] key : keys) {
            settings.put(key[0] + "." + key[1], sh("settings get " + key[0] + " " + key[1]));
        }
        answer.put("settings", settings);
        answer.put("night", sh("cmd uimode night"));
        String size = sh("wm size");
        String density = sh("wm density");
        String w = first("Physical size: (\\d+)x\\d+", size);
        String h = first("Physical size: \\d+x(\\d+)", size);
        String d = first("Physical density: (\\d+)", density);
        answer.put("display", new JSONObject()
                .put("size", w == null ? JSONObject.NULL : new JSONArray().put(Integer.parseInt(w)).put(Integer.parseInt(h)))
                .put("density", d == null ? JSONObject.NULL : Integer.parseInt(d)));
        JSONObject roles = new JSONObject();
        String[] roleNames = {"DIALER", "BROWSER", "SMS", "HOME"};
        for (String role : roleNames) {
            String holder = sh("cmd role get-role-holders android.app.role." + role);
            roles.put(role.toLowerCase(), holder.isEmpty() ? JSONObject.NULL : holder.split("\\s+")[0]);
        }
        answer.put("roles", roles);
        JSONObject apps = new JSONObject();
        for (String pkg : packages) {
            String info = sh("dumpsys package " + pkg);
            String name = first("versionName=(\\S+)", info);
            String code = first("versionCode=(\\d+)", info);
            String path = sh("pm path " + pkg + " | head -1 | cut -d: -f2");
            JSONObject app = new JSONObject()
                    .put("version_name", name == null || name.equals("null") ? JSONObject.NULL : name)
                    .put("version_code", code == null || code.equals("0") ? JSONObject.NULL : Integer.parseInt(code))
                    .put("apk_path", path.isEmpty() ? JSONObject.NULL : path)
                    .put("apk_sha256", JSONObject.NULL);
            if (!path.isEmpty() && new File(path).canRead()) {
                app.put("apk_sha256", sha256(new File(path)));
            }
            apps.put(pkg, app);
        }
        answer.put("packages", apps);
    }

    // --- the element tree ------------------------------------------------------------------------

    private static String text(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    /** One node and its visible children, with the same attributes `uiautomator dump` writes (the host builds
     *  the same tree from them). Invisible nodes are left out, as uiautomator leaves them out. */
    private static JSONObject node(AccessibilityNodeInfo n) throws Exception {
        Rect b = new Rect();
        n.getBoundsInScreen(b);
        JSONObject o = new JSONObject()
                .put("class", text(n.getClassName())).put("package", text(n.getPackageName()))
                .put("resource-id", text(n.getViewIdResourceName())).put("text", text(n.getText()))
                .put("content-desc", text(n.getContentDescription()))
                .put("bounds", new JSONArray().put(b.left).put(b.top).put(b.right).put(b.bottom))
                .put("clickable", n.isClickable()).put("long-clickable", n.isLongClickable())
                .put("scrollable", n.isScrollable()).put("enabled", n.isEnabled()).put("checkable", n.isCheckable())
                .put("checked", n.isChecked()).put("focusable", n.isFocusable()).put("focused", n.isFocused())
                .put("selected", n.isSelected()).put("password", n.isPassword());
        JSONArray children = new JSONArray();
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo child = n.getChild(i);
            if (child != null) {
                if (child.isVisibleToUser()) {
                    children.put(node(child));
                }
                child.recycle();
            }
        }
        o.put("children", children);
        return o;
    }

    /** The screen as a tree, read straight from UiAutomation: no wait for the screen to go idle (which the
     *  uiautomator command does, and which a blinking cursor can stretch to its limit). With "windows" every
     *  window of the screen is a root, the floating selection toolbar included. */
    private static void tree(JSONObject answer, boolean allWindows) throws Exception {
        UiAutomation automation = automation();
        JSONArray roots = new JSONArray();
        if (allWindows) {
            for (AccessibilityWindowInfo info : automation.getWindows()) {
                AccessibilityNodeInfo root = info.getRoot();
                if (root != null) {
                    roots.put(node(root));
                    root.recycle();
                }
            }
        } else {
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            if (root != null) {
                roots.put(node(root));
                root.recycle();
            }
        }
        answer.put("roots", roots);
    }

    // --- input -----------------------------------------------------------------------------------

    private static void inject(UiAutomation automation, android.view.InputEvent event) throws Exception {
        inject(automation, event, true);
    }

    /** With `sync` the call returns when the event has been dispatched (about 40 ms each); without, it queues the
     *  event and returns at once. Events of one batch are dispatched in the order they were queued, so a batch
     *  of keys is queued and only its last event is synchronous: the answer comes when the whole batch is in. */
    private static void inject(UiAutomation automation, android.view.InputEvent event, boolean sync) throws Exception {
        if (!automation.injectInputEvent(event, sync)) {
            throw new IllegalStateException("the input event was not injected");
        }
    }

    private static MotionEvent motion(long down, int action, float x, float y) {
        MotionEvent event = MotionEvent.obtain(down, android.os.SystemClock.uptimeMillis(), action, x, y, 0);
        event.setSource(InputDevice.SOURCE_TOUCHSCREEN);
        return event;
    }

    /** A touch from (x1,y1) to (x2,y2) over `ms` milliseconds: a tap when the points are equal and `ms` is
     *  short, a long-press when `ms` is long, a swipe otherwise. */
    private static void touch(int x1, int y1, int x2, int y2, int ms) throws Exception {
        UiAutomation automation = automation();
        long down = android.os.SystemClock.uptimeMillis();
        inject(automation, motion(down, MotionEvent.ACTION_DOWN, x1, y1));
        if (x1 != x2 || y1 != y2) {
            int steps = Math.max(2, ms / 16);
            for (int i = 1; i <= steps; i++) {
                float f = (float) i / steps;
                Thread.sleep(ms / steps);
                inject(automation, motion(down, MotionEvent.ACTION_MOVE, x1 + (x2 - x1) * f, y1 + (y2 - y1) * f));
            }
        } else if (ms > 0) {
            Thread.sleep(ms);
        }
        inject(automation, motion(down, MotionEvent.ACTION_UP, x2, y2));
    }

    private static int keyCode(String name) {
        if (name.matches("\\d+")) {
            return Integer.parseInt(name);
        }
        int code = KeyEvent.keyCodeFromString(name.startsWith("KEYCODE_") ? name : "KEYCODE_" + name);
        if (code == KeyEvent.KEYCODE_UNKNOWN) {
            throw new IllegalArgumentException("unknown key " + name);
        }
        return code;
    }

    private static void keys(String[] names) throws Exception {
        UiAutomation automation = automation();
        for (int i = 0; i < names.length; i++) {
            int code = keyCode(names[i]);
            long now = android.os.SystemClock.uptimeMillis();
            KeyEvent down = new KeyEvent(now, now, KeyEvent.ACTION_DOWN, code, 0);
            down.setSource(InputDevice.SOURCE_KEYBOARD);
            inject(automation, down, false);
            KeyEvent up = new KeyEvent(now, android.os.SystemClock.uptimeMillis(), KeyEvent.ACTION_UP, code, 0);
            up.setSource(InputDevice.SOURCE_KEYBOARD);
            inject(automation, up, i == names.length - 1);  // the last one waits: the batch is in
        }
    }

    private static void type(String text) throws Exception {
        UiAutomation automation = automation();
        KeyCharacterMap map = KeyCharacterMap.load(KeyCharacterMap.VIRTUAL_KEYBOARD);
        KeyEvent[] events = map.getEvents(text.toCharArray());
        if (events == null) {
            throw new IllegalArgumentException("the text cannot be typed with a key map: " + text);
        }
        for (int i = 0; i < events.length; i++) {
            events[i].setSource(InputDevice.SOURCE_KEYBOARD);
            inject(automation, events[i], i == events.length - 1);  // queued in order; the last one waits
        }
    }

    // --- commands --------------------------------------------------------------------------------

    private static JSONObject run(String[] args) throws Exception {
        if (args.length < 1) {
            throw new IllegalArgumentException("usage: clip-get | clip-set TEXT | shot DIR NAME | focus | env PACKAGE... | tree [windows]"
                    + " | tap X Y | swipe X1 Y1 X2 Y2 MS | long-press X Y MS | key NAME... | text TEXT");
        }
        JSONObject answer = new JSONObject();
        answer.put("command", args[0]);
        switch (args[0]) {
            case "clip-set":
                clipSet(args.length > 1 ? args[1] : "");
                break;
            case "clip-get":
                clipGet(answer);
                break;
            case "shot":
                if (args.length < 3) {
                    throw new IllegalArgumentException("usage: shot DIR NAME");
                }
                shot(answer, args[1], args[2]);
                break;
            case "focus": {
                JSONObject state = windowState(false);
                answer.put("focus", state.get("focus")).put("keyguard", state.get("keyguard")).put("rotation", state.get("rotation"));
                break;
            }
            case "env": {
                String[] packages = new String[args.length - 1];
                System.arraycopy(args, 1, packages, 0, packages.length);
                env(answer, packages);
                break;
            }
            case "tree":
                tree(answer, args.length > 1 && args[1].equals("windows"));
                break;
            case "tap":
                touch(Integer.parseInt(args[1]), Integer.parseInt(args[2]), Integer.parseInt(args[1]), Integer.parseInt(args[2]), 0);
                break;
            case "swipe":
                touch(Integer.parseInt(args[1]), Integer.parseInt(args[2]), Integer.parseInt(args[3]), Integer.parseInt(args[4]),
                        Integer.parseInt(args[5]));
                break;
            case "long-press":
                touch(Integer.parseInt(args[1]), Integer.parseInt(args[2]), Integer.parseInt(args[1]), Integer.parseInt(args[2]),
                        Integer.parseInt(args[3]));
                break;
            case "key": {
                String[] names = new String[args.length - 1];
                System.arraycopy(args, 1, names, 0, names.length);
                keys(names);
                break;
            }
            case "text":
                type(args.length > 1 ? args[1] : "");
                break;
            case "quit":
                break;
            default:
                throw new IllegalArgumentException("unknown command " + args[0]);
        }
        answer.put("ok", true);
        return answer;
    }

    /** run(), with every failure turned into {"ok":false,"error":...}, and the shot's raw sidecar left next to
     *  the picture on the phone. */
    private static JSONObject answer(String[] args) {
        JSONObject answer;
        try {
            answer = run(args);
        } catch (Throwable problem) {
            Throwable cause = problem.getCause() != null ? problem.getCause() : problem;
            answer = new JSONObject();
            try {
                answer.put("ok", false);
                answer.put("error", cause.getClass().getName() + ": " + cause.getMessage());
            } catch (Exception ignored) {
                // a JSONObject.put of two strings does not fail
            }
        }
        if (answer.optBoolean("ok") && answer.has("png") && !answer.has("png_bytes")) {
            try (java.io.FileOutputStream out = new java.io.FileOutputStream(answer.optString("png") + ".raw.json")) {
                out.write(answer.toString(1).getBytes("UTF-8"));
            } catch (Exception ignored) {
                // the answer itself is the same; the host notices a missing file
            }
        }
        return answer;
    }

    // --- the server ------------------------------------------------------------------------------

    private static byte[] readAll(File file) throws Exception {
        try (FileInputStream in = new FileInputStream(file)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[65536];
            int n;
            while ((n = in.read(buffer)) > 0) {
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        }
    }

    private static void serve(String name) throws Exception {
        LocalServerSocket server = new LocalServerSocket(name);
        automation();  // connect now, so the first command does not pay for it
        System.out.println(new JSONObject().put("ready", true).put("socket", name).toString());
        System.out.flush();
        boolean quit = false;
        while (!quit) {
            LocalSocket client = server.accept();
            client.setSoTimeout((int) IDLE_EXIT_MS);
            BufferedReader in = new BufferedReader(new InputStreamReader(client.getInputStream(), "UTF-8"));
            OutputStream out = client.getOutputStream();
            try {
                String line;
                while ((line = in.readLine()) != null) {
                    JSONObject request = new JSONObject(line);
                    JSONArray array = request.getJSONArray("args");
                    String[] args = new String[array.length()];
                    for (int i = 0; i < args.length; i++) {
                        args[i] = array.getString(i);
                    }
                    byte[] binary = null;
                    JSONObject answer = answer(args);
                    if (request.optBoolean("inline") && answer.optBoolean("ok") && answer.has("png")) {
                        binary = readAll(new File(answer.getString("png")));
                        answer.put("png_bytes", binary.length);
                        try (java.io.FileOutputStream raw = new java.io.FileOutputStream(answer.getString("png") + ".raw.json")) {
                            raw.write(answer.toString(1).getBytes("UTF-8"));
                        }
                    }
                    out.write((answer.toString() + "\n").getBytes("UTF-8"));
                    if (binary != null) {
                        out.write(binary);
                    }
                    out.flush();
                    if (args.length > 0 && args[0].equals("quit")) {
                        quit = true;
                        break;
                    }
                }
            } catch (java.net.SocketTimeoutException idle) {
                quit = true;  // nobody asked for ten minutes: the computer is gone
            } finally {
                try {
                    client.close();
                } catch (Exception ignored) {
                    // closed already
                }
            }
        }
        server.close();
    }

    public static void main(String[] args) {
        try {
            if (args.length >= 2 && args[0].equals("serve")) {
                serve(args[1]);
            } else {
                System.out.println(answer(args).toString());
            }
        } catch (Throwable problem) {
            System.out.println("{\"ok\":false,\"error\":\"" + String.valueOf(problem).replace("\"", "'") + "\"}");
        }
        shutdown();
        System.exit(0);  // the handler thread of UiAutomation would keep the process alive
    }
}
