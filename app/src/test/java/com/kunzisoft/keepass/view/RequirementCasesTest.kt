package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Runs every code case of the case files under tel-cases that is not known to differ from the requirements, as its
 * own test, on the desktop JVM (Robolectric). This is the normal task: it must be green.
 * The cases that are known to differ run in RequirementCasesKnownDefectsTest.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
open class RequirementCasesTest(private val caseId: String) {

    companion object {
        internal fun read(path: String): String =
            RequirementCasesTest::class.java.classLoader!!
                .getResourceAsStream(path)!!
                .bufferedReader().use { it.readText() }

        // Only the ids are parameters: the parameters are created outside the Robolectric sandbox,
        // objects made there cannot be used inside it.
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            RequirementCases.headers(::read).filter(RequirementCases::isNormal).map { arrayOf<Any>(it.id) }
    }

    @Test
    fun case() = RequirementCaseChecks.run(caseId, ::read, ApplicationProvider.getApplicationContext<Context>())
}
