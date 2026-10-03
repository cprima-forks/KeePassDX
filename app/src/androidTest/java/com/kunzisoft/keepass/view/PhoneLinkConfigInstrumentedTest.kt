package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.JUnit4

/** The configuration of the phone number links as a whole, on the phone. See PhoneLinkConfigTest. */
@RunWith(JUnit4::class)
class PhoneLinkConfigInstrumentedTest {

    @Test
    fun shippedValues() = PhoneLinkFlagChecks.shippedValues()

    @Test
    fun rfc3966IsRequired() = PhoneLinkFlagChecks.rfc3966IsRequired()

    @Test
    fun allFieldsHasAnEffect() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val json = instrumentation.context.assets.open(TelLinkCases.FILE_NAME)
            .bufferedReader().use { it.readText() }
        var failure: Throwable? = null
        instrumentation.runOnMainSync {
            try {
                PhoneLinkFlagChecks.allFieldsHasAnEffect(TelLinkCases.parse(json), instrumentation.targetContext)
            } catch (throwable: Throwable) {
                failure = throwable
            }
        }
        failure?.let { throw it }
    }
}
