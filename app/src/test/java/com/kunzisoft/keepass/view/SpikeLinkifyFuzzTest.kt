package com.kunzisoft.keepass.view

import org.junit.Test

/** The pattern against the hand-written reference, on the desktop JVM. See TelPatternFuzzChecks. */
class SpikeLinkifyFuzzTest {

    @Test
    fun patternAgreesWithTheReferenceOnRandomStrings() {
        TelPatternFuzzChecks.run()
    }
}
