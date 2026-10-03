package com.kunzisoft.keepass.linklab

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Looper
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.kunzisoft.keepass.R
import com.kunzisoft.keepass.view.RqCase
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.json.JSONObject

/**
 * LinkLab (fork issue #15): shows one test case at a time and records what Android returns for it.
 *
 * It observes and never judges. The layout is a fixed header (which case), a scrolling content area (the
 * value, the links, what the classifier and the installed apps say) and a fixed footer (the actions, and
 * in every screenshot the provenance of what is shown).
 *
 * Scripts drive it through the intent extras listed in [Companion] and read `state.json`; the screen is
 * never scraped.
 */
class LabActivity : Activity() {

    private lateinit var data: LabData
    private lateinit var recorder: Recorder
    private var loaded = false
    private var index = 0
    private val worker = Executors.newSingleThreadExecutor()
    private val shown = HashMap<String, Shown>()
    private var detailsVisible = false

    /** What has been observed for one case in this session. */
    private class Shown(
        val link: Probes.LinkResult,
        @Volatile var classifier: List<Probes.ClassifierRow>? = null,
        @Volatile var handlers: List<Probes.HandlerRow>? = null
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.linklab_activity)
        applyInsets(R.id.linklab_root, R.id.linklab_header, R.id.linklab_footer)

        findViewById<View>(R.id.linklab_about).setOnClickListener {
            startActivity(Intent(this, LabAboutActivity::class.java))
        }
        findViewById<View>(R.id.linklab_previous).setOnClickListener { show(index - 1) }
        findViewById<View>(R.id.linklab_next).setOnClickListener { show(index + 1) }
        findViewById<View>(R.id.linklab_run).setOnClickListener { show(index, force = true) }
        findViewById<View>(R.id.linklab_copy).setOnClickListener { copyAll() }
        findViewById<View>(R.id.linklab_save).setOnClickListener {
            Toast.makeText(this, save().path, Toast.LENGTH_LONG).show()
        }
        findViewById<View>(R.id.linklab_details_toggle).setOnClickListener {
            detailsVisible = !detailsVisible
            renderDetails()
        }

