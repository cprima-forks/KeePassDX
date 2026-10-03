package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * Runs every code case of the case files under tel-cases that is not known to differ from the requirements, as its
 * own test, on the phone: the pattern is compiled and matched by the phone's own regular expression
 * engine, which Robolectric cannot show. The same cases run on the desktop JVM in RequirementCasesTest.
 * The cases that are known to differ run in RequirementCasesKnownDefectsInstrumentedTest.
 */
@RunWith(Parameterized::class)
class RequirementCasesInstrumentedTest(private val caseId: String) {

    companion object {
        private fun read(path: String): String =
            InstrumentationRegistry.getInstrumentation().context.assets
                .open(path).bufferedReader().use { it.readText() }

        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            RequirementCases.headers(::read).filter(RequirementCases::isNormal).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        var failure: Throwable? = null
        // Views belong to the main thread; a failure is rethrown here so that the runner reports it
        instrumentation.runOnMainSync {
            try {
                RequirementCaseChecks.run(caseId, ::read, instrumentation.targetContext)
            } catch (throwable: Throwable) {
                failure = throwable
            }
        }
        failure?.let { throw it }
    }
}
