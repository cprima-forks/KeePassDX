package com.kunzisoft.keepass.view

import android.widget.TextView
import androidx.core.text.util.LinkifyCompat
import java.util.regex.Pattern

/*
 * Spike for upstream issue #1852 (fork issue #6): link an explicit RFC 3966 global `tel:`
 * number, in the URL field only.
 *
 * To remove it: delete this file, SpikeLinkifyTest and the one call in TextFieldView.linkify().
 */

private const val TEL_SCHEME = "tel:"

/**
 * `tel:` followed by `+`, the RFC 3966 visual separators `-` `.` `(` `)` and digits, with at
 * least one digit (RFC 3966 section 3, global-number-digits).
 * No spaces (section 5.1.1). Case-insensitive (section 4).
 */
internal val TEL_PATTERN: Pattern =
    Pattern.compile("tel:\\+[0-9().-]*[0-9][0-9().-]*", Pattern.CASE_INSENSITIVE)

/**
 * Turns each `tel:` number in [view] into a link, only when [fieldTag] is the URL field.
 *
 * Must run after the mask based `LinkifyCompat.addLinks(view, mask)`: that call removes all
 * existing link spans, the pattern based call used here only adds spans.
 */
internal fun spikeLinkifyTel(view: TextView, fieldTag: Any?) {
    if (fieldTag != TemplateAbstractView.FIELD_URL_TAG) return
    // With "tel:" as default scheme, Linkify also rewrites "TEL:" to "tel:" in the link target.
    LinkifyCompat.addLinks(view, TEL_PATTERN, TEL_SCHEME)
}
