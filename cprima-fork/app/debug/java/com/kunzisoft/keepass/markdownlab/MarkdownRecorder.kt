package com.kunzisoft.keepass.markdownlab

import android.content.Context
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * The record of one MarkdownLab run: one JSON object per line, the header first. The file is the truth; the screen
 * only shows it. It records what was observed and never a verdict.
 */
class MarkdownRecorder(val runId: String = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())) {

    private val lines = ArrayList<String>()
    private var seq = 0

    fun header(context: Context, caseCount: Int, dataTag: String, envId: String?) {
        add("run.header", null) {
            put("package", context.packageName)
            put("version", context.packageManager.getPackageInfo(context.packageName, 0).versionName)
            put("release", Build.VERSION.RELEASE)
            put("model", Build.MODEL)
            put("cases", caseCount)
            put("data", dataTag)
            if (envId != null) put("env", envId)
        }
    }

    /** One observation: what the renderer returned for a case, how long it took, or the exception it threw. */
    fun add(probe: String, caseId: String?, fill: JSONObject.() -> Unit) {
        val line = JSONObject()
            .put("v", VERSION)
            .put("run", runId)
            .put("sdk", Build.VERSION.SDK_INT)
            .put("seq", seq++)
            .put("t", System.currentTimeMillis())
            .put("probe", probe)
        if (caseId != null) line.put("case", caseId)
        line.fill()
        lines += line.toString()
    }

    fun linesOf(caseId: String): List<String> = lines.filter { JSONObject(it).optString("case") == caseId }

    fun all(): List<String> = lines

    fun save(directory: File): File {
        val dir = File(directory, runId).also { it.mkdirs() }
        val file = File(dir, "diagnostics.jsonl")
        file.writeText(lines.joinToString("\n", postfix = "\n"), Charsets.UTF_8)
        return file
    }

    companion object {
        const val VERSION = 1

        /** The first 12 hex digits of the SHA-256 of the case files, so that a record says which data it came from. */
        fun tagOf(files: List<String>): String {
            val digest = MessageDigest.getInstance("SHA-256")
            files.forEach { digest.update(it.toByteArray(Charsets.UTF_8)) }
            return digest.digest().joinToString("") { "%02x".format(it) }.take(12)
        }

        fun spansJson(spans: List<com.kunzisoft.keepass.utils.MdSpan>): JSONArray {
            val array = JSONArray()
            spans.forEach { array.put(JSONObject().put("kind", it.kind).put("start", it.start).put("end", it.end)) }
            return array
        }
    }
}
