package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import com.kunzisoft.keepass.utils.TelLinkConfig

/** The configuration of the phone number links as a whole: shipped values, required notation, effect of fields. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TelLinkConfigTest {

    @Test
    fun shippedValues() = TelLinkFlagChecks.shippedValues()

    @Test
    fun rfc3966IsRequired() = TelLinkFlagChecks.rfc3966IsRequired()

    @Test
    fun namedFieldsHaveAnEffect() {
        TelLinkFlagChecks.namedFieldsHaveAnEffect(
            flagInputs { path ->
                TelLinkConfigTest::class.java.classLoader!!
                    .getResourceAsStream(path)!!
                    .bufferedReader().use { it.readText() }
            },
            ApplicationProvider.getApplicationContext<Context>()
        )
    }
}
