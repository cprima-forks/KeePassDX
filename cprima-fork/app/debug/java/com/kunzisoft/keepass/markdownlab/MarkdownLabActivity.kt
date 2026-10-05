package com.kunzisoft.keepass.markdownlab

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.text.Spanned
import android.util.Log
import android.view.View
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.kunzisoft.keepass.R
import com.kunzisoft.keepass.utils.MarkdownCases
import com.kunzisoft.keepass.utils.MarkdownRenderer
import com.kunzisoft.keepass.utils.MarkdownSpans
import com.kunzisoft.keepass.utils.MdCase
import org.json.JSONObject

/**
 * MarkdownLab (spike for upstream issue #2702): shows one case at a time, the Markdown as stored and what the
 * renderer makes of it, side by side in one screen, and records what was observed.
 *
 * It observes and never judges: no expected result is shown. The layout is a fixed header (which case), a scrolling
 * content area and a fixed footer (the actions, and in every screenshot where it was taken). A script drives it
 * through the intent extras of [Companion]; the screen is never scraped.
 *
 * Debug build only, no launcher entry. Start it with
 * `adb shell am start -n com.kunzisoft.keepass.cprima_fork/com.kunzisoft.keepass.markdownlab.MarkdownLabActivity --es case-id M-FM-001`.
 * The rendered text is not tappable: a link in a case is shown, never opened.
 */
class MarkdownLabActivity : Activity() {

    private lateinit var cases: List<MdCase>
    private lateinit var recorder: MarkdownRecorder
    private var dataTag = ""
    private var index = 0
    private var loaded = false

