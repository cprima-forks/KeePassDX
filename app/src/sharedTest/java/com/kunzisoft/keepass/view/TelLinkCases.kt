package com.kunzisoft.keepass.view

import org.json.JSONArray
import org.json.JSONObject

/** A link as the user sees it: the linked text and the target it opens. */
data class TelLink(val text: String, val target: String)

/** What a case of tel-link-cases.json states. */
enum class TelLinkKind {
    /** Decided behaviour: [TelLinkCase.links] is the complete list of links expected. */
    WORKS,

    /** Decided behaviour: no tel link is expected. */
    FAILS,

    /**
     * Behaviour seen in a test and not decided yet: [TelLinkCase.links] is the complete list that the
     * code gives today (empty for no link). A decision may change the expectation.
     */
    OBSERVED
}

/** One case of tel-link-cases.json. */
class TelLinkCase(
    val id: String,
    val kind: TelLinkKind,
    val field: String,
    val input: String,
    /** True when the input was built from a repeated unit, to keep the file small. */
    val generated: Boolean,
    val links: List<TelLink>,
    /** The decision this case verifies or waits for, empty if none. */
    val decision: String,
    val note: String
) {
    // Used by the test runners as the name of the test
    override fun toString() = id
}

/** Reads the cases of the file tel-link-cases.json (shared by the unit and the instrumented test). */
object TelLinkCases {

    const val FILE_NAME = "tel-link-cases.json"

    const val URL_FIELD = "url"
    val FIELDS = listOf(URL_FIELD, "notes", "custom", "username", "password", "title", "unset")

    private val ID_REGEX = Regex("\"id\"\\s*:\\s*\"([^\"]+)\"")

    /** The view tag of a field name, null for a field without tag. */
    fun tagOf(field: String): Any? = when (field) {
        URL_FIELD -> TemplateAbstractView.FIELD_URL_TAG
        "notes" -> TemplateAbstractView.FIELD_NOTES_TAG
        "custom" -> TemplateAbstractView.FIELD_CUSTOM_TAG
        "username" -> TemplateAbstractView.FIELD_USERNAME_TAG
        "password" -> TemplateAbstractView.FIELD_PASSWORD_TAG
        "title" -> TemplateAbstractView.FIELD_TITLE_TAG
        "unset" -> null
        else -> throw IllegalArgumentException("Unknown field in the case file: $field")
    }

    /**
     * Only the case ids, found without a JSON parser. The Robolectric runner reads its parameters
     * outside the sandbox, where org.json is not the real implementation.
     */
    fun ids(json: String): List<String> =
        ID_REGEX.findAll(json).map { it.groupValues[1] }.toList()

    fun parse(json: String): List<TelLinkCase> {
        val root = JSONObject(json)
        return parseList(root.getJSONArray("works"), TelLinkKind.WORKS) +
                parseList(root.getJSONArray("fails"), TelLinkKind.FAILS) +
                parseList(root.optJSONArray("observed") ?: JSONArray(), TelLinkKind.OBSERVED)
    }

    private fun parseList(array: JSONArray, kind: TelLinkKind): List<TelLinkCase> =
        (0 until array.length()).map { index ->
            val case = array.getJSONObject(index)
            val links = case.optJSONArray("links")
            val generated = case.optJSONObject("generated")
            TelLinkCase(
                id = case.getString("id"),
                kind = kind,
                field = case.optString("field", URL_FIELD),
                input = if (generated != null) {
                    generated.optString("prefix") +
                            generated.getString("unit").repeat(generated.getInt("count")) +
                            generated.optString("suffix")
                } else case.getString("input"),
                generated = generated != null,
                links = if (links == null) emptyList()
                else (0 until links.length()).map { linkIndex ->
                    val link = links.getJSONObject(linkIndex)
                    TelLink(link.getString("text"), link.getString("target"))
                },
                decision = case.optString("decision"),
                note = case.optString("note")
            )
        }
}
