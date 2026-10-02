package com.kunzisoft.keepass.view

import android.content.Context
import android.text.Spanned
import android.text.method.LinkMovementMethod
import android.text.style.URLSpan
import android.text.util.Linkify
import android.widget.TextView
import androidx.core.text.util.LinkifyCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue

/** The checks applied to every case of tel-link-cases.json. */
object TelLinkCaseChecks {

    /** The two calls TextFieldView.linkify() makes for a field: the mask based one, then the spike. */
    private fun linkify(view: TextView, tag: Any?) {
        LinkifyCompat.addLinks(view, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        spikeLinkifyTel(view, tag)
    }

    private fun viewWith(context: Context, input: String) =
        TextView(context).apply { text = input }

    /** Linked text and link target of every link, in text order. */
    private fun linksOf(view: TextView): List<TelLink> {
        val spanned = view.text as? Spanned ?: return emptyList()
        return spanned.getSpans(0, spanned.length, URLSpan::class.java)
            .sortedWith(compareBy({ spanned.getSpanStart(it) }, { spanned.getSpanEnd(it) }))
            .map { span ->
                TelLink(
                    spanned.subSequence(spanned.getSpanStart(span), spanned.getSpanEnd(span)).toString(),
                    span.url
                )
            }
    }

    private fun isTel(link: TelLink) = link.target.startsWith(TEL_SCHEME, ignoreCase = true)

    private fun linksIn(context: Context, input: String, field: String, times: Int = 1): List<TelLink> {
        val view = viewWith(context, input)
        repeat(times) { linkify(view, TelLinkCases.tagOf(field)) }
        return linksOf(view)
    }

    fun check(case: TelLinkCase, context: Context) {
        fun message(what: String) = "[${case.id}] $what (${case.note})"

        val once = linksIn(context, case.input, case.field)

        // 1. The result for the field of the case
        if (case.field == TelLinkCases.URL_FIELD && case.works) {
            assertEquals(message("links"), case.links, once)
        } else {
            assertEquals(message("no tel link"), emptyList<TelLink>(), once.filter(::isTel))
            assertEquals(message("other links"), case.links.filterNot(::isTel), once.filterNot(::isTel))
        }

        // 2. Linkifying again and again changes nothing (TextFieldView.linkify() runs on every value)
        assertEquals(
            message("links after three runs"),
            once,
            linksIn(context, case.input, case.field, times = 3)
        )

        // 3. The scheme is never part of the linked text: a long-press selects the whole link
        once.filter(::isTel).forEach { link ->
            val scheme = link.target.substringBefore(':') + ':'
            assertFalse(
                message("linked text '${link.text}' starts with its scheme"),
                link.text.startsWith(scheme, ignoreCase = true)
            )
        }

        // 4. The view reacts to taps as soon as it holds a link
        if (once.isNotEmpty()) {
            val view = viewWith(context, case.input)
            linkify(view, TelLinkCases.tagOf(case.field))
            assertTrue(message("link movement method"), view.movementMethod is LinkMovementMethod)
        }

        // 5. Only the URL field gets a tel link: the same input in every other field
        if (case.works) {
            TelLinkCases.FIELDS.filter { it != TelLinkCases.URL_FIELD }.forEach { field ->
                val links = linksIn(context, case.input, field)
                assertEquals(
                    message("no tel link in the field '$field'"),
                    emptyList<TelLink>(),
                    links.filter(::isTel)
                )
                assertEquals(
                    message("other links in the field '$field'"),
                    case.links.filterNot(::isTel),
                    links.filterNot(::isTel)
                )
            }
        }
    }
}