        try {
            data = LabData.load(this, intent.getStringExtra(EXTRA_CASES_DIR))
        } catch (e: LabDataException) {
            showFailure(e.message ?: "the case data cannot be used")
            return
        }
        recorder = Recorder(SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date()))
        recorder.header(
            this, data, intent.getStringExtra(EXTRA_ENV_ID), intent.getStringExtra(EXTRA_DATA_COMMIT), adhoc = false
        )
        loaded = true
        findViewById<TextView>(R.id.linklab_provenance).text = provenance()
        handleIntent(intent, first = true)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (loaded) handleIntent(intent, first = false)
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    // ----- the control interface of the scripts

    private fun handleIntent(intent: Intent, first: Boolean) {
        if (intent.getBooleanExtra(EXTRA_BATCH, false)) {
            runBatch(intent.getStringExtra(EXTRA_LIST)?.split(',')?.map { it.trim() }?.filter { it.isNotEmpty() })
            return
        }
        val caseId = intent.getStringExtra(EXTRA_CASE_ID)
        val action = intent.getStringExtra(EXTRA_ACTION)
        when {
            action == "next" -> show(index + 1)
            action == "prev" -> show(index - 1)
            action == "probe" -> show(index, force = true)
            action == "export" -> save()
            action == "exit" -> finish()
            action?.startsWith("goto:") == true -> gotoCase(action.removePrefix("goto:"))
            caseId != null -> gotoCase(caseId)
            first -> show(0)
        }
    }

    private fun gotoCase(caseId: String) {
        val target = data.cases.indexOfFirst { it.id == caseId }
        if (target < 0) showFailure("unknown case $caseId") else show(target)
    }

    // ----- the screen

    private fun showFailure(message: String) {
        findViewById<TextView>(R.id.linklab_case_id).text = "No data"
        findViewById<TextView>(R.id.linklab_title).text = message
        findViewById<TextView>(R.id.linklab_provenance).text = provenanceBase()
        Log.e(TAG, "LINKLAB_ERROR $message")
        listOf(R.id.linklab_run, R.id.linklab_copy, R.id.linklab_save, R.id.linklab_previous, R.id.linklab_next)
            .forEach { findViewById<View>(it).isEnabled = false }
    }

    private fun show(newIndex: Int, force: Boolean = false) {
        val count = data.cases.size
        index = ((newIndex % count) + count) % count
        val case = data.cases[index]
        val value = data.valueOf(case)

        // A new case starts at the top; a re-run keeps the position
        if (!force) findViewById<ScrollView>(R.id.linklab_content).scrollTo(0, 0)
        findViewById<TextView>(R.id.linklab_position).text = "${index + 1} / $count"
        findViewById<TextView>(R.id.linklab_case_id).text = case.id
        findViewById<TextView>(R.id.linklab_requirements).text =
            case.requirements.joinToString(" · ") + "  ·  " + case.level
        findViewById<TextView>(R.id.linklab_title).text =
            value.note.replaceFirstChar { it.uppercase() }.ifEmpty { value.id }
        findViewById<TextView>(R.id.linklab_stored).text = visible(value.text)
        val users = data.usedBy(value.id)
        findViewById<TextView>(R.id.linklab_stored_note).text =
            "${value.id} · ${value.text.length} characters · used by " +
                    users.joinToString(", ") { it.id }.let { if (users.size > 6) users.take(6).joinToString(", ") { c -> c.id } + " …" else it }

        val known = shown[case.id]
        if (known != null && !force) {
            render(case, known)
            writeState(case, ready = known.classifier != null && known.handlers != null)
            return
        }
        writeState(case, ready = false)
        val entry = Shown(Probes.links(this, case, value, recorder))
        shown[case.id] = entry
        render(case, entry)
        worker.execute {
            try {
                entry.classifier = Probes.classifier(this, case, value, entry.link, recorder)
                entry.handlers = Probes.handlers(this, case, value, entry.link, recorder)
            } catch (e: Exception) {
                Log.e(TAG, "probe failed for ${case.id}", e)
                recorder.add("skipped", case.id, value.id) {
                    put("probe", "classifier.*|intent.handlers")
                    put("reason", e.javaClass.simpleName + ": " + e.message)
                }
                entry.classifier = entry.classifier ?: emptyList()
                entry.handlers = entry.handlers ?: emptyList()
            }
            runOnUiThread {
                if (data.cases[index].id == case.id) render(case, entry)
                writeState(case, ready = true)
            }
        }
    }

    private fun render(case: RqCase, entry: Shown) {
        val host = findViewById<ViewGroup>(R.id.linklab_field_host)
        host.removeAllViews()
        entry.link.field?.let { field ->
            (field.parent as? ViewGroup)?.removeView(field)
            host.addView(field)
        }

        val links = findViewById<LinearLayout>(R.id.linklab_links)
        links.removeAllViews()
        if (entry.link.spans.isEmpty()) addRow(links, "", getString(R.string.linklab_none))
        entry.link.spans.forEach { span ->
            addRow(links, "${span.start}..${span.end}", visible(span.text) + "\n→ " + (span.url ?: span.kind))
        }

        val classifier = findViewById<LinearLayout>(R.id.linklab_classifier)
        classifier.removeAllViews()
        val rows = entry.classifier
        if (rows == null) addRow(classifier, "", getString(R.string.linklab_pending))
        else rows.forEach { addRow(classifier, it.label, it.value) }

        val handlers = findViewById<LinearLayout>(R.id.linklab_handlers)
        handlers.removeAllViews()
        val handled = entry.handlers
        if (handled == null) addRow(handlers, "", getString(R.string.linklab_pending))
        else if (handled.isEmpty()) addRow(handlers, "", getString(R.string.linklab_none))
        else handled.forEach { addRow(handlers, it.uri, it.handlers.joinToString("\n").ifEmpty { "none" }) }

        renderDetails()
    }

    private fun renderDetails() {
        val toggle = findViewById<TextView>(R.id.linklab_details_toggle)
        val details = findViewById<TextView>(R.id.linklab_details)
        toggle.setText(if (detailsVisible) R.string.linklab_details_hide else R.string.linklab_details_show)
        details.visibility = if (detailsVisible) View.VISIBLE else View.GONE
        if (detailsVisible && loaded) {
            details.text = recorder.linesOf(data.cases[index].id).joinToString("\n\n")
        }
    }

    private fun addRow(container: LinearLayout, label: String, value: String) {
        val row = LayoutInflater.from(this).inflate(R.layout.linklab_row, container, false)
        row.findViewById<TextView>(R.id.linklab_row_label).text = label
        row.findViewById<TextView>(R.id.linklab_row_value).text = value
        container.addView(row)
    }

    private fun provenanceBase() =
        "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}) · ${Build.MODEL} · " +
                "KeePassDX ${packageManager.getPackageInfo(packageName, 0).versionName}"

    private fun provenance() =
        provenanceBase() + " · ${LabSchema.VIEW_KIND} · schema ${LabSchema.VERSION} · " +
                "data ${data.dataTag} (${data.sourceName.substringBefore(':')})"

    // ----- state, files and batch

    private fun labDirectory(): File {
        val base = getExternalFilesDir(null) ?: filesDir
        return File(base, "linklab").also { it.mkdirs() }
    }

    private fun writeState(case: RqCase, ready: Boolean) {
        val state = JSONObject()
            .put("run", recorder.runId)
            .put("case", case.id)
            .put("value", case.value)
            .put("index", index)
            .put("total", data.cases.size)
            .put("ready", ready)
            .put("seq", recorder.lastSequence)
            .put("t", System.currentTimeMillis())
        worker.execute {
            try {
                File(labDirectory(), "state.json").writeText(state.toString())
            } catch (e: Exception) {
                Log.w(TAG, "state.json not written: ${e.message}")
            }
        }
        Log.i(TAG, "LINKLAB_STATE $state")
    }

    private fun save(): File {
        val directory = File(labDirectory(), recorder.runId).also { it.mkdirs() }
        val file = File(directory, "diagnostics.jsonl")
        file.writeText(recorder.lines.joinToString("\n") + "\n")
        return file
    }

    private fun copyAll() {
        val lines = recorder.lines
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("LinkLab", lines.joinToString("\n")))
        Toast.makeText(this, "${lines.size} lines copied", Toast.LENGTH_SHORT).show()
    }

    private fun <T> onMain(block: () -> T): T {
        if (Looper.myLooper() == Looper.getMainLooper()) return block()
        val latch = CountDownLatch(1)
        var result: Any? = null
        var error: Throwable? = null
        runOnUiThread {
            try {
                result = block()
            } catch (throwable: Throwable) {
                error = throwable
            } finally {
                latch.countDown()
            }
        }
        latch.await(60, TimeUnit.SECONDS)
        error?.let { throw it }
        @Suppress("UNCHECKED_CAST")
        return result as T
    }

    /** Probes every code case (or the listed cases) without a gesture, writes the file and ends. */
    private fun runBatch(ids: List<String>?) {
        val targets = ids?.mapNotNull { id -> data.cases.firstOrNull { it.id == id } } ?: data.codeCases
        findViewById<TextView>(R.id.linklab_title).text = "Batch of ${targets.size} cases"
        worker.execute {
            targets.forEachIndexed { number, case ->
                val value = data.valueOf(case)
                val link = onMain { Probes.links(this, case, value, recorder) }
                val entry = Shown(link)
                entry.classifier = Probes.classifier(this, case, value, link, recorder)
                entry.handlers = Probes.handlers(this, case, value, link, recorder)
                shown[case.id] = entry
                runOnUiThread {
                    index = data.cases.indexOfFirst { it.id == case.id }
                    render(case, entry)
                    findViewById<TextView>(R.id.linklab_position).text = "${number + 1} / ${targets.size}"
                    findViewById<TextView>(R.id.linklab_case_id).text = case.id
                    findViewById<TextView>(R.id.linklab_requirements).text =
                        case.requirements.joinToString(" · ") + "  ·  " + case.level
                    findViewById<TextView>(R.id.linklab_stored).text = visible(value.text.take(300))
                    findViewById<TextView>(R.id.linklab_stored_note).text = "${value.id} · ${value.text.length} characters"
                }
            }
            val file = save()
            Log.i(TAG, "LINKLAB_DONE n=${targets.size} file=${file.path}")
            runOnUiThread {
                findViewById<TextView>(R.id.linklab_title).text = "Batch done: ${targets.size} cases, ${file.name}"
                // Stays open for a person to read; a script ends it with --es action exit
            }
        }
    }

    companion object {
        const val TAG = "LinkLab"
        const val EXTRA_CASE_ID = "case-id"
        const val EXTRA_ACTION = "action"
        const val EXTRA_LIST = "list"
        const val EXTRA_BATCH = "batch"
        const val EXTRA_CASES_DIR = "cases-dir"
        const val EXTRA_ENV_ID = "env-id"
        const val EXTRA_DATA_COMMIT = "data-commit"
    }
}

