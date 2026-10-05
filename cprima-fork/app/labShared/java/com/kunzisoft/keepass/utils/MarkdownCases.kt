package com.kunzisoft.keepass.utils

import org.json.JSONArray

/** One span that a case expects: a neutral kind (see [MarkdownCaseChecks.spansOf]) and the range of the shown text. */
class MdSpan(val kind: String, val start: Int, val end: Int) {
    override fun toString() = "$kind[$start,$end)"
}

/** One case of markdown-cases/<topic>.json: Markdown in, the shown text and its spans out. */
class MdCase(
    val id: String,
    val requirements: List<String>,
    val level: String,
    val markdown: String,
    /** The limits the case runs with, null for the default limits. */
    val maxChars: Int?,
    val maxDepth: Int?,
    val text: String,
    val spans: List<MdSpan>,
    val current: String
) {
    // Used by the test runners as the name of the test
    override fun toString() = id
}

/** The case files under cprima-fork/app/sharedTest/resources/markdown-cases. */
object MarkdownCases {

    /** The topics, one file each. */
    val TOPICS = listOf(
        "formatting", "plain-stays-plain", "excluded", "links", "safety", "limits",
        "consumed-characters", "plain-notes"
    )

    const val MATCHES = "matches"
    const val DIFFERS = "differs"

    fun pathOf(topic: String) = "markdown-cases/$topic.json"

    /** The part of a case that decides in which test class it runs. */
    class Header(val id: String, val level: String, val current: String)

    // One case per line, with the fields in this order: id, level, current. This avoids a JSON parser: the
    // Robolectric runner reads its parameters outside the sandbox, where org.json is not the real implementation.
    private val HEADER_REGEX = Regex(
        "\"id\"\\s*:\\s*\"([^\"]+)\"[^\\n]*?\"level\"\\s*:\\s*\"(\\w+)\"[^\\n]*?\"current\"\\s*:\\s*\"(\\w+)\""
    )

    fun headers(readFile: (String) -> String): List<Header> =
        TOPICS.flatMap { topic ->
            HEADER_REGEX.findAll(readFile(pathOf(topic)))
                .map { Header(it.groupValues[1], it.groupValues[2], it.groupValues[3]) }
                .toList()
        }

    /** True for the cases of the normal task: not known to differ from the requirements. */
    fun isNormal(header: Header) = header.current != DIFFERS

    /** True for the cases of the known defects task: known to differ from the requirements. */
    fun isKnownDefect(header: Header) = header.current == DIFFERS

    private fun parseCases(json: String): List<MdCase> {
        val array = JSONArray(json)
        return (0 until array.length()).map { index ->
            val case = array.getJSONObject(index)
            val expected = case.getJSONObject("expected")
            val spans = expected.getJSONArray("spans")
            val limits = case.optJSONObject("limits")
            MdCase(
                id = case.getString("id"),
                requirements = strings(case.getJSONArray("requirements")),
                level = case.getString("level"),
                markdown = case.getString("markdown"),
                maxChars = limits?.getInt("maxChars"),
                maxDepth = limits?.getInt("maxDepth"),
                text = expected.getString("text"),
                spans = (0 until spans.length()).map { spanIndex ->
                    val span = spans.getJSONObject(spanIndex)
                    MdSpan(span.getString("kind"), span.getInt("start"), span.getInt("end"))
                },
                current = case.getString("current")
            )
        }
    }

    private fun strings(array: JSONArray): List<String> = (0 until array.length()).map { array.getString(it) }

    /** All cases. */
    fun load(readFile: (String) -> String): List<MdCase> =
        TOPICS.flatMap { parseCases(readFile(pathOf(it))) }
}
