package com.kunzisoft.keepass.view

import android.content.Context
import android.text.method.LinkMovementMethod
import android.text.util.Linkify
import androidx.core.text.util.LinkifyCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue

/**
 * The checks for a case of tel-cases/<topic>.json at the code level.
 *
 * The verdict is the comparison of `expected` with the actual links. `current`, `legacy` and the
 * notes of a case never influence it.
 */
object RequirementCaseChecks {

    /** Loads the case [caseId] with its value and checks it. */
    internal fun run(
        caseId: String,
        readFile: (String) -> String,
        context: Context,
        config: PhoneLinkConfig = PHONE_LINK_CONFIG
    ) {
        val (values, cases) = RequirementCases.load(readFile)
        val case = cases.first { it.id == caseId }
        check(case, values.getValue(case.value), context, config)
    }

    internal fun check(
        case: RqCase,
        value: RqValue,
        context: Context,
        config: PhoneLinkConfig = PHONE_LINK_CONFIG
    ) {
        require(case.level == RqLevel.CODE) { "${case.id} is not a code case" }
        require(!config.allFields) { "allFields is checked in PhoneLinkFlagChecks" }
        val expected = checkNotNull(case.links) { "${case.id} has no expected links" }
        fun message(what: String) = "[${case.id} ${case.requirements.joinToString()}] $what"

        val started = System.nanoTime()
        val actual = TelLinkCaseChecks.linksIn(context, value.text, case.field, config = config)
        val elapsedMs = (System.nanoTime() - started) / 1_000_000

        // The verdict: the complete list of links, in text order
        assertEquals(message("links"), expected, actual)

        // A case with a time limit must finish within it
        case.timeLimitMs?.let { assertTrue(message("took $elapsedMs ms"), elapsedMs < it) }

        // Linkifying again and again changes nothing (TextFieldView.linkify() runs on every value)
        assertEquals(
            message("links after three runs"),
            actual,
            TelLinkCaseChecks.linksIn(context, value.text, case.field, times = 3, config = config)
        )

        actual.filter(TelLinkCaseChecks::isTel).forEach { link ->
            // The scheme is never part of the linked text: a long-press selects the whole link
            assertFalse(
                message("linked text '${link.text}' starts with its scheme"),
                link.text.startsWith(TEL_SCHEME, ignoreCase = true)
            )
            // The target holds no white space and no control character
            assertFalse(
                message("target '${link.target}' holds white space or a control character"),
                link.target.any { it.isWhitespace() || it.isISOControl() }
            )
        }

        // The view reacts to taps as soon as it holds a link
        if (actual.isNotEmpty()) {
            assertTrue(
                message("link movement method"),
                linkified(context, value.text, case.field, config).movementMethod is LinkMovementMethod
            )
        }

        // Only the URL field gets a tel link: the same value in every other field
        if (case.field == TelLinkCases.URL_FIELD && expected.any(TelLinkCaseChecks::isTel)) {
            TelLinkCases.FIELDS.filter { it != TelLinkCases.URL_FIELD }.forEach { field ->
                assertEquals(
                    message("no tel link in the field '$field'"),
                    emptyList<TelLink>(),
                    TelLinkCaseChecks.linksIn(context, value.text, field, config = config)
                        .filter(TelLinkCaseChecks::isTel)
                )
            }
        }
    }

    /** The two calls TextFieldView.linkify() makes for a field: the mask based one, then the spike. */
    private fun linkified(context: Context, text: String, field: String, config: PhoneLinkConfig) =
        TelLinkCaseChecks.viewWith(context, text).also {
            LinkifyCompat.addLinks(it, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
            spikeLinkifyTel(it, TelLinkCases.tagOf(field), config)
        }
}
