package com.kunzisoft.keepass.utils

import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Runs every case of the case files under markdown-cases that is not known to differ from the requirements, as its
 * own test, on the desktop JVM (Robolectric). This is the normal task: it must be green.
 * The cases that are known to differ run in MarkdownRendererKnownDefectsTest.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
open class MarkdownRendererTest(private val caseId: String) {

    companion object {
        internal fun read(path: String): String =
            MarkdownRendererTest::class.java.classLoader!!
                .getResourceAsStream(path)!!
                .bufferedReader().use { it.readText() }

        // Only the ids are parameters: the parameters are created outside the Robolectric sandbox,
        // objects made there cannot be used inside it.
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            MarkdownCases.headers(::read).filter(MarkdownCases::isNormal).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() = MarkdownCaseChecks.run(caseId, ::read)
}
