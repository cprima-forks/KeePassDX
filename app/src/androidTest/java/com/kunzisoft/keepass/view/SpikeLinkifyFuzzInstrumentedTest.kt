package com.kunzisoft.keepass.view

import org.junit.Test

/** The pattern against the hand-written reference, with the phone's regex engine. See TelPatternFuzzChecks. */
class SpikeLinkifyFuzzInstrumentedTest {

    @Test
    fun patternAgreesWithTheReferenceOnRandomStrings() {
        TelPatternFuzzChecks.run()
    }
}
