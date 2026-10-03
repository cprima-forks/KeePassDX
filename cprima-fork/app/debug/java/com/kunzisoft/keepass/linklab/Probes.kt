package com.kunzisoft.keepass.linklab

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.text.util.Linkify
import android.view.View
import android.view.ViewGroup
import android.view.textclassifier.TextClassification
import android.view.textclassifier.TextClassificationManager
import android.view.textclassifier.TextLinks
import android.view.textclassifier.TextSelection
import android.widget.TextView
import androidx.core.text.util.LinkifyCompat
import com.kunzisoft.keepass.view.RqCase
import com.kunzisoft.keepass.view.RqValue
import com.kunzisoft.keepass.view.TelLinkCases
import com.kunzisoft.keepass.view.TextFieldView
import com.kunzisoft.keepass.view.spikeLinkifyTel
import org.json.JSONArray
import org.json.JSONObject

/**
 * The observations LinkLab makes of one case. Each probe records what an Android API returns or leaves
 * behind; none of them judges. Link probes touch views and run on the main thread; the classifier and the
 * handler probes run on a background thread (the system classifier returns nothing on the main thread).
 */
object Probes {

    /** Longer texts are not probed: the classifier is slow on them and nothing is learnt. */
    const val MAX_TEXT = 2000

    /** The real field view of the case and the spans on its text. */
    class LinkResult(val field: TextFieldView?, val spans: List<SpanDump.Span>) {
        val telSpans: List<SpanDump.Span> get() = spans.filter { it.url?.startsWith("tel:", ignoreCase = true) == true }
    }

    private fun labelOf(fieldName: String) = when (fieldName) {
        TelLinkCases.URL_FIELD -> "URL"
        "notes" -> "Notes"
        "custom" -> "Custom"
        "username" -> "User name"
        "password" -> "Password"
        "title" -> "Title"
        else -> "(no tag)"
    }

    private fun textViewsIn(view: View): List<TextView> =
        if (view is TextView) listOf(view)
        else (view as? ViewGroup)?.let { group ->
            (0 until group.childCount).flatMap { textViewsIn(group.getChildAt(it)) }
        } ?: emptyList()

