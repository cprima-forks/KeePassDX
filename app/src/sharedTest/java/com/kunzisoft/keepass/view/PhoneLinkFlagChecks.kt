package com.kunzisoft.keepass.view

import android.content.Context
import android.text.util.Linkify
import androidx.core.text.util.LinkifyCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail

/**
 * The checks for the feature flags of the phone number links (PhoneLinkConfig). The inputs come from
 * the case file: no phone number is written in this code.
 */
internal object PhoneLinkFlagChecks {

    /** The shipped values are the owner's decision: tel only, URL field only, RFC 3966 notation. */
    fun shippedValues() {
        assertEquals(setOf(PhoneLinkScheme.TEL), PHONE_LINK_CONFIG.schemes)
        assertEquals(false, PHONE_LINK_CONFIG.allFields)
        assertEquals(setOf(PhoneNumberNotation.RFC3966), PHONE_LINK_CONFIG.notations)
    }

    /** RFC 3966 is the base: a configuration without it is refused. */
    fun rfc3966IsRequired() {
        try {
            PhoneLinkConfig(notations = emptySet())
            fail("a configuration without the RFC3966 notation was accepted")
        } catch (expected: IllegalArgumentException) {
            // the refusal is the expected behaviour
        }
    }

    /** What TextFieldView.linkify() does for a field, with the default argument for the configuration. */
    private fun linksWithDefaultArgument(context: Context, input: String, field: String): List<TelLink> {
        val view = TelLinkCaseChecks.viewWith(context, input)
        LinkifyCompat.addLinks(view, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        spikeLinkifyTel(view, TelLinkCases.tagOf(field))
        return TelLinkCaseChecks.linksOf(view)
    }

    /** The call that TextFieldView makes (no configuration given) is the shipped configuration. */
    fun defaultArgumentIsShippedConfiguration(case: TelLinkCase, context: Context) {
        TelLinkCases.FIELDS.forEach { field ->
            assertEquals(
                "[${case.id}] field '$field': default argument against the shipped configuration",
                TelLinkCaseChecks.linksIn(context, case.input, field, config = PHONE_LINK_CONFIG),
                linksWithDefaultArgument(context, case.input, field)
            )
        }
    }

    /** Without the tel scheme no tel link appears in any field; the other links are untouched. */
    fun noSchemesNoTelLink(case: TelLinkCase, context: Context) {
        val none = PhoneLinkConfig(schemes = emptySet())
        TelLinkCases.FIELDS.forEach { field ->
            val links = TelLinkCaseChecks.linksIn(context, case.input, field, config = none)
            assertEquals(
                "[${case.id}] field '$field': tel links without the tel scheme",
                emptyList<TelLink>(),
                links.filter(TelLinkCaseChecks::isTel)
            )
            assertEquals(
                "[${case.id}] field '$field': the other links without the tel scheme",
                TelLinkCaseChecks.linksIn(context, case.input, field).filterNot(TelLinkCaseChecks::isTel),
                links
            )
        }
    }

    /** With allFields every field behaves as the URL field does with the shipped configuration. */
    fun allFieldsBehaveAsUrlField(case: TelLinkCase, context: Context) {
        val everywhere = PhoneLinkConfig(allFields = true)
        val expected = TelLinkCaseChecks.linksIn(context, case.input, TelLinkCases.URL_FIELD)
        TelLinkCases.FIELDS.forEach { field ->
            assertEquals(
                "[${case.id}] field '$field' with allFields",
                expected,
                TelLinkCaseChecks.linksIn(context, case.input, field, config = everywhere)
            )
        }
    }

    /**
     * The allFields check must not be vacuous: over all cases, the flag changes the links of at
     * least one field other than the URL field (and of none in the URL field, see above).
     */
    fun allFieldsHasAnEffect(cases: List<TelLinkCase>, context: Context) {
        val everywhere = PhoneLinkConfig(allFields = true)
        val changed = cases.sumOf { case ->
            TelLinkCases.FIELDS.filter { it != TelLinkCases.URL_FIELD }.count { field ->
                TelLinkCaseChecks.linksIn(context, case.input, field) !=
                        TelLinkCaseChecks.linksIn(context, case.input, field, config = everywhere)
            }
        }
        assertTrue("allFields changed no field of any case", changed > 0)
    }
}
