package com.kunzisoft.keepass.viewmodel

/*
 * The data of the view-model spike (requirements: wiki page Requirements-Entry-View-Model). Plain Kotlin, no Android
 * class, so that the desktop JVM test, the phone and the lab screen use the same code.
 */

/** The logical record of an entry (VM-020). It has no KDBX type; the same record can come from any source (VM-021). */
class NormalizedRecord(
    val id: String,
    /** The entity types of the record, in the order of `_schema` (VM-004), such as `bank-account@0`. */
    val schemas: List<String>,
    /** The values by property name. An empty value is not a property. */
    val properties: Map<String, String>,
    /** The names the store marks as protected. The schema can protect more (see [ViewModelBuilder]). */
    val protectedNames: Set<String>
)

/** What the view model is for: reading an entry, or editing it (the screen only; nothing is written back). */
enum class Mode { VIEW, EDIT }

/** What kind of input a row asks for in the edit mode. */
enum class Input { TEXT, MULTILINE, DATE, SECRET }

/** How serious a finding of the validation is: the `x-pdh-level` of the failing rule, `error` when there is none. */
enum class Level { WARN, ERROR }

/** One finding of the validation (VM-015). It never carries a value (VM-041). */
data class Finding(
    val entity: String,
    val keyword: String?,
    val schemaPath: String,
    val objectPath: String,
    val message: String,
    val level: Level
)

sealed interface RenderedValue {
    data class Text(val text: String) : RenderedValue

    /** A protected value. It holds no text at all (VM-041). */
    data object Protected : RenderedValue
}

data class RenderedRow(
    val attribute: String,
    val label: String,
    val value: RenderedValue,
    val copy: Boolean,
    val multiline: Boolean,
    /** For the edit mode: which input the row needs (from the schema and the style). */
    val input: Input = Input.TEXT,
    /** The schema lists the property as required. */
    val required: Boolean = false
)

data class RenderedSection(val label: String, val collapsed: Boolean, val rows: List<RenderedRow>)

/** What a screen shows (VM-040). */
data class RenderedRecord(
    val title: String,
    val entityTypes: List<String>,
    val sections: List<RenderedSection>,
    val findings: List<Finding>
) {
    /** The view model as text. It is what the lab shows and what the leak check reads (VM-043). */
    fun toText(): String = buildString {
        appendLine("title: $title")
        appendLine("types: ${entityTypes.joinToString(", ")}")
        for (section in sections) {
            appendLine("[${section.label}]${if (section.collapsed) " (collapsed)" else ""}")
            for (row in section.rows) {
                val shown = when (val value = row.value) {
                    is RenderedValue.Text -> value.text
                    RenderedValue.Protected -> "<protected>"
                }
                val flags = listOfNotNull(
                    "copy".takeIf { row.copy }, "multiline".takeIf { row.multiline },
                    "required".takeIf { row.required }, "input=${row.input.name.lowercase()}".takeIf { row.input != Input.TEXT && row.input != Input.MULTILINE }
                )
                appendLine("  ${row.label} = $shown${if (flags.isEmpty()) "" else "  {${flags.joinToString(",")}}"}")
            }
        }
        for (finding in findings) {
            appendLine("finding ${finding.level}: ${finding.entity} ${finding.keyword ?: "?"} at ${finding.objectPath.ifEmpty { "/" }}")
        }
    }
}
