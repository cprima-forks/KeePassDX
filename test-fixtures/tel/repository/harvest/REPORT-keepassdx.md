# Harvest of KeePassDX's own screens

Written by `harvest_keepassdx.py`. Navigation only: nothing was changed. Predicted needs come from `predicted-needs-keepassdx.json`, written before looking.

## settings.main

From: the list, the navigation drawer, Settings. 41 nodes of the app on the screen; in front: `com.kunzisoft.keepass.free/com.kunzisoft.keepass.settings.SettingsActivity`.

| Predicted need | Found | Best candidate |
|---|---|---|
| category_application: app timeout, screenshot mode, lock settings | NO (0) | - |
| category_appearance: text size, theme, monospace font | **yes** (1) | `android:id/title` (TextView) |
| category_form_filling: clipboard timeout, copy of protected fields | **yes** (1) | `android:id/title` (TextView) |

With an id or description, not predicted: 38.

- `action_bar_root`   (LinearLayout)
- `content`   (FrameLayout)
- `toolbar_coordinator`   (ViewGroup)
- `toolbar`   (ViewGroup)
- `` Navigate up  (ImageButton)
- `fragment_container`   (FrameLayout)
- `list_container`   (FrameLayout)
- `recycler_view`   (RecyclerView)
- `title`  App (TextView)
- `icon_frame`   (LinearLayout)
- `icon`   (ImageView)
- `title`  App settings (TextView)
- `summary`  Search, lock, history, properties (TextView)
- `icon_frame`   (LinearLayout)
- `icon`   (ImageView)
- `summary`  Keyboard, autofill, clipboard (TextView)
- `icon_frame`   (LinearLayout)
- `icon`   (ImageView)
- `title`  Device unlocking (TextView)
- `summary`  Biometry, device credential (TextView)
- `icon_frame`   (LinearLayout)
- `icon`   (ImageView)
- `summary`  Themes, colors, icons, fonts, attributes (TextView)
- `title`  Database (TextView)
- `icon_frame`   (LinearLayout)

## settings.app_settings

From: the settings, the category row. 37 nodes of the app on the screen; in front: `com.kunzisoft.keepass.free/com.kunzisoft.keepass.settings.SettingsActivity`.

With an id or description, not predicted: 36.

- `action_bar_root`   (LinearLayout)
- `content`   (FrameLayout)
- `toolbar_coordinator`   (ViewGroup)
- `toolbar`   (ViewGroup)
- `` Navigate up  (ImageButton)
- `fragment_container`   (FrameLayout)
- `list_container`   (FrameLayout)
- `recycler_view`   (RecyclerView)
- `title`  General (TextView)
- `title`  Allow no master key (TextView)
- `summary`  Allows tapping the "Open" button if no credentials are selected (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Delete password (TextView)
- `summary`  Deletes the password entered after a connection attempt to a database (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Autosave database (TextView)
- `summary`  Save the database after every important action (in "Modifiable" mode) (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Quick search (TextView)
- `summary`  Request a search when opening a database (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)

## settings.appearance

From: the settings, the category row. 35 nodes of the app on the screen; in front: `com.kunzisoft.keepass.free/com.kunzisoft.keepass.settings.SettingsActivity`.

With an id or description, not predicted: 34.

- `action_bar_root`   (LinearLayout)
- `content`   (FrameLayout)
- `toolbar_coordinator`   (ViewGroup)
- `toolbar`   (ViewGroup)
- `` Navigate up  (ImageButton)
- `fragment_container`   (FrameLayout)
- `list_container`   (FrameLayout)
- `recycler_view`   (RecyclerView)
- `title`  Interface (TextView)
- `title`  App theme (TextView)
- `summary`  Theme used in the app (TextView)
- `title`  Theme brightness (TextView)
- `summary`  Select light or dark themes (TextView)
- `title`  Icon pack (TextView)
- `summary`  Icon pack used in the app (TextView)
- `title`  Entry colours (TextView)
- `summary`  Displays foreground and background colours in an entry (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Colourise passwords (TextView)
- `summary`  Colourise password characters by type (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Nodes (TextView)
- `title`  Hide expired entries (TextView)

## settings.form_filling

From: the settings, the category row. 36 nodes of the app on the screen; in front: `com.kunzisoft.keepass.free/com.kunzisoft.keepass.settings.SettingsActivity`.

With an id or description, not predicted: 35.

- `action_bar_root`   (LinearLayout)
- `content`   (FrameLayout)
- `toolbar_coordinator`   (ViewGroup)
- `toolbar`   (ViewGroup)
- `` Navigate up  (ImageButton)
- `fragment_container`   (FrameLayout)
- `list_container`   (FrameLayout)
- `recycler_view`   (RecyclerView)
- `title`  Credential provider (TextView)
- `title`  Credential provider service (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `icon_frame`   (LinearLayout)
- `icon`   (ImageView)
- `summary`  Configure autofilling to quickly fill out forms in other apps (TextView)
- `title`  Autofill settings (TextView)
- `title`  Share to Magikeyboard (TextView)
- `summary`  Share entries retrieved from autofill to Magikeyboard (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Keyboard (TextView)
- `icon_frame`   (LinearLayout)
- `icon`   (ImageView)
- `summary`  Activate a custom keyboard populating your passwords and all identity fields (TextView)
- `title`  Device keyboard settings (TextView)

## settings.device_unlocking

From: the settings, the category row. 34 nodes of the app on the screen; in front: `com.kunzisoft.keepass.free/com.kunzisoft.keepass.settings.SettingsActivity`.

With an id or description, not predicted: 33.

- `action_bar_root`   (LinearLayout)
- `content`   (FrameLayout)
- `toolbar_coordinator`   (ViewGroup)
- `toolbar`   (ViewGroup)
- `` Navigate up  (ImageButton)
- `fragment_container`   (FrameLayout)
- `list_container`   (FrameLayout)
- `recycler_view`   (RecyclerView)
- `title`  General (TextView)
- `icon_frame`   (LinearLayout)
- `icon`   (ImageView)
- `summary`  Use device unlocking to open a database more easily (TextView)
- `title`  Biometric unlocking (TextView)
- `summary`  Lets you scan your biometric to open the database (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Device credential unlocking (TextView)
- `summary`  Lets you use your device credential to open the database (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Auto-open prompt (TextView)
- `summary`  Automatically request device unlock if the database is set up to use it (TextView)
- `widget_frame`   (LinearLayout)
- `switchWidget`   (Switch)
- `title`  Content (TextView)
