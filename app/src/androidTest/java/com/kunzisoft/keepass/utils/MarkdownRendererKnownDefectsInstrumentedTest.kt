package com.kunzisoft.keepass.utils

import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * Runs the cases of markdown-cases that are known to differ from the requirements (current: differs), as evidence,
 * on the phone or emulator. They are expected to fail until the defect is fixed, so the normal run leaves this class
 * out (see fork.gradle); `-PknownDefects` runs only this class.
 */
@RunWith(Parameterized::class)
class MarkdownRendererKnownDefectsInstrumentedTest(private val caseId: String) {

    companion object {
        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            MarkdownCases.headers(MarkdownRendererInstrumentedTest.Companion::read)
                .filter(MarkdownCases::isKnownDefect).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() = MarkdownCaseChecks.run(caseId, MarkdownRendererInstrumentedTest.Companion::read)
}
