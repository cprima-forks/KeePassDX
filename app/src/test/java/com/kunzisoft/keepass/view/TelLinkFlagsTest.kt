package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The feature flags of the phone number links, checked against the value of every code case on the
 * desktop JVM (Robolectric). The same checks run on the phone in TelLinkFlagsInstrumentedTest.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
class TelLinkFlagsTest(private val caseId: String) {

    companion object {
        private fun read(path: String): String =
            TelLinkFlagsTest::class.java.classLoader!!
                .getResourceAsStream(path)!!
                .bufferedReader().use { it.readText() }

        // Only the ids are parameters: see RequirementCasesTest
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            RequirementCases.headers(::read).filter { it.level == RqLevel.CODE }.map { arrayOf<Any>(it.id) }
    }

    private val context: Context get() = ApplicationProvider.getApplicationContext()
    private val case: FlagInput
        get() = flagInputs(::read).first { it.id == caseId }

    @Test
    fun defaultArgumentIsShippedConfiguration() =
        TelLinkFlagChecks.defaultArgumentIsShippedConfiguration(case, context)

    @Test
    fun noSchemesNoTelLink() = TelLinkFlagChecks.noSchemesNoTelLink(case, context)

    @Test
    fun namedFieldsBehaveAsUrlField() = TelLinkFlagChecks.namedFieldsBehaveAsUrlField(case, context)

    @Test
    fun emptyFieldsNoTelLink() = TelLinkFlagChecks.emptyFieldsNoTelLink(case, context)
}