    /** What the renderer returned for one case, observed once. */
    private class Observed(val rendered: Spanned?, val spans: String, val millis: Double, val error: String?)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.markdownlab_activity)
        val root = findViewById<View>(R.id.markdownlab_root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }

        findViewById<View>(R.id.markdownlab_previous).setOnClickListener { show(index - 1) }
        findViewById<View>(R.id.markdownlab_next).setOnClickListener { show(index + 1) }
        findViewById<View>(R.id.markdownlab_run).setOnClickListener { show(index) }
        findViewById<View>(R.id.markdownlab_copy).setOnClickListener { copyRecord() }
        findViewById<View>(R.id.markdownlab_save).setOnClickListener {
            Toast.makeText(this, save().path, Toast.LENGTH_LONG).show()
        }

        try {
            val files = MarkdownCases.TOPICS.map { readAsset(MarkdownCases.pathOf(it)) }
            cases = MarkdownCases.load(::readAsset)
            dataTag = MarkdownRecorder.tagOf(files)
        } catch (e: Exception) {
            showFailure("the case data cannot be used: ${e.javaClass.simpleName}: ${e.message}")
            return
        }
        recorder = MarkdownRecorder()
        recorder.header(this, cases.size, dataTag, intent.getStringExtra(EXTRA_ENV_ID))
        loaded = true
        findViewById<TextView>(R.id.markdownlab_provenance).text = provenance()
        handleIntent(intent, first = true)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (loaded) handleIntent(intent, first = false)
    }

    // ----- the control interface of the scripts

    private fun handleIntent(intent: Intent, first: Boolean) {
        if (intent.getBooleanExtra(EXTRA_BATCH, false)) {
            runBatch(intent.getIntExtra(EXTRA_REPEAT, 1).coerceAtLeast(1))
            return
        }
        val caseId = intent.getStringExtra(EXTRA_CASE_ID)
        val action = intent.getStringExtra(EXTRA_ACTION)
        when {
            action == "next" -> show(index + 1)
            action == "prev" -> show(index - 1)
            action == "run" -> show(index)
            action == "export" -> save()
            action == "exit" -> finish()
            caseId != null -> {
                val target = cases.indexOfFirst { it.id == caseId }
                if (target < 0) showFailure("unknown case $caseId") else show(target)
            }
            first -> show(0)
        }
    }

    // ----- the screen

    private fun showFailure(message: String) {
        findViewById<TextView>(R.id.markdownlab_case_id).text = getString(R.string.markdownlab_no_data)
        findViewById<TextView>(R.id.markdownlab_requirements).text = message
        findViewById<TextView>(R.id.markdownlab_provenance).text = provenanceBase()
        Log.e(TAG, "MARKDOWNLAB_ERROR $message")
        listOf(
            R.id.markdownlab_run, R.id.markdownlab_copy, R.id.markdownlab_save,
            R.id.markdownlab_previous, R.id.markdownlab_next
        ).forEach { findViewById<View>(it).isEnabled = false }
    }

    private fun show(newIndex: Int) {
        val count = cases.size
        index = ((newIndex % count) + count) % count
        val case = cases[index]
        val observed = observe(case, repeat = 1)

        findViewById<ScrollView>(R.id.markdownlab_content).scrollTo(0, 0)
        findViewById<TextView>(R.id.markdownlab_position).text = "${index + 1} / $count"
        findViewById<TextView>(R.id.markdownlab_case_id).text = case.id
        findViewById<TextView>(R.id.markdownlab_requirements).text =
            case.requirements.joinToString(" · ") + "  ·  " + case.level + "  ·  " + case.current

        findViewById<TextView>(R.id.markdownlab_markdown).text =
            if (case.markdown.isEmpty()) getString(R.string.markdownlab_empty) else visible(case.markdown)
        findViewById<TextView>(R.id.markdownlab_markdown_note).text =
            getString(R.string.markdownlab_characters, case.markdown.length)

        val shown = findViewById<TextView>(R.id.markdownlab_rendered)
        if (observed.error != null) {
            shown.text = observed.error
        } else {
            // A link in the text is shown and never opened: no movement method is set
            shown.text = observed.rendered
        }
        findViewById<TextView>(R.id.markdownlab_rendered_note).text =
            getString(R.string.markdownlab_rendered_note, observed.rendered?.length ?: 0, observed.millis)
        findViewById<TextView>(R.id.markdownlab_spans).text =
            observed.spans.ifEmpty { getString(R.string.markdownlab_none) }
    }

    /** Renders the case, records it and returns what was seen. With `repeat` > 1 the best of the runs is the time. */
    private fun observe(case: MdCase, repeat: Int): Observed {
        val limits = if (case.maxChars != null) {
            MarkdownRenderer.Limits(case.maxChars, case.maxDepth ?: MarkdownRenderer.Limits.DEFAULT.maxDepth)
        } else MarkdownRenderer.Limits.DEFAULT
        var rendered: Spanned? = null
        var error: String? = null
        var first = 0.0
        var best = Double.MAX_VALUE
        try {
            for (run in 0 until repeat) {
                val started = System.nanoTime()
                rendered = MarkdownRenderer.render(case.markdown, limits)
                val millis = (System.nanoTime() - started) / 1_000_000.0
                if (run == 0) first = millis
                if (millis < best) best = millis
            }
        } catch (t: Throwable) {
            // Whatever the library or the renderer throws is an observation, for example a NoSuchMethodError on an old Android
            error = t.javaClass.name + ": " + t.message
            Log.e(TAG, "render failed for ${case.id}", t)
        }
        val spans = rendered?.let { MarkdownSpans.spansOf(it) }.orEmpty()
        val spanText = spans.joinToString("\n")
        recorder.add("markdown.render", case.id) {
            put("markdown", case.markdown)
            put("text", rendered?.toString() ?: JSONObject.NULL)
            put("spans", MarkdownRecorder.spansJson(spans))
            put("millis_first", first)
            put("millis_best", if (best == Double.MAX_VALUE) 0.0 else best)
            put("repeat", repeat)
            put("error", error ?: JSONObject.NULL)
        }
        return Observed(rendered, spanText, if (best == Double.MAX_VALUE) 0.0 else best, error)
    }

    /** The stored text with every space as · and every line end as ↵, so that trailing spaces can be seen. */
    private fun visible(text: String) = text.replace(" ", "·").replace("\n", "↵\n")

    private fun provenanceBase() =
        "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}) · ${Build.MODEL} · " +
                "KeePassDX ${packageManager.getPackageInfo(packageName, 0).versionName}"

    private fun provenance() = provenanceBase() + " · schema ${MarkdownRecorder.VERSION} · data $dataTag"

    // ----- files and batch

    private fun labDirectory() = java.io.File(getExternalFilesDir(null) ?: filesDir, "markdownlab").also { it.mkdirs() }

    private fun save(): java.io.File = recorder.save(labDirectory())

    private fun copyRecord() {
        val text = recorder.linesOf(cases[index].id).joinToString("\n")
        (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText("MarkdownLab", text))
        Toast.makeText(this, R.string.markdownlab_copied, Toast.LENGTH_SHORT).show()
    }

    /** Observes every case without a screen and ends with one logcat line that names the file. */
    private fun runBatch(repeat: Int) {
        cases.forEach { observe(it, repeat) }
        val file = save()
        Log.i(TAG, "MARKDOWNLAB_DONE n=${cases.size} file=${file.path}")
        show(0)
    }

    private fun readAsset(path: String): String = assets.open(path).bufferedReader().use { it.readText() }

    companion object {
        const val TAG = "MarkdownLab"
        const val EXTRA_CASE_ID = "case-id"
        const val EXTRA_ACTION = "action"
        const val EXTRA_BATCH = "batch"
        const val EXTRA_REPEAT = "repeat"
        const val EXTRA_ENV_ID = "env-id"
    }
}
