package com.kunzisoft.keepass.view

import android.content.Context
import android.text.Spanned
import android.text.style.URLSpan
import android.text.util.Linkify
import android.widget.TextView
import androidx.core.text.util.LinkifyCompat

/** The helpers that run the linkify of a field on a text and read the links back. */
object TelLinkCaseChecks {

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
}
