package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * Runs every code case of the case files under tel-cases that is marked `current: differs`, on the phone, from the
 * same `expected` as every other case. They are the record of the known defects: expected to fail
 * until the implementation meets the requirement, never skipped or rewritten.
 *
 * Not part of the default instrumented run (see testInstrumentationRunnerArguments in
 * app/build.gradle.kts). Run it with `-PknownDefects`. When a defect is fixed, change only `current`
 * of the case to `matches`.
 */
@RunWith(Parameterized::class)
class RequirementCasesKnownDefectsInstrumentedTest(private val caseId: String) {

    companion object {
        private fun read(path: String): String =
            InstrumentationRegistry.getInstrumentation().context.assets
                .open(path).bufferedReader().use { it.readText() }

        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            RequirementCases.headers(::read).filter(RequirementCases::isKnownDefect).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        var failure: Throwable? = null
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
