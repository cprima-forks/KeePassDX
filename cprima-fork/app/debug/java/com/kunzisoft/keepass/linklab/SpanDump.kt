package com.kunzisoft.keepass.linklab

import android.text.Spanned
import android.text.style.URLSpan
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject

/** The spans of a text, as the platform returns them. */
object SpanDump {

    class Span(
        val kind: String,
        val start: Int,
        val end: Int,
        val flags: Int,
        val text: String,
        val url: String?
    )

    /**
     * All spans on the text of [view], sorted by start, end and class. The platform's own bookkeeping spans are
     * left out: the editor's (android.widget) and the markers of the text selection (android.text.Selection).
     */
    fun spansOf(view: TextView): List<Span> {
        val text = view.text as? Spanned ?: return emptyList()
        return text.getSpans(0, text.length, Any::class.java)
            .filterNot {
                val name = it.javaClass.name
                name.startsWith("android.widget.") || name.startsWith("android.text.Selection")
            }
            .map { span ->
                val start = text.getSpanStart(span)
                val end = text.getSpanEnd(span)
                Span(
                    kind = span.javaClass.simpleName,
                    start = start,
                    end = end,
                    flags = text.getSpanFlags(span),
                    text = text.subSequence(start, end).toString(),
                    url = (span as? URLSpan)?.url
                )
            }
            .sortedWith(compareBy({ it.start }, { it.end }, { it.kind }))
    }

    fun json(spans: List<Span>): JSONArray = JSONArray().also { array ->
        spans.forEach { span ->
            array.put(
                JSONObject()
                    .put("class", span.kind)
                    .put("start", span.start)
                    .put("end", span.end)
                    .put("flags", span.flags)
                    .put("text", span.text)
                    .put("url", span.url ?: JSONObject.NULL)
            )
        }
    }
}
