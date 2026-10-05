package com.kunzisoft.keepass.utils

import android.graphics.Typeface
import android.text.Spanned
import android.text.style.BulletSpan
import android.text.style.DynamicDrawableSpan
import android.text.style.QuoteSpan
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
import android.text.style.TypefaceSpan
import android.text.style.URLSpan
import kotlin.math.abs

/**
 * The spans of a rendered text as neutral kinds, so that the tests and the MarkdownLab read the same thing on every
 * Android version: `bold`, `italic`, `heading:N`, `code`, `bullet`, `quote`, `rule`, `link:<url>`, `image`.
 * Anything else is reported as `other:<class>`, so that an unexpected span is visible and not dropped.
 */
object MarkdownSpans {

    const val IMAGE = "image"

    fun spansOf(text: Spanned): List<MdSpan> {
        val all = text.getSpans(0, text.length, Any::class.java)
        val headings = all.filterIsInstance<RelativeSizeSpan>().map { text.getSpanStart(it) to text.getSpanEnd(it) }
        val result = mutableListOf<MdSpan>()
        for (span in all) {
            val start = text.getSpanStart(span)
            val end = text.getSpanEnd(span)
            when (span) {
                is RelativeSizeSpan -> {
                    val level = MarkdownRenderer.HEADING_SIZES.indexOfFirst { abs(it - span.sizeChange) < 0.001f }
                    result += MdSpan(if (level >= 0) "heading:${level + 1}" else "size:${span.sizeChange}", start, end)
                }
                is StyleSpan -> {
                    // A heading is also bold: the bold span of the same range belongs to the heading
                    val ofHeading = (start to end) in headings
                    if (span.style and Typeface.BOLD != 0 && !(ofHeading && span.style == Typeface.BOLD)) {
                        result += MdSpan("bold", start, end)
                    }
                    if (span.style and Typeface.ITALIC != 0) result += MdSpan("italic", start, end)
                }
                is TypefaceSpan -> result += MdSpan(if (span.family == "monospace") "code" else "typeface:${span.family}", start, end)
                is BulletSpan -> result += MdSpan("bullet", start, end)
                is QuoteSpan -> result += MdSpan("quote", start, end)
                is RuleSpan -> result += MdSpan("rule", start, end)
                is URLSpan -> result += MdSpan("link:${span.url}", start, end)
                is DynamicDrawableSpan -> result += MdSpan(IMAGE, start, end)
                else -> result += MdSpan("other:${span.javaClass.simpleName}", start, end)
            }
        }
        return result.sortedWith(compareBy({ it.start }, { it.end }, { it.kind }))
    }
}
