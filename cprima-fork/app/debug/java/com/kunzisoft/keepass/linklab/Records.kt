package com.kunzisoft.keepass.linklab

import android.content.Context
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

/** The version of the diagnostic records. A change of a field name or type raises it. */
object LabSchema {
    const val VERSION = 1

    /** What the lab shows: the real TextFieldView, built directly, tag first and then the value. */
    const val VIEW_KIND = "textfieldview"
    const val TAG_SOURCE = "constant"
}

/** Writes every character above 126 as \uXXXX, so that a record never holds an invisible character. */
internal fun asciiOnly(text: String): String {
    val out = StringBuilder(text.length)
    for (ch in text) {
        if (ch.code > 126) out.append("\\u").append("%04x".format(ch.code)) else out.append(ch)
    }
    return out.toString()
}

/**
 * Collects the records of one run, one JSON line each. Every record has the same envelope: `v`, `run`,
 * `seq`, `t`, `probe`, `case`, `value`; the payload follows.
 */
class Recorder(val runId: String) {
    private var sequence = 0
    private val all = ArrayList<String>()
    private val perCase = HashMap<String, MutableList<String>>()

    val lines: List<String> get() = synchronized(this) { ArrayList(all) }

    val lastSequence: Int get() = synchronized(this) { sequence }

    fun linesOf(caseId: String): List<String> = synchronized(this) { ArrayList(perCase[caseId].orEmpty()) }

    fun add(probe: String, caseId: String?, valueId: String?, fill: JSONObject.() -> Unit = {}): JSONObject {
        val record = JSONObject()
        synchronized(this) {
            sequence += 1
            record.put("v", LabSchema.VERSION)
            record.put("run", runId)
            record.put("seq", sequence)
            record.put("t", System.currentTimeMillis())
            record.put("probe", probe)
            record.put("case", caseId ?: JSONObject.NULL)
            record.put("value", valueId ?: JSONObject.NULL)
            record.fill()
            val line = asciiOnly(record.toString())
            all.add(line)
            if (caseId != null) perCase.getOrPut(caseId) { ArrayList() }.add(line)
        }
        return record
    }

    /** The first record of a run: where the data and the app come from. */
    fun header(context: Context, data: LabData, environmentId: String?, dataCommit: String?, adhoc: Boolean) {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        add("run.header", null, null) {
            put("adhoc", adhoc)
            put("env_id", environmentId ?: JSONObject.NULL)
            put("app", JSONObject()
                .put("package", context.packageName)
                .put("version_name", info.versionName)
                .put("version_code", if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else @Suppress("DEPRECATION") info.versionCode.toLong()))
            put("env", JSONObject()
                .put("sdk", Build.VERSION.SDK_INT)
                .put("release", Build.VERSION.RELEASE)
                .put("model", Build.MODEL)
                .put("classifier", classifierName(context)))
            put("view_kind", LabSchema.VIEW_KIND)
            put("tag_source", LabSchema.TAG_SOURCE)
            put("data", JSONObject()
                .put("source", data.sourceName)
                .put("commit", dataCommit ?: JSONObject.NULL)
                .put("files", JSONObject().also { files -> data.hashes.forEach { (path, hash) -> files.put(path, hash) } }))
        }
    }

    private fun classifierName(context: Context): String =
        if (Build.VERSION.SDK_INT >= 26)
            context.getSystemService(android.view.textclassifier.TextClassificationManager::class.java)
                ?.textClassifier?.javaClass?.name ?: "none"
        else "n/a (API < 26)"
}

internal fun jsonArray(items: List<JSONObject>): JSONArray = JSONArray().also { array -> items.forEach { array.put(it) } }
