package com.kunzisoft.keepass.utils

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue

/**
 * The check of one case, shared by the desktop JVM test and the instrumented test: render the Markdown, then
 * compare the shown text and the spans, each as a list. Observed spans are given neutral kinds by [MarkdownSpans],
 * so that the same case file is read on every Android version.
 */
object MarkdownCaseChecks {

    fun run(caseId: String, readFile: (String) -> String) {
        val case = MarkdownCases.load(readFile).first { it.id == caseId }
        val limits = if (case.maxChars != null) {
            MarkdownRenderer.Limits(case.maxChars, case.maxDepth ?: MarkdownRenderer.Limits.DEFAULT.maxDepth)
        } else MarkdownRenderer.Limits.DEFAULT

        val rendered = MarkdownRenderer.render(case.markdown, limits)
        val spans = MarkdownSpans.spansOf(rendered)

        // Owner requirement: a password manager loads no image. Whatever the case, no span may be an image.
        assertTrue("${case.id}: an image span was made: $spans", spans.none { it.kind == MarkdownSpans.IMAGE })

        assertEquals("${case.id}: shown text", case.text, rendered.toString())
        assertEquals("${case.id}: spans", describe(case.spans), describe(spans))
    }

    private fun describe(spans: List<MdSpan>) =
        spans.sortedWith(compareBy({ it.start }, { it.end }, { it.kind })).map { it.toString() }
}
