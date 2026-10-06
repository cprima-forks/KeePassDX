package com.kunzisoft.keepass.viewmodel

import io.github.optimumcode.json.schema.JsonSchema
import io.github.optimumcode.json.schema.JsonSchemaLoader
import io.github.optimumcode.json.schema.ValidationError
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Makes the view model from a normalised record, the schemas and the render styles.
 *
 *  - Validation is the library's (VM-012); this class writes no validator. A failing rule gets the severity of the
 *    `x-pdh-level` that sits next to it in the schema file (see [SchemaPath]).
 *  - A record that fails is still shown, and the findings are listed (VM-014, VM-015).
 *  - Nothing is dropped: a property that no style names comes last, in the section "Other" (VM-031). A type without a
 *    style is shown with a default style made from its schema (VM-032).
 *  - A protected value never enters the view model (VM-041). The property is protected when the store says so or when
 *    the schema marks it `x-pdh-protected`.
 *  - With several entity types the sections follow the order of the record's types; a property that occurs in more
 *    than one is shown once, where the first style puts it (VM-033).
 */
class ViewModelBuilder(private val schemas: SchemaSet) {

    private val compiled = HashMap<String, JsonSchema>()

    private fun schemaOf(entity: EntityFiles): JsonSchema = compiled.getOrPut(entity.name) {
        // The entity schemas refer to "../types.schema.json". Nothing is fetched: the types file is registered here. This
        // version of the library does not remove the ".." of the resolved address (experiment VX-007), so the file is
        // registered under the address as the library resolves it, which is the $id of the file with "entities/../".
        val types = Json.parseToJsonElement(schemas.typesText)
        val id = types.jsonObject["\$id"]?.jsonPrimitive?.content ?: error("types.schema.json has no \$id")
        val unresolved = id.replace("/schemas/", "/schemas/entities/../")
        JsonSchemaLoader.create().register(types, unresolved).fromDefinition(entity.schemaText)
    }

    /** [mode] EDIT also lists the properties that have no value yet, because an input needs a row to be typed into. */
    fun build(record: NormalizedRecord, mode: Mode = Mode.VIEW): RenderedRecord {
        val editing = mode == Mode.EDIT
        val findings = ArrayList<Finding>()
        val known = ArrayList<EntityFiles>()
        for (name in record.schemas) {
            val entity = schemas.entities[name]
            if (entity == null) {
                findings += Finding(name, "schema", "", "", "unknown entity type", Level.ERROR)
            } else {
                known += entity
                findings += validate(entity, record)
            }
        }

        val protected = record.protectedNames + known.flatMap { protectedBySchema(it) }
        val titleName = known.firstNotNullOfOrNull { it.render?.get("title")?.jsonPrimitive?.content } ?: "Title"
        val shown = HashSet<String>()
        shown += titleName

        fun makeRow(attribute: String, copy: Boolean, multiline: Boolean): RenderedRow {
            val isProtected = attribute in protected
            val value = if (isProtected) RenderedValue.Protected else RenderedValue.Text(record.properties[attribute].orEmpty())
            val input = when {
                isProtected -> Input.SECRET
                multiline -> Input.MULTILINE
                known.any { isDate(it, attribute) } -> Input.DATE
                else -> Input.TEXT
            }
            return RenderedRow(attribute, attribute, value, copy, multiline, input, known.any { attribute in requiredNames(it) })
        }

        val sections = ArrayList<RenderedSection>()
        for (entity in known) {
            val style = entity.render
            if (style == null) {
                val rows = propertyNames(entity).filter { (editing || it in record.properties) && it !in shown }
                    .map { makeRow(it, copy = false, multiline = false) }
                shown += rows.map { it.attribute }
                if (rows.isNotEmpty()) sections += RenderedSection("Properties", false, rows)
                continue
            }
            for (section in arrayOrEmpty(style["sections"])) {
                val sectionObject = section.jsonObject
                val rows = ArrayList<RenderedRow>()
                for (item in arrayOrEmpty(sectionObject["rows"])) {
                    val rowObject = item.jsonObject
                    val attribute = rowObject["attribute"]?.jsonPrimitive?.content ?: continue
                    if ((!editing && attribute !in record.properties) || attribute in shown) continue
                    shown += attribute
                    rows += makeRow(attribute, rowObject.flag("copy"), rowObject.flag("multiline"))
                }
                if (rows.isNotEmpty()) {
                    sections += RenderedSection(
                        sectionObject["label"]?.jsonPrimitive?.content ?: "", sectionObject.flag("collapsed"), rows
                    )
                }
            }
        }

        val candidates = if (editing) (record.properties.keys + known.flatMap { propertyNames(it) }).distinct() else record.properties.keys.toList()
        val other = candidates.filter { it !in shown }.map { makeRow(it, copy = false, multiline = false) }
        if (other.isNotEmpty()) sections += RenderedSection("Other", false, other)

        val title = when {
            titleName in protected -> "(protected title)"
            else -> record.properties[titleName] ?: record.id
        }
        return RenderedRecord(title, record.schemas, sections, findings)
    }

    private fun validate(entity: EntityFiles, record: NormalizedRecord): List<Finding> {
        val errors = ArrayList<ValidationError>()
        val instance = JsonObject(record.properties.mapValues { JsonPrimitive(it.value) })
        schemaOf(entity).validate(instance as JsonElement, errors::add)
        return errors.map { error ->
            val path = error.schemaPath.toString()
            // This version of the library gives no failing keyword: it is the last part of the schema path
            val keyword = path.split('/').lastOrNull { it.isNotEmpty() && !it.startsWith("#") && it.toIntOrNull() == null }
            Finding(
                entity = entity.name,
                keyword = keyword,
                schemaPath = path,
                objectPath = error.objectPath.toString(),
                // The message of the library can quote the value. A finding never carries a value, so it is not used.
                message = "fails ${keyword ?: "a rule"} of ${entity.name}",
                level = SchemaPath.levelOf(entity.schema, path)
            )
        }
    }

    private fun requiredNames(entity: EntityFiles): Set<String> =
        arrayOrEmpty(entity.schema["required"]).map { it.jsonPrimitive.content }.toSet()

    /** A date property: its schema refers to the shared type `date` or says `format: date`. */
    private fun isDate(entity: EntityFiles, attribute: String): Boolean {
        val property = objectOrEmpty(objectOrEmpty(entity.schema["properties"])[attribute])
        return property["\$ref"]?.jsonPrimitive?.content?.endsWith("/date") == true ||
            property["format"]?.jsonPrimitive?.content == "date"
    }

    private fun propertyNames(entity: EntityFiles): List<String> =
        objectOrEmpty(entity.schema["properties"]).keys.toList()

    private fun protectedBySchema(entity: EntityFiles): List<String> =
        objectOrEmpty(entity.schema["properties"])
            .filter { (it.value as? JsonObject)?.get("x-pdh-protected")?.jsonPrimitive?.booleanOrNull == true }
            .map { it.key }

    private fun JsonObject.flag(name: String): Boolean = this[name]?.jsonPrimitive?.boolean ?: false

    private fun objectOrEmpty(element: JsonElement?): JsonObject = (element as? JsonObject) ?: JsonObject(emptyMap())
    private fun arrayOrEmpty(element: JsonElement?): JsonArray = (element as? JsonArray) ?: JsonArray(emptyList())
}
