package com.kunzisoft.keepass.view

/** A link as the user sees it: the linked text and the target it opens. */
data class TelLink(val text: String, val target: String)

/** The fields of an entry that the cases name, and the view tag of each. */
object TelLinkCases {

    const val URL_FIELD = "url"
    val FIELDS = listOf(URL_FIELD, "notes", "custom", "username", "password", "title", "unset")

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
}
