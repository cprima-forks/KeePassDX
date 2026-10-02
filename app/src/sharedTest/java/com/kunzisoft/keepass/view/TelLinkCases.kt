package com.kunzisoft.keepass.view

import org.json.JSONArray
import org.json.JSONObject

/** A link as the user sees it: the linked text and the target it opens. */
data class TelLink(val text: String, val target: String)

/** One case of tel-link-cases.json. */
class TelLinkCase(
    val id: String,
    /** true: [links] is the complete list of links expected; false: no tel link is expected. */
    val works: Boolean,
    val field: String,
    val input: String,
    val links: List<TelLink>,
    val note: String
) {
    // Used by the test runners as the name of the test
    override fun toString() = id
}

/** Reads the cases of the file tel-link-cases.json (shared by the unit and the instrumented test). */
object TelLinkCases {

    const val FILE_NAME = "tel-link-cases.json"

    const val URL_FIELD = "url"
    val FIELDS = listOf(URL_FIELD, "notes", "custom", "username", "unset")

    private val ID_REGEX = Regex("\"id\"\\s*:\\s*\"([^\"]+)\"")

    /** The view tag of a field name, null for a field without tag. */
    fun tagOf(field: String): Any? = when (field) {
        URL_FIELD -> TemplateAbstractView.FIELD_URL_TAG
        "notes" -> TemplateAbstractView.FIELD_NOTES_TAG
        "custom" -> TemplateAbstractView.FIELD_CUSTOM_TAG
        "username" -> TemplateAbstractView.FIELD_USERNAME_TAG
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
        return parseList(root.getJSONArray("works"), works = true) +
                parseList(root.getJSONArray("fails"), works = false)
    }

    private fun parseList(array: JSONArray, works: Boolean): List<TelLinkCase> =
        (0 until array.length()).map { index ->
            val case = array.getJSONObject(index)
            val links = case.optJSONArray("links")
            TelLinkCase(
                id = case.getString("id"),
                works = works,
                field = case.optString("field", URL_FIELD),
                input = case.getString("input"),
                links = if (links == null) emptyList()
                else (0 until links.length()).map { linkIndex ->
                    val link = links.getJSONObject(linkIndex)
                    TelLink(link.getString("text"), link.getString("target"))
                },
                note = case.optString("note")
            )
        }
}
