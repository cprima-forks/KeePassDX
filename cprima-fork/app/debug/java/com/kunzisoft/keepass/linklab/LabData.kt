package com.kunzisoft.keepass.linklab

import android.content.Context
import com.kunzisoft.keepass.view.RequirementCases
import com.kunzisoft.keepass.view.RqCase
import com.kunzisoft.keepass.view.RqLevel
import com.kunzisoft.keepass.view.RqValue
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import org.json.JSONException

/** The case data cannot be used. The message is the one line that tells why. */
class LabDataException(message: String) : Exception(message)

/** Where the case files are read from. */
interface CaseSource {
    val name: String
    fun exists(path: String): Boolean
    fun read(path: String): ByteArray
}

/** The case files packaged in the app (the fallback). */
class AssetSource(private val context: Context) : CaseSource {
    override val name = "assets"

    override fun exists(path: String) = try {
        context.assets.open(path).close()
        true
    } catch (e: IOException) {
        false
    }

    override fun read(path: String): ByteArray = context.assets.open(path).use { it.readBytes() }
}

/** A directory that was filled with `adb push` (the override). */
class DirSource(private val dir: File) : CaseSource {
    override val name = "dir:" + dir.path
    override fun exists(path: String) = File(dir, path).isFile
    override fun read(path: String): ByteArray = File(dir, path).readBytes()
}

/**
 * The cases and values LinkLab works on, with the SHA-256 of every file they were read from.
 *
 * The files are `tel-values.json` and `tel-cases/<topic>.json`, the same files the code tests read.
 * They are read from an override directory if one holds all of them, else from the packaged assets. A
 * directory that holds only some of them is an error, not a fallback.
 */
class LabData(
    val sourceName: String,
    val values: Map<String, RqValue>,
    val cases: List<RqCase>,
    val hashes: Map<String, String>
) {
    val codeCases: List<RqCase> = cases.filter { it.level == RqLevel.CODE }

    fun valueOf(case: RqCase): RqValue = values.getValue(case.value)

    fun usedBy(valueId: String): List<RqCase> = cases.filter { it.value == valueId }

    /** The first digits of the hash of the values file: enough to recognise a data set on a screenshot. */
    val dataTag: String get() = (hashes[RequirementCases.VALUES_FILE] ?: "").take(8)

    companion object {
        /** Below the app-specific external files directory; `adb push` can write there. */
        const val OVERRIDE_SUBDIRECTORY = "linklab/cases"

        fun overrideDirectory(context: Context, explicit: String?): File? =
            explicit?.let { File(it) }
                ?: context.getExternalFilesDir(null)?.let { File(it, OVERRIDE_SUBDIRECTORY) }

        fun load(context: Context, explicitDirectory: String? = null): LabData {
            val files = listOf(RequirementCases.VALUES_FILE) + RequirementCases.TOPICS.map(RequirementCases::pathOf)
            val dir = overrideDirectory(context, explicitDirectory)
            val dirSource = dir?.let(::DirSource)
            val present = dirSource?.let { source -> files.filter(source::exists) }.orEmpty()
            val source: CaseSource = when {
                present.isEmpty() -> {
                    if (explicitDirectory != null) throw LabDataException("no case files in $explicitDirectory")
                    AssetSource(context)
                }
                present.size == files.size -> dirSource!!
                else -> throw LabDataException(
                    "the override directory $dir is incomplete, missing: " + (files - present.toSet()).joinToString()
                )
            }
            return read(source, files)
        }

        internal fun read(source: CaseSource, files: List<String>): LabData {
            val hashes = LinkedHashMap<String, String>()
            val texts = HashMap<String, String>()
            for (path in files) {
                val bytes = try {
                    source.read(path)
                } catch (e: IOException) {
                    throw LabDataException("cannot read $path from ${source.name}: ${e.message}")
                }
                val bad = bytes.indexOfFirst { (it.toInt() and 0xFF) > 126 }
                if (bad >= 0) throw LabDataException("$path holds a non-ASCII byte at offset $bad; write invisible characters as \\uXXXX")
                hashes[path] = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
                texts[path] = String(bytes, Charsets.UTF_8)
            }
            val values = try {
                RequirementCases.parseValues(texts.getValue(RequirementCases.VALUES_FILE))
            } catch (e: JSONException) {
                throw LabDataException("${RequirementCases.VALUES_FILE} is not valid: ${e.message}")
            }
            val cases = RequirementCases.TOPICS.flatMap { topic ->
                val path = RequirementCases.pathOf(topic)
                try {
                    RequirementCases.parseCases(texts.getValue(path))
                } catch (e: JSONException) {
                    throw LabDataException("$path is not valid: ${e.message}")
                }
            }
            val duplicates = cases.groupBy { it.id }.filter { it.value.size > 1 }.keys
            if (duplicates.isNotEmpty()) throw LabDataException("duplicate case ids: $duplicates")
            val unknown = cases.filter { it.value !in values }.map { it.id }
            if (unknown.isNotEmpty()) throw LabDataException("cases with an unknown value: $unknown")
            return LabData(source.name, values, cases, hashes)
        }
    }
}
