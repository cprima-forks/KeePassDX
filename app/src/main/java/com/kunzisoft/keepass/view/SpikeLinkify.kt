package com.kunzisoft.keepass.view

import android.widget.TextView
import androidx.core.text.util.LinkifyCompat
import java.util.regex.Pattern

/*
 * Spike for upstream issue #1852 (fork issues #6 and #9): link an explicit RFC 3966 global `tel:`
 * number, in the URL field only.
 *
 * The link covers only the number, not the `tel:` prefix, so that a long-press selects just the
 * number and the selection toolbar's Call action gives the dialer the number without the prefix.
 * (Android selects a whole link span on a long-press, see Editor.selectCurrentWord().)
 *
 * To remove it: delete this file, the test sources under src/sharedTest, SpikeLinkifyCasesTest,
 * SpikeLinkifyCasesInstrumentedTest, the sourceSets lines for them in app/build.gradle.kts and
 * the one call in TextFieldView.linkify().
 */

/** Default scheme that Linkify prepends to the matched number to build the link target. */
internal const val TEL_SCHEME = "tel:"

/**
 * The number of an explicit `tel:` value: `+`, the RFC 3966 visual separators `-` `.` `(` `)` and
 * digits, with at least one digit (RFC 3966 section 3, global-number-digits). No spaces (section
 * 5.1.1). `tel:` must stand directly before the number (case-insensitive, section 4), but it is a
 * lookbehind and not part of the match: the link span, a long-press selection and the Call action
 * therefore contain only the number.
 */
internal val TEL_PATTERN: Pattern =
    Pattern.compile("(?<=tel:)\\+[0-9().-]*[0-9][0-9().-]*", Pattern.CASE_INSENSITIVE)

/**
 * Turns the number of each `tel:` value in [view] into a link, only when [fieldTag] is the URL
 * field.
 *
 * Must run after the mask based `LinkifyCompat.addLinks(view, mask)`: that call removes all
 * existing link spans, the pattern based call used here only adds spans.
 */
internal fun spikeLinkifyTel(view: TextView, fieldTag: Any?) {
    if (fieldTag != TemplateAbstractView.FIELD_URL_TAG) return
    // The span covers only the number. Linkify prepends the default scheme (in lower case), so
    // the link target is always "tel:+...".
    LinkifyCompat.addLinks(view, TEL_PATTERN, TEL_SCHEME)
}
