/*
 * Copyright 2026 Christian Prior-Mamulyan.
 *
 * This file is part of KeePassDX.
 *
 *  KeePassDX is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  KeePassDX is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with KeePassDX.  If not, see <http://www.gnu.org/licenses/>.
 *
 */
package com.kunzisoft.keepass.utils

import android.text.Spanned
import android.text.style.URLSpan
import android.text.util.Linkify
import android.widget.TextView
import androidx.core.text.util.LinkifyCompat
import com.kunzisoft.keepass.view.TemplateAbstractView
import java.util.regex.Pattern


/*
 * Links an explicit RFC 3966 global `tel:` number (issue #1852), in the URL field only.
 *
 * To add another scheme, for example `sms:`: add a value to [TelLinkScheme], add its pattern and
 * match filter next to [TelLinkifyUtil.TEL_PATTERN], and call it from [TelLinkifyUtil.linkifySchemes].
 * The call in TextFieldView does not change. With a second scheme, give each scheme its own util
 * (SmsLinkifyUtil) and move the flags and linkifySchemes() to a SchemeLinkifyUtil.
 */

/** A scheme whose numbers are linked. Only the implemented values exist. */
enum class TelLinkScheme { TEL }

/** A way of writing a number that is accepted. Only the implemented values exist. */
enum class TelNumberNotation {
    /** RFC 3966: `+`, digits and the visual separators `-` `.` `(` `)`; a space ends the number */
    RFC3966
}

/** A field of an entry in which numbers can be linked. The password and the expiry are not listed. */
enum class LinkedField { TITLE, USER_NAME, URL, NOTES, CUSTOM }

/**
 * The flags of the phone number links, as one value so that every configuration can be tested.
 *
 * @param schemes the schemes whose numbers are linked
 * @param fields the fields in which numbers are linked, empty: nowhere
 * @param notations the accepted notations, [TelNumberNotation.RFC3966] is the base and required
 */
class TelLinkConfig(
    val schemes: Set<TelLinkScheme> = setOf(TelLinkScheme.TEL),
    val fields: Set<LinkedField> = setOf(LinkedField.URL),
    val notations: Set<TelNumberNotation> = setOf(TelNumberNotation.RFC3966)
) {
    init {
        require(TelNumberNotation.RFC3966 in notations) { "the RFC3966 notation is required" }
    }
}

/** The configuration the app uses: tel numbers, URL field only, RFC 3966 notation */
val TEL_LINK_CONFIG = TelLinkConfig()


object TelLinkifyUtil {

    /** Scheme that Linkify prepends to the matched number to build the link target */
    const val TEL_SCHEME = "tel:"

    /**
     * The number of a `tel:` value: `+`, digits and the visual separators `-` `.` `(` `)`, with at
     * least one digit (RFC 3966 section 3), no space. `tel:` is a lookbehind and not part of the
     * match, so the link, the long-press selection and the Call action contain only the number.
     */
    val TEL_PATTERN: Pattern =
        Pattern.compile("(?<=tel:)\\+[0-9().-]*[0-9][0-9().-]*", Pattern.CASE_INSENSITIVE)

    /**
     * Rejects a match of [TEL_PATTERN] when a letter (or a combining mark) stands directly before
     * `tel:`, as in `Hotel:+49`, because `tel:` is then the end of a word, and when the match lies
     * inside another link, as in `https://example.com/tel:+49`.
     */
    val TEL_MATCH_FILTER = Linkify.MatchFilter { text, start, end ->
        val prefixStart = start - TEL_SCHEME.length
        if (prefixStart > 0) {
            // By code point, so letters outside the Basic Multilingual Plane count too
            val previous = Character.codePointBefore(text, prefixStart)
            if (Character.isLetter(previous)
                || Character.getType(previous) == Character.NON_SPACING_MARK.toInt()) {
                return@MatchFilter false
            }
        }
        if (text is Spanned && text.getSpans(start, end, URLSpan::class.java).isNotEmpty()) {
            return@MatchFilter false
        }
        true
    }

    /** The field of a view tag, null for the password, the expiry and a view without a known tag */
    private fun linkedFieldOf(fieldTag: Any?): LinkedField? = when (fieldTag) {
        TemplateAbstractView.FIELD_TITLE_TAG -> LinkedField.TITLE
        TemplateAbstractView.FIELD_USERNAME_TAG -> LinkedField.USER_NAME
        TemplateAbstractView.FIELD_URL_TAG -> LinkedField.URL
        TemplateAbstractView.FIELD_NOTES_TAG -> LinkedField.NOTES
        TemplateAbstractView.FIELD_CUSTOM_TAG -> LinkedField.CUSTOM
        else -> null
    }

    /**
     * Turns the numbers of the enabled schemes into links, in the fields of
     * [TelLinkConfig.fields]. Must run after LinkifyCompat.addLinks(view, mask): that call
     * removes all link spans, this one only adds, and [TEL_MATCH_FILTER] needs the web and e-mail
     * links to be there.
     */
    fun TextView.linkifySchemes(fieldTag: Any?,
                                config: TelLinkConfig = TEL_LINK_CONFIG) {
        if (linkedFieldOf(fieldTag) !in config.fields)
            return
        if (TelLinkScheme.TEL in config.schemes) {
            LinkifyCompat.addLinks(this, TEL_PATTERN, TEL_SCHEME, TEL_MATCH_FILTER, null)
        }
    }
}
