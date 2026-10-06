package com.kunzisoft.keepass.viewmodel

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** The text of one entity type: its schema, and its render style when there is one (VM-032). */
class EntityFiles(val name: String, val schemaText: String, val renderText: String?) {
    val schema: JsonObject = Json.parseToJsonElement(schemaText).jsonObject
    val render: JsonObject? = renderText?.let { Json.parseToJsonElement(it).jsonObject }
}

/**
 * The schema files of the spike: the shared value types and the entity types that the catalog names. The files are
 * read through [read], so the desktop test (class path), the lab (assets) and a test (memory) all work.
 *
 * Layout, as in the files of the proposal: `catalogs/default.json`, `types.schema.json`,
 * `entities/<name>.schema.json` and `entities/<name>.render.json`.
 */
class SchemaSet(val typesText: String, val entities: Map<String, EntityFiles>) {

    companion object {
        fun load(read: (path: String) -> String?): SchemaSet {
            val catalog = Json.parseToJsonElement(requireNotNull(read("catalogs/default.json")) { "no catalog" }).jsonObject
            val types = requireNotNull(read("types.schema.json")) { "no types.schema.json" }
            val names = catalog["entity_types"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty()
            val entities = LinkedHashMap<String, EntityFiles>()
            for (name in names) {
                val schema = requireNotNull(read("entities/$name.schema.json")) { "no schema for $name" }
                entities[name] = EntityFiles(name, schema, read("entities/$name.render.json"))
            }
            return SchemaSet(types, entities)
        }
    }
}

/** Finds the subschema that a validation error points to, to read the `x-pdh-level` that sits next to the rule. */
internal object SchemaPath {

    /**
     * The `x-pdh-level` that applies to the failing rule: the deepest one on the way down the path. The path can leave
     * the file (a rule of another document through `$ref`); then the last level found is used.
     */
    fun levelOf(schema: JsonElement, path: String): Level {
        var node: JsonElement? = schema
        var level: String? = null
        for (segment in path.trimStart('#').split('/').filter { it.isNotEmpty() }) {
            val key = segment.replace("~1", "/").replace("~0", "~")
            node = when (node) {
                is JsonObject -> node[key]
                is JsonArray -> key.toIntOrNull()?.let { node.getOrNull(it) }
                else -> null
            }
            val declared = (node as? JsonObject)?.get("x-pdh-level")?.jsonPrimitive?.content
            if (declared != null) level = declared
            if (node == null) break
        }
        return if (level == "warn") Level.WARN else Level.ERROR
    }
}
