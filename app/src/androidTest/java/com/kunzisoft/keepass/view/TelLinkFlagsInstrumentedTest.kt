package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * The feature flags of the phone number links, checked against the value of every code case on the
 * phone. The same checks run on the desktop JVM in TelLinkFlagsTest.
 */
@RunWith(Parameterized::class)
class TelLinkFlagsInstrumentedTest(private val case: FlagInput) {

    companion object {
        private fun read(path: String): String =
            InstrumentationRegistry.getInstrumentation().context.assets
                .open(path).bufferedReader().use { it.readText() }

        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun cases(): List<Array<Any>> = flagInputs(::read).map { arrayOf<Any>(it) }
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
        onMainThread { TelLinkFlagChecks.defaultArgumentIsShippedConfiguration(case, it) }

    @Test
    fun noSchemesNoTelLink() = onMainThread { TelLinkFlagChecks.noSchemesNoTelLink(case, it) }

    @Test
    fun namedFieldsBehaveAsUrlField() = onMainThread { TelLinkFlagChecks.namedFieldsBehaveAsUrlField(case, it) }

    @Test
    fun emptyFieldsNoTelLink() = onMainThread { TelLinkFlagChecks.emptyFieldsNoTelLink(case, it) }
}
