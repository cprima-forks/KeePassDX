package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** The configuration of the phone number links as a whole: shipped values, required notation, effect of allFields. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PhoneLinkConfigTest {

    @Test
    fun shippedValues() = PhoneLinkFlagChecks.shippedValues()

    @Test
    fun rfc3966IsRequired() = PhoneLinkFlagChecks.rfc3966IsRequired()

    @Test
    fun allFieldsHasAnEffect() {
        PhoneLinkFlagChecks.allFieldsHasAnEffect(
            flagInputs { path ->
                PhoneLinkConfigTest::class.java.classLoader!!
                    .getResourceAsStream(path)!!
                    .bufferedReader().use { it.readText() }
            },
            ApplicationProvider.getApplicationContext<Context>()
        )
    }
}