/** Pads the fixed header and footer by the system bars, so that nothing sits under them (edge to edge). */
internal fun Activity.applyInsets(rootId: Int, headerId: Int, footerId: Int) {
    val header = findViewById<View>(headerId)
    val footer = findViewById<View>(footerId)
    val top = header.paddingTop
    val left = header.paddingLeft
    val right = header.paddingRight
    val bottom = footer.paddingBottom
    ViewCompat.setOnApplyWindowInsetsListener(findViewById(rootId)) { _, insets ->
        val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
        header.setPadding(left + bars.left, top + bars.top, right + bars.right, header.paddingBottom)
        footer.setPadding(footer.paddingLeft, footer.paddingTop, footer.paddingRight, bottom + bars.bottom)
        insets
    }
}

/** The text with every invisible or easily confused character written out, so a screenshot shows what is stored. */
internal fun visible(text: String): String {
    if (text.isEmpty()) return "(empty)"
    val out = StringBuilder()
    for (ch in text) {
        val type = Character.getType(ch)
        when {
            ch == '\n' -> out.append("⟨LF⟩")
            ch == '\r' -> out.append("⟨CR⟩")
            ch == '\t' -> out.append("⟨TAB⟩")
            ch == ' ' -> out.append(' ')
            type == Character.CONTROL.toInt() || type == Character.FORMAT.toInt() ||
                    type == Character.SPACE_SEPARATOR.toInt() || type == Character.LINE_SEPARATOR.toInt() ->
                out.append("⟨U+%04X⟩".format(ch.code))
            else -> out.append(ch)
        }
    }
    return out.toString()
}
