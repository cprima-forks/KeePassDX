package com.kunzisoft.keepass.utils

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * Runs every case of the case files under markdown-cases that is not known to differ from the requirements, as its
 * own test, on the phone or emulator: the library runs on the Android version of the device, which Robolectric
 * cannot show. The same cases run on the desktop JVM in MarkdownRendererTest.
 * The cases that are known to differ run in MarkdownRendererKnownDefectsInstrumentedTest.
 */
@RunWith(Parameterized::class)
class MarkdownRendererInstrumentedTest(private val caseId: String) {

    companion object {
        internal fun read(path: String): String =
            InstrumentationRegistry.getInstrumentation().context.assets
                .open(path).bufferedReader().use { it.readText() }

        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            MarkdownCases.headers(::read).filter(MarkdownCases::isNormal).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() = MarkdownCaseChecks.run(caseId, ::read)
}
