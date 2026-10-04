package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.JUnit4
import com.kunzisoft.keepass.utils.TelLinkConfig

/** The configuration of the tel links as a whole, on the phone. See TelLinkConfigTest. */
@RunWith(JUnit4::class)
class TelLinkConfigInstrumentedTest {

    @Test
    fun shippedValues() = TelLinkFlagChecks.shippedValues()

    @Test
    fun rfc3966IsRequired() = TelLinkFlagChecks.rfc3966IsRequired()

    @Test
    fun namedFieldsHaveAnEffect() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val inputs = flagInputs { path ->
            instrumentation.context.assets.open(path).bufferedReader().use { it.readText() }
        }
        var failure: Throwable? = null
        instrumentation.runOnMainSync {
            try {
                TelLinkFlagChecks.namedFieldsHaveAnEffect(inputs, instrumentation.targetContext)
            } catch (throwable: Throwable) {
                failure = throwable
            }
        }
        failure?.let { throw it }
    }
}
