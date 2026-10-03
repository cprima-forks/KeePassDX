package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * The feature flags of the phone number links, checked against every case of tel-link-cases.json on
 * the phone. The same checks run on the desktop JVM in PhoneLinkFlagsTest.
 */
@RunWith(Parameterized::class)
class PhoneLinkFlagsInstrumentedTest(private val case: TelLinkCase) {

    companion object {
        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun cases(): List<Array<Any>> {
            val json = InstrumentationRegistry.getInstrumentation().context.assets
                .open(TelLinkCases.FILE_NAME).bufferedReader().use { it.readText() }
            return TelLinkCases.parse(json).map { arrayOf<Any>(it) }
        }
    }

    /** Views belong to the main thread; a failure is rethrown here so that the runner reports it. */
    private fun onMainThread(block: (android.content.Context) -> Unit) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        var failure: Throwable? = null
        instrumentation.runOnMainSync {
            try {
                block(instrumentation.targetContext)
            } catch (throwable: Throwable) {
                failure = throwable
            }
        }
        failure?.let { throw it }
    }

    @Test
    fun defaultArgumentIsShippedConfiguration() =
        onMainThread { PhoneLinkFlagChecks.defaultArgumentIsShippedConfiguration(case, it) }

    @Test
    fun noSchemesNoTelLink() = onMainThread { PhoneLinkFlagChecks.noSchemesNoTelLink(case, it) }

    @Test
    fun allFieldsBehaveAsUrlField() = onMainThread { PhoneLinkFlagChecks.allFieldsBehaveAsUrlField(case, it) }
}
