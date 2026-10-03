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

    /** A generated input must be handled within this time, so a slow pattern shows up as a failure. */
    private const val TIME_LIMIT_MS = 2000L

    /** The two calls TextFieldView.linkify() makes for a field: the mask based one, then the spike. */
    private fun linkify(view: TextView, tag: Any?, config: PhoneLinkConfig) {
        LinkifyCompat.addLinks(view, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        spikeLinkifyTel(view, tag, config)
    }

    internal fun viewWith(context: Context, input: String) =
        TextView(context).apply { text = input }

    /** Linked text and link target of every link, in text order. */
    internal fun linksOf(view: TextView): List<TelLink> {
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

    internal fun isTel(link: TelLink) = link.target.startsWith(TEL_SCHEME, ignoreCase = true)

    internal fun linksIn(
        context: Context,
        input: String,
        field: String,
        times: Int = 1,
        config: PhoneLinkConfig = PHONE_LINK_CONFIG
    ): List<TelLink> {
        val view = viewWith(context, input)
        repeat(times) { linkify(view, TelLinkCases.tagOf(field), config) }
        return linksOf(view)
    }

    /**
     * The checks for [config]. They state the decided behaviour of the URL field only: a configuration
     * that links in every field is checked in [PhoneLinkFlagChecks].
     */
    internal fun check(case: TelLinkCase, context: Context, config: PhoneLinkConfig = PHONE_LINK_CONFIG) {
        require(!config.allFields) { "allFields is checked in PhoneLinkFlagChecks" }
        fun message(what: String) = "[${case.id}] $what (${case.note})"

        val started = System.nanoTime()
        val once = linksIn(context, case.input, case.field, config = config)
        val elapsedMs = (System.nanoTime() - started) / 1_000_000

        // 0. A generated input is long; it must not take long
        if (case.generated) {
            assertTrue(message("took ${elapsedMs} ms"), elapsedMs < TIME_LIMIT_MS)
        }

        // 1. The result for the field of the case
        if (case.field == TelLinkCases.URL_FIELD && case.kind != TelLinkKind.FAILS) {
            assertEquals(message("links"), case.links, once)
        } else {
            assertEquals(message("no tel link"), emptyList<TelLink>(), once.filter(::isTel))
            assertEquals(message("other links"), case.links.filterNot(::isTel), once.filterNot(::isTel))
        }

        // 2. Linkifying again and again changes nothing (TextFieldView.linkify() runs on every value)
        assertEquals(
            message("links after three runs"),
            once,
            linksIn(context, case.input, case.field, times = 3, config = config)
        )

        once.filter(::isTel).forEach { link ->
            // 3. The scheme is never part of the linked text: a long-press selects the whole link
            val scheme = link.target.substringBefore(':') + ':'
            assertFalse(
                message("linked text '${link.text}' starts with its scheme"),
                link.text.startsWith(scheme, ignoreCase = true)
            )
            // 4. The target is exactly the scheme and the linked text
            assertEquals(message("target of '${link.text}'"), TEL_SCHEME + link.text, link.target)
            // 5. The target holds no white space and no control character
            assertFalse(
                message("target '${link.target}' holds white space or a control character"),
                link.target.any { it.isWhitespace() || it.isISOControl() }
            )
        }

        // 6. The view reacts to taps as soon as it holds a link
        if (once.isNotEmpty()) {
            val view = viewWith(context, case.input)
            linkify(view, TelLinkCases.tagOf(case.field), config)
            assertTrue(message("link movement method"), view.movementMethod is LinkMovementMethod)
        }

        // 7. Only the URL field gets a tel link: the same input in every other field
        if (case.kind != TelLinkKind.FAILS) {
            TelLinkCases.FIELDS.filter { it != TelLinkCases.URL_FIELD }.forEach { field ->
                val links = linksIn(context, case.input, field, config = config)
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
