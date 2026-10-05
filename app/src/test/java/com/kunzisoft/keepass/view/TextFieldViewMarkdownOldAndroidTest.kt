package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The notes field on Android 4.4 (API 19), the `minSdk` of the app, on the desktop JVM (Robolectric). The Markdown
 * library cannot run there (it needs java.util.function, which Android has from API 24; see the wiki page
 * Research-Markdown-minSdk), so below the minimum version the field must show its text as it is and must not load the
 * library. Robolectric cannot show a missing class of the real Android, so the run on a real API 19 emulator is the
 * MarkdownLab batch, not this test.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [19])
class TextFieldViewMarkdownOldAndroidTest {

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Test fun theMinimumVersionGatesTheField() = TextFieldViewMarkdownChecks.theMinimumVersionGatesTheField(context)
    @Test fun belowTheMinimumTheNotesStayPlain() = TextFieldViewMarkdownChecks.belowTheMinimumTheNotesStayPlain(context)
    @Test fun anotherFieldIsShownAsItIs() = TextFieldViewMarkdownChecks.anotherFieldIsShownAsItIs(context)
}
