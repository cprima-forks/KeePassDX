package com.kunzisoft.keepass.viewmodel

/**
 * Makes the logical record from the fields of an entry (VM-020). The input is plain names and values, so it does not
 * matter whether they come from a KDBX entry or from memory (VM-021).
 *
 * `_schema` lists the entity types, separated by commas (VM-004). It is not a property of the record.
 */
object RecordNormalizer {

    const val SCHEMA_FIELD = "_schema"

    fun normalize(id: String, fields: Map<String, String>, protectedFields: Set<String> = emptySet()): NormalizedRecord {
        val schemas = fields[SCHEMA_FIELD].orEmpty().split(',').map { it.trim() }.filter { it.isNotEmpty() }
        val properties = LinkedHashMap<String, String>()
        for ((name, value) in fields) {
            if (name != SCHEMA_FIELD && value.isNotEmpty()) properties[name] = value
        }
        return NormalizedRecord(id, schemas, properties, protectedFields)
    }
}
