package com.kunzisoft.keepass.view

import android.content.Context
import android.text.util.Linkify
import androidx.core.text.util.LinkifyCompat
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import com.kunzisoft.keepass.utils.TEL_LINK_CONFIG
import com.kunzisoft.keepass.utils.LinkedField
import com.kunzisoft.keepass.utils.TelLinkConfig
import com.kunzisoft.keepass.utils.TelLinkScheme
import com.kunzisoft.keepass.utils.TelNumberNotation
import com.kunzisoft.keepass.utils.TelLinkifyUtil.linkifySchemes

/** One input of a flag check: the id of the case it comes from, and the text of its value. */
class FlagInput(val id: String, val input: String) {
    override fun toString() = id
}

/** The value of every code case as the input of a flag check: the flags do not look at `expected`. */
internal fun flagInputs(readFile: (String) -> String): List<FlagInput> {
    val (values, cases) = RequirementCases.load(readFile)
    return cases.filter { it.level == RqLevel.CODE }
        .map { FlagInput(it.id, values.getValue(it.value).text) }
}

/**
 * The checks for the feature flags of the phone number links (TelLinkConfig). The inputs are the
 * values of the code cases (tel-values.json): no phone number is written in this code.
 */
internal object TelLinkFlagChecks {

    /** The shipped values are the owner's decision: tel only, URL field only, RFC 3966 notation. */
    fun shippedValues() {
        assertEquals(setOf(TelLinkScheme.TEL), TEL_LINK_CONFIG.schemes)
        assertEquals(setOf(LinkedField.URL), TEL_LINK_CONFIG.fields)
        assertEquals(setOf(TelNumberNotation.RFC3966), TEL_LINK_CONFIG.notations)
    }

    /** RFC 3966 is the base: a configuration without it is refused. */
    fun rfc3966IsRequired() {
        try {
            TelLinkConfig(notations = emptySet())
            fail("a configuration without the RFC3966 notation was accepted")
        } catch (expected: IllegalArgumentException) {
            // the refusal is the expected behaviour
        }
    }

    /** What TextFieldView.linkify() does for a field, with the default argument for the configuration. */
    private fun linksWithDefaultArgument(context: Context, input: String, field: String): List<TelLink> {
        val view = TelLinkCaseChecks.viewWith(context, input)
        LinkifyCompat.addLinks(view, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        view.linkifySchemes(TelLinkCases.tagOf(field))
        return TelLinkCaseChecks.linksOf(view)
    }

    /** The call that TextFieldView makes (no configuration given) is the shipped configuration. */
    fun defaultArgumentIsShippedConfiguration(case: FlagInput, context: Context) {
        TelLinkCases.FIELDS.forEach { field ->
            assertEquals(
                "[${case.id}] field '$field': default argument against the shipped configuration",
                TelLinkCaseChecks.linksIn(context, case.input, field, config = TEL_LINK_CONFIG),
                linksWithDefaultArgument(context, case.input, field)
            )
        }
    }

    /** Without the tel scheme no tel link appears in any field; the other links are untouched. */
    fun noSchemesNoTelLink(case: FlagInput, context: Context) {
        val none = TelLinkConfig(schemes = emptySet())
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

    /** The fields that [LinkedField] names; the password and a view without a tag are not among them. */
    private val NAMED_FIELDS = listOf(TelLinkCases.URL_FIELD, "notes", "custom", "username", "title")

    /**
     * With every named field in the set, each named field behaves as the URL field does with the
     * shipped configuration; the password and a view without a tag still get no tel link.
     */
    fun namedFieldsBehaveAsUrlField(case: FlagInput, context: Context) {
        val everywhere = TelLinkConfig(fields = LinkedField.values().toSet())
        val expected = TelLinkCaseChecks.linksIn(context, case.input, TelLinkCases.URL_FIELD)
        TelLinkCases.FIELDS.forEach { field ->
            val links = TelLinkCaseChecks.linksIn(context, case.input, field, config = everywhere)
            if (field in NAMED_FIELDS) {
                assertEquals("[${case.id}] field '$field' with all named fields", expected, links)
            } else {
                assertEquals(
                    "[${case.id}] field '$field' is not a named field",
                    emptyList<TelLink>(),
                    links.filter(TelLinkCaseChecks::isTel)
                )
            }
        }
    }

    /** An empty set of fields is the fuse: no field gets a tel link. */
    fun emptyFieldsNoTelLink(case: FlagInput, context: Context) {
        val fuse = TelLinkConfig(fields = emptySet())
        TelLinkCases.FIELDS.forEach { field ->
            assertEquals(
                "[${case.id}] field '$field' with no fields",
                emptyList<TelLink>(),
                TelLinkCaseChecks.linksIn(context, case.input, field, config = fuse)
                    .filter(TelLinkCaseChecks::isTel)
            )
        }
    }

    /**
     * The check must not be vacuous: over all cases, the set changes the links of at least one
     * field other than the URL field.
     */
    fun namedFieldsHaveAnEffect(cases: List<FlagInput>, context: Context) {
        val everywhere = TelLinkConfig(fields = LinkedField.values().toSet())
        val changed = cases.sumOf { case ->
            NAMED_FIELDS.filter { it != TelLinkCases.URL_FIELD }.count { field ->
                TelLinkCaseChecks.linksIn(context, case.input, field) !=
                        TelLinkCaseChecks.linksIn(context, case.input, field, config = everywhere)
            }
        }
        assertTrue("the set of fields changed no field of any case", changed > 0)
    }
}
