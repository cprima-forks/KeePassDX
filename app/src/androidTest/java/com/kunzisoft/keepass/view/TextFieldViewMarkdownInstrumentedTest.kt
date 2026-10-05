package com.kunzisoft.keepass.view

import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

/**
 * The wiring of the Markdown rendering in TextFieldView, on the phone or emulator: the real view, the real
 * Android text classes of the device. The same checks run on the desktop JVM in TextFieldViewMarkdownTest.
 */
@RunWith(Parameterized::class)
class TextFieldViewMarkdownInstrumentedTest(private val name: String) {

    companion object {
        @JvmStatic
        @Parameterized.Parameters(name = "{0}")
        fun names(): List<Array<Any>> = TextFieldViewMarkdownChecks.ALL.keys.map { arrayOf<Any>(it) }
    }

    @Test
    fun check() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        var failure: Throwable? = null
        // Views belong to the main thread; a failure is rethrown here so that the runner reports it
        instrumentation.runOnMainSync {
            try {
                TextFieldViewMarkdownChecks.ALL.getValue(name)(instrumentation.targetContext)
            } catch (throwable: Throwable) {
                failure = throwable
            }
        }
        failure?.let { throw it }
    }
}
