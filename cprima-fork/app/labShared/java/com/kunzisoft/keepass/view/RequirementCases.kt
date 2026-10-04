package com.kunzisoft.keepass.view

import org.json.JSONArray
import org.json.JSONObject

/** The level of a case. A case belongs to exactly one level. */
object RqLevel {
    /** Text in, links out: runs in every code environment. */
    const val CODE = "code"

    /** An automated run on a phone or emulator: driven by phonectl, not by these runners. */
    const val DEVICE = "device"

    /** A check by a person. */
    const val MANUAL = "manual"
}

/**
 * What a case says about the implementation today. It is migration and defect state, never an input
 * to a verdict: the verdict always compares `expected` with the actual result.
 */
object RqCurrent {
    const val MATCHES = "matches"
    const val DIFFERS = "differs"
    const val UNKNOWN = "unknown"
}

/** One exact input string, by the id of tel-values.json. */
class RqValue(val id: String, val text: String, val note: String = "")

/** One case of tel-cases/<topic>.json. */
class RqCase(
    val id: String,
    val requirements: List<String>,
    val level: String,
    /** The id of the value, see [RqValue]. */
    val value: String,
    val field: String,
    /** The complete list of links expected, null for a case that is not at the code level. */
    val links: List<TelLink>?,
    /** The time within which the case must finish, null for no limit. */
    val timeLimitMs: Long?,
    val current: String,
    /** Names of the scenarios of the older case file that this case comes from: provenance, not the exact old input. */
    val legacy: List<String>,
    /** API levels on which the case is known to differ although `current` says it matches, see [RequirementCases.isNormal]. */
    val differsOnSdk: List<Int> = emptyList()
) {
    // Used by the test runners as the name of the test
    override fun toString() = id
}

/** The case files under cprima-fork/app/sharedTest/resources: tel-values.json and tel-cases/<topic>.json. */
object RequirementCases {

    const val VALUES_FILE = "tel-values.json"

    /** The topics, one file each. The data hygiene test checks that this list matches the folder. */
    val TOPICS = listOf(
        "number-grammar", "boundaries", "prefix-context", "parameters",
        "neighbours", "fields", "control-characters", "interaction"
    )

    fun pathOf(topic: String) = "tel-cases/$topic.json"

    /** The part of a case that decides in which test class it runs. */
    class Header(val id: String, val level: String, val current: String, val differsOnSdk: Set<Int> = emptySet())

    // One case per line, with the fields in this order: the files are written that way and the data
    // hygiene test checks it. This avoids a JSON parser: the Robolectric runner reads its parameters
    // outside the sandbox, where org.json is not the real implementation.
    private val HEADER_REGEX = Regex(
        "\"id\"\\s*:\\s*\"([^\"]+)\"[^\\n]*?\"level\"\\s*:\\s*\"(\\w+)\"[^\\n]*?\"current\"\\s*:\\s*\"(\\w+)\"" +
            "(?:\\s*,\\s*\"differs_on_sdk\"\\s*:\\s*\\[([0-9,\\s]*)\\])?"
    )

    fun headers(readFile: (String) -> String): List<Header> =
        TOPICS.flatMap { topic ->
            HEADER_REGEX.findAll(readFile(pathOf(topic)))
                .map { Header(it.groupValues[1], it.groupValues[2], it.groupValues[3], sdkList(it.groupValues[4])) }
                .toList()
        }

    private fun sdkList(text: String): Set<Int> =
        text.split(',').map { it.trim() }.filter { it.isNotEmpty() }.map { it.toInt() }.toSet()

    /** A case known to differ: everywhere (`current`), or on the API level the run is on (`differs_on_sdk`). */
    private fun differs(header: Header, sdk: Int?) =
        header.current == RqCurrent.DIFFERS || (sdk != null && sdk in header.differsOnSdk)

    /** True for the cases of the normal task: executable here, and not known to differ on this API level. */
    fun isNormal(header: Header, sdk: Int? = null) = header.level == RqLevel.CODE && !differs(header, sdk)

    /** True for the cases of the known defects task: executable here, and known to differ on this API level. */
    fun isKnownDefect(header: Header, sdk: Int? = null) = header.level == RqLevel.CODE && differs(header, sdk)

    fun parseValues(json: String): Map<String, RqValue> {
        val array = JSONArray(json)
        return (0 until array.length()).map { index ->
            val value = array.getJSONObject(index)
            val generated = value.optJSONObject("generated")
            RqValue(
                id = value.getString("id"),
                text = if (generated != null) {
                    generated.optString("prefix") +
                            generated.getString("unit").repeat(generated.getInt("count")) +
                            generated.optString("suffix")
                } else value.getString("value"),
                note = value.optString("note")
            )
        }.associateBy { it.id }
    }

    fun parseCases(json: String): List<RqCase> {
        val array = JSONArray(json)
        return (0 until array.length()).map { index ->
            val case = array.getJSONObject(index)
            val expected = case.getJSONObject("expected")
            val links = expected.optJSONArray("links")
            RqCase(
                id = case.getString("id"),
                requirements = strings(case.getJSONArray("requirements")),
                level = case.getString("level"),
                value = case.getString("value"),
                field = case.optString("field", TelLinkCases.URL_FIELD),
                links = links?.let { array ->
                    (0 until array.length()).map { linkIndex ->
                        val link = array.getJSONObject(linkIndex)
                        TelLink(link.getString("text"), link.getString("target"))
                    }
                },
                timeLimitMs = if (expected.has("timeLimitMs")) expected.getLong("timeLimitMs") else null,
                current = case.getString("current"),
                legacy = strings(case.optJSONArray("legacy") ?: JSONArray()),
                differsOnSdk = (case.optJSONArray("differs_on_sdk") ?: JSONArray()).let { array -> (0 until array.length()).map { array.getInt(it) } }
            )
        }
    }

    private fun strings(array: JSONArray): List<String> = (0 until array.length()).map { array.getString(it) }

    /** All values and all cases. */
    fun load(readFile: (String) -> String): Pair<Map<String, RqValue>, List<RqCase>> =
        parseValues(readFile(VALUES_FILE)) to TOPICS.flatMap { parseCases(readFile(pathOf(it))) }

}
