package com.kunzisoft.keepass.view

import android.text.Spanned
import android.text.style.URLSpan
import android.text.util.Linkify
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
 * To remove it: delete this file, the test sources and the case files under cprima-fork/app/sharedTest,
 * RequirementCasesTest, RequirementCasesKnownDefectsTest, RequirementCaseFilesTest,
 * RequirementCasesInstrumentedTest, RequirementCasesKnownDefectsInstrumentedTest,
 * SpikeLinkifyFuzzTest, SpikeLinkifyFuzzInstrumentedTest, PhoneLinkFlagsTest,
 * PhoneLinkFlagsInstrumentedTest, PhoneLinkConfigTest, PhoneLinkConfigInstrumentedTest, the sourceSets
 * and test lines for them in app/build.gradle.kts and the one call in TextFieldView.linkify().
 */

/** A scheme whose numbers are linked. Only the values that are implemented exist. */
internal enum class PhoneLinkScheme { TEL }

/** A way of writing a number that is accepted. Only the values that are implemented exist. */
internal enum class PhoneNumberNotation {
    /** RFC 3966: `+`, digits and the visual separators `-` `.` `(` `)`; a space ends the number. */
    RFC3966
}

/**
 * The feature flags of the phone number links, as one value so that a test can check every
 * configuration without rebuilding the app. The shipped values are [PHONE_LINK_CONFIG].
 *
 * @param schemes the schemes whose numbers are linked
 * @param allFields link in every text field; false: only in the URL field
 * @param notations the accepted notations; [PhoneNumberNotation.RFC3966] is the base and required
 */
internal class PhoneLinkConfig(
    val schemes: Set<PhoneLinkScheme> = setOf(PhoneLinkScheme.TEL),
    val allFields: Boolean = false,
    val notations: Set<PhoneNumberNotation> = setOf(PhoneNumberNotation.RFC3966)
) {
    init {
        require(PhoneNumberNotation.RFC3966 in notations) { "the RFC3966 notation is required" }
    }
}

/** The configuration the app uses: tel numbers, URL field only, RFC 3966 notation. */
internal val PHONE_LINK_CONFIG = PhoneLinkConfig()

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
 * Decides for each match of [TEL_PATTERN] whether it becomes a link. Linkify passes the whole text
 * and the offsets of the number; the `tel:` prefix stands directly before [start].
 *
 * Rejects a match
 * - when a letter of any script stands directly before the prefix (`Hotel:+49`, `Titel:+1`,
 *   `xtel:+49`): the prefix is then the end of a longer word, not a prefix. A combining mark
 *   counts as part of the letter before it. The text is read by code point, so letters outside
 *   the Basic Multilingual Plane count too.
 * - when it lies inside another link (`https://example.com/tel:+49`): the pattern based
 *   `addLinks` does not remove overlapping links, only the mask based one does.
 */
internal val TEL_MATCH_FILTER = Linkify.MatchFilter { text, start, end ->
    val prefixStart = start - TEL_SCHEME.length
    if (prefixStart > 0) {
        val previous = Character.codePointBefore(text, prefixStart)
        if (Character.isLetter(previous) ||
            Character.getType(previous) == Character.NON_SPACING_MARK.toInt()
        ) {
            return@MatchFilter false
        }
    }
    if (text is Spanned && text.getSpans(start, end, URLSpan::class.java).isNotEmpty()) {
        return@MatchFilter false
    }
    true
}

/**
 * Turns the number of each `tel:` value in [view] into a link, as [config] says: nothing when the
 * tel scheme is off, and in the URL field only unless [PhoneLinkConfig.allFields] is set.
 *
 * Must run after the mask based `LinkifyCompat.addLinks(view, mask)`: that call removes all
 * existing link spans, the pattern based call used here only adds spans, and [TEL_MATCH_FILTER]
 * needs the web and e-mail links to be there already.
 */
internal fun spikeLinkifyTel(view: TextView, fieldTag: Any?, config: PhoneLinkConfig = PHONE_LINK_CONFIG) {
    if (PhoneLinkScheme.TEL !in config.schemes) return
    if (!config.allFields && fieldTag != TemplateAbstractView.FIELD_URL_TAG) return
    // The span covers only the number. Linkify prepends the default scheme (in lower case), so
    // the link target is always "tel:+...".
    LinkifyCompat.addLinks(view, TEL_PATTERN, TEL_SCHEME, TEL_MATCH_FILTER, null)
}
