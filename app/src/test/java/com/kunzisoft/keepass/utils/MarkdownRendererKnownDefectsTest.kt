package com.kunzisoft.keepass.utils

import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Runs the cases of markdown-cases that are known to differ from the requirements (current: differs), as evidence.
 * They are expected to fail until the defect is fixed, so the normal task leaves this class out;
 * `-PknownDefects` runs only these.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
open class MarkdownRendererKnownDefectsTest(private val caseId: String) {

    companion object {
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            MarkdownCases.headers(MarkdownRendererTest.Companion::read).filter(MarkdownCases::isKnownDefect).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() = MarkdownCaseChecks.run(caseId, MarkdownRendererTest.Companion::read)
}