    /** Main thread. */
    fun links(activity: Activity, case: RqCase, value: RqValue, rec: Recorder): LinkResult {
        val text = value.text
        if (text.length > MAX_TEXT) {
            rec.add("skipped", case.id, value.id) {
                put("probe", "link.*")
                put("reason", "text longer than $MAX_TEXT characters (${text.length})")
            }
            return LinkResult(null, emptyList())
        }
        val tag = TelLinkCases.tagOf(case.field)

        // The mask based call alone
        val maskView = TextView(activity).apply { this.text = text }
        val returned = LinkifyCompat.addLinks(maskView, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        rec.add("link.mask", case.id, value.id) {
            put("call", "LinkifyCompat.addLinks(WEB_URLS|EMAIL_ADDRESSES)")
            put("returned", returned)
            put("spans", SpanDump.json(SpanDump.spansOf(maskView)))
        }

        // The two calls of TextFieldView.linkify() on a plain text view
        val spikeView = TextView(activity).apply { this.text = text }
        LinkifyCompat.addLinks(spikeView, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        spikeLinkifyTel(spikeView, tag)
        rec.add("link.spike", case.id, value.id) {
            put("call", "addLinks(WEB_URLS|EMAIL_ADDRESSES), then spikeLinkifyTel")
            put("spans", SpanDump.json(SpanDump.spansOf(spikeView)))
        }

        // The real field view, built the way the template does it: the tag first, the value after
        val field = TextFieldView(activity)
        field.label = labelOf(case.field)
        field.tag = tag
        field.value = text.toCharArray()
        val spans = textViewsIn(field).firstOrNull { it.text.toString() == text }
            ?.let { SpanDump.spansOf(it) }.orEmpty()
        rec.add("link.field", case.id, value.id) {
            put("field", case.field)
            put("tag", tag?.toString() ?: JSONObject.NULL)
            put("spans", SpanDump.json(spans))
        }

        // The platform's own detector, on a view of its own (the mask based call removes existing links)
        val phoneView = TextView(activity).apply { this.text = text }
        @Suppress("DEPRECATION")
        val phoneReturned = Linkify.addLinks(phoneView, Linkify.PHONE_NUMBERS)
        rec.add("link.phoneNumbers", case.id, value.id) {
            put("call", "Linkify.addLinks(PHONE_NUMBERS)")
            put("returned", phoneReturned)
            put("spans", SpanDump.json(SpanDump.spansOf(phoneView)))
        }
        return LinkResult(field, spans)
    }

    /** What the classifier returned for one range of the text. */
    class ClassifierRow(val label: String, val value: String)

    /** Background thread. Returns the rows the screen shows; the full data goes into the records. */
    fun classifier(
        context: Context, case: RqCase, value: RqValue, link: LinkResult, rec: Recorder
    ): List<ClassifierRow> {
        if (Build.VERSION.SDK_INT < 26) {
            rec.add("skipped", case.id, value.id) {
                put("probe", "classifier.*")
                put("reason", "API ${Build.VERSION.SDK_INT} < 26")
            }
            return listOf(ClassifierRow("", "not available before API 26"))
        }
        val text = value.text
        if (text.length > MAX_TEXT) return listOf(ClassifierRow("", "text too long"))
        val classifier = context.getSystemService(TextClassificationManager::class.java).textClassifier
        val rows = ArrayList<ClassifierRow>()

        if (Build.VERSION.SDK_INT >= 28) {
            val result = classifier.generateLinks(TextLinks.Request.Builder(text).build())
            val found = result.links.map { textLink ->
                JSONObject().put("start", textLink.start).put("end", textLink.end)
                    .put("entities", JSONObject().also { entities ->
                        for (index in 0 until textLink.entityCount) {
                            val type = textLink.getEntity(index)
                            entities.put(type, textLink.getConfidenceScore(type).toDouble())
                        }
                    })
            }
            rec.add("classifier.generateLinks", case.id, value.id) {
                put("class", classifier.javaClass.name)
                put("links", jsonArray(found))
            }
            rows.add(ClassifierRow("links", if (found.isEmpty()) "none" else found.joinToString(", ") {
                "${it.getInt("start")}..${it.getInt("end")}"
            }))
        }

        // The range the user would long-press: the tel links, else the first run of digits
        val ranges = link.telSpans.map { it.start to it.end }.ifEmpty {
            Regex("[+0-9][0-9()./ -]*[0-9]").find(text)?.let { listOf(it.range.first to it.range.last + 1) }.orEmpty()
        }
        for ((start, end) in ranges) {
            val middle = start + (end - start) / 2
            val selection = classifier.suggestSelection(TextSelection.Request.Builder(text, middle, middle + 1).build())
            rec.add("classifier.suggestSelection", case.id, value.id) {
                put("at", JSONArray().put(middle).put(middle + 1))
                put("selection", JSONArray().put(selection.selectionStartIndex).put(selection.selectionEndIndex))
                put("selected_text", text.substring(selection.selectionStartIndex, selection.selectionEndIndex))
                put("entities", JSONObject().also { entities ->
                    for (index in 0 until selection.entityCount) {
                        val type = selection.getEntity(index)
                        entities.put(type, selection.getConfidenceScore(type).toDouble())
                    }
                })
            }
            val classification = classifier.classifyText(TextClassification.Request.Builder(text, start, end).build())
            val actions = if (Build.VERSION.SDK_INT >= 28) classification.actions.map { it.title.toString() } else emptyList()
            val entityNames = (0 until classification.entityCount).map { classification.getEntity(it) }
            rec.add("classifier.classifyText", case.id, value.id) {
                put("at", JSONArray().put(start).put(end))
                put("entities", JSONObject().also { entities ->
                    entityNames.forEach { entities.put(it, classification.getConfidenceScore(it).toDouble()) }
                })
                put("actions", JSONArray(actions))
            }
            rows.add(ClassifierRow("$start..$end",
                "selection ${selection.selectionStartIndex}..${selection.selectionEndIndex}\n" +
                        "entity ${entityNames.joinToString().ifEmpty { "none" }}\n" +
                        "actions ${actions.joinToString().ifEmpty { "none" }}"))
        }
        if (ranges.isEmpty()) rows.add(ClassifierRow("", "no number in the text"))
        return rows
    }

    class HandlerRow(val uri: String, val handlers: List<String>, val resolvesTo: String?)

    /** Background thread. Which installed apps can open each distinct tel: target; nothing is started. */
    fun handlers(context: Context, case: RqCase, value: RqValue, link: LinkResult, rec: Recorder): List<HandlerRow> {
        val packageManager = context.packageManager
        return link.telSpans.mapNotNull { it.url }.distinct().map { uri ->
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(uri))
            @Suppress("DEPRECATION")
            val found = packageManager.queryIntentActivities(intent, 0)
            @Suppress("DEPRECATION")
            val resolved = packageManager.resolveActivity(intent, 0)
            rec.add("intent.handlers", case.id, value.id) {
                put("uri", uri)
                put("action", Intent.ACTION_VIEW)
                put("resolves_to", resolved?.activityInfo?.packageName ?: JSONObject.NULL)
                put("handlers", JSONArray().also { array ->
                    found.forEach {
                        array.put(JSONObject().put("package", it.activityInfo.packageName)
                            .put("activity", it.activityInfo.name)
                            .put("label", it.loadLabel(packageManager).toString()))
                    }
                })
            }
            HandlerRow(uri, found.map { it.loadLabel(packageManager).toString() }, resolved?.activityInfo?.packageName)
        }
    }
}
