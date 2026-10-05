package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The wiring of the Markdown rendering in TextFieldView, on the desktop JVM (Robolectric). The checks are the
 * ones of TextFieldViewMarkdownChecks, which the instrumented test runs on a phone or emulator.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TextFieldViewMarkdownTest {

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Test fun shippedFlagsAreTheNotesOnly() = TextFieldViewMarkdownChecks.shippedFlagsAreTheNotesOnly(context)
    @Test fun onlyTheNotesTagIsAMarkdownField() = TextFieldViewMarkdownChecks.onlyTheNotesTagIsAMarkdownField(context)
    @Test fun anEmptySetSwitchesItOff() = TextFieldViewMarkdownChecks.anEmptySetSwitchesItOff(context)
    @Test fun notesAreShownAsMarkdownAndTheStoredTextIsKept() = TextFieldViewMarkdownChecks.notesAreShownAsMarkdownAndTheStoredTextIsKept(context)
    @Test fun anotherFieldIsShownAsItIs() = TextFieldViewMarkdownChecks.anotherFieldIsShownAsItIs(context)
    @Test fun aHiddenNotesFieldIsNotRenderedUntilItIsRevealed() = TextFieldViewMarkdownChecks.aHiddenNotesFieldIsNotRenderedUntilItIsRevealed(context)
    @Test fun aSecondValueReplacesTheFirst() = TextFieldViewMarkdownChecks.aSecondValueReplacesTheFirst(context)
    @Test fun theLinksOfTheNotesCanBeTapped() = TextFieldViewMarkdownChecks.theLinksOfTheNotesCanBeTapped(context)
    @Test fun aBareAddressInRenderedNotesIsNotLinkified() = TextFieldViewMarkdownChecks.aBareAddressInRenderedNotesIsNotLinkified(context)
}
