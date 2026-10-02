package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Runs every case of tel-link-cases.json as its own test, on the desktop JVM (Robolectric).
 * The same cases run on the phone in SpikeLinkifyCasesInstrumentedTest.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
class SpikeLinkifyCasesTest(private val caseId: String) {

    companion object {
        private fun caseFile(): String =
            SpikeLinkifyCasesTest::class.java.classLoader!!
                .getResourceAsStream(TelLinkCases.FILE_NAME)!!
                .bufferedReader().use { it.readText() }

        // Only the ids are parameters: the parameters are created outside the Robolectric sandbox,
        // objects made there cannot be used inside it.
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> = TelLinkCases.ids(caseFile()).map { arrayOf<Any>(it) }
    }

    @Test
    fun case() {
        val case = TelLinkCases.parse(caseFile()).first { it.id == caseId }
        TelLinkCaseChecks.check(case, ApplicationProvider.getApplicationContext<Context>())
    }
}
