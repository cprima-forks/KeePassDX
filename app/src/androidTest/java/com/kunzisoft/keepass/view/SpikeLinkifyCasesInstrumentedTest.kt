package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * Runs every case of tel-link-cases.json as its own test, on the phone: the pattern is compiled and
 * matched by the phone's own regular expression engine, which Robolectric cannot show.
 * The same cases run on the desktop JVM in SpikeLinkifyCasesTest.
 */
@RunWith(Parameterized::class)
class SpikeLinkifyCasesInstrumentedTest(private val case: TelLinkCase) {

    companion object {
        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun cases(): List<Array<Any>> {
            val json = InstrumentationRegistry.getInstrumentation().context.assets
                .open(TelLinkCases.FILE_NAME).bufferedReader().use { it.readText() }
            return TelLinkCases.parse(json).map { arrayOf<Any>(it) }
        }
    }

    @Test
    fun case() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        var failure: Throwable? = null
        // Views belong to the main thread; a failure is rethrown here so that the runner reports it
        instrumentation.runOnMainSync {
            try {
                TelLinkCaseChecks.check(case, instrumentation.targetContext)
            } catch (throwable: Throwable) {
                failure = throwable
            }
        }
        failure?.let { throw it }
    }
}
