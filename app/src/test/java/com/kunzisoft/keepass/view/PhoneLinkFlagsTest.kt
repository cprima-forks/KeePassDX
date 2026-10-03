package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The feature flags of the phone number links, checked against every case of tel-link-cases.json on
 * the desktop JVM (Robolectric). The same checks run on the phone in PhoneLinkFlagsInstrumentedTest.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
class PhoneLinkFlagsTest(private val caseId: String) {

    companion object {
        private fun caseFile(): String =
            PhoneLinkFlagsTest::class.java.classLoader!!
                .getResourceAsStream(TelLinkCases.FILE_NAME)!!
                .bufferedReader().use { it.readText() }

        // Only the ids are parameters: see SpikeLinkifyCasesTest
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> = TelLinkCases.ids(caseFile()).map { arrayOf<Any>(it) }
    }

    private val context: Context get() = ApplicationProvider.getApplicationContext()
    private val case: TelLinkCase get() = TelLinkCases.parse(caseFile()).first { it.id == caseId }

    @Test
    fun defaultArgumentIsShippedConfiguration() =
        PhoneLinkFlagChecks.defaultArgumentIsShippedConfiguration(case, context)

    @Test
    fun noSchemesNoTelLink() = PhoneLinkFlagChecks.noSchemesNoTelLink(case, context)

    @Test
    fun allFieldsBehaveAsUrlField() = PhoneLinkFlagChecks.allFieldsBehaveAsUrlField(case, context)
}
