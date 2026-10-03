package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Runs every code case of the case files under tel-cases that is marked `current: differs`, from the same
 * `expected` as every other case. These cases are the record of the known defects: they are expected
 * to fail until the implementation meets the requirement, and they are never skipped or rewritten.
 *
 * Not part of the default unit test task. Run it with `-PknownDefects`. When a defect is fixed, change
 * only `current` of the case to `matches`; the case then joins RequirementCasesTest.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
open class RequirementCasesKnownDefectsTest(private val caseId: String) {

    companion object {
        internal fun read(path: String): String =
            RequirementCasesKnownDefectsTest::class.java.classLoader!!
                .getResourceAsStream(path)!!
                .bufferedReader().use { it.readText() }

        // Only the ids are parameters: see RequirementCasesTest
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            RequirementCases.headers(::read).filter(RequirementCases::isKnownDefect).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() = RequirementCaseChecks.run(caseId, ::read, ApplicationProvider.getApplicationContext<Context>())
}
