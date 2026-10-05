package com.kunzisoft.keepass.view

import android.content.Context
import android.text.Spanned
import android.text.style.StyleSpan
import android.view.ContextThemeWrapper
import com.kunzisoft.keepass.R
import com.kunzisoft.keepass.utils.MARKDOWN_CONFIG
import com.kunzisoft.keepass.utils.MarkdownConfig
import com.kunzisoft.keepass.utils.MarkdownField
import com.kunzisoft.keepass.utils.MarkdownNotesUtil
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue

/**
 * The checks of the Markdown wiring in TextFieldView, shared by the desktop JVM test and the instrumented test: only
 * the notes field shows its text as Markdown, the stored text stays what `value` returns, and a hidden field is not
 * rendered. A view belongs to the main thread; the instrumented test calls these from there.
 */
object TextFieldViewMarkdownChecks {

    private class Probe(context: Context) : TextFieldView(context) {
        fun shown(): CharSequence = valueView.text
    }

    // The view reads attributes of the theme of the app, which a plain application context may not have
    private fun themed(base: Context): Context = ContextThemeWrapper(base, R.style.KeepassDXStyle_Night)

    private fun field(base: Context, tag: Any?, text: String, revealed: Boolean? = null): Probe =
        Probe(themed(base)).apply {
            this.tag = tag
            if (revealed != null) setProtection(isProtected = true, isRevealedByDefault = revealed, needUserVerificationToReveal = false)
            value = text.toCharArray()
        }

    val ALL: Map<String, (Context) -> Unit> = linkedMapOf(
        "shippedFlagsAreTheNotesOnly" to ::shippedFlagsAreTheNotesOnly,
        "onlyTheNotesTagIsAMarkdownField" to ::onlyTheNotesTagIsAMarkdownField,
        "anEmptySetSwitchesItOff" to ::anEmptySetSwitchesItOff,
        "notesAreShownAsMarkdownAndTheStoredTextIsKept" to ::notesAreShownAsMarkdownAndTheStoredTextIsKept,
        "anotherFieldIsShownAsItIs" to ::anotherFieldIsShownAsItIs,
        "aHiddenNotesFieldIsNotRenderedUntilItIsRevealed" to ::aHiddenNotesFieldIsNotRenderedUntilItIsRevealed,
        "aSecondValueReplacesTheFirst" to ::aSecondValueReplacesTheFirst
    )

    fun shippedFlagsAreTheNotesOnly(@Suppress("UNUSED_PARAMETER") context: Context) {
        assertEquals(setOf(MarkdownField.NOTES), MARKDOWN_CONFIG.fields)
    }

    fun onlyTheNotesTagIsAMarkdownField(@Suppress("UNUSED_PARAMETER") context: Context) {
        assertTrue(MarkdownNotesUtil.shows(TemplateAbstractView.FIELD_NOTES_TAG))
        listOf(
            TemplateAbstractView.FIELD_TITLE_TAG, TemplateAbstractView.FIELD_USERNAME_TAG,
            TemplateAbstractView.FIELD_PASSWORD_TAG, TemplateAbstractView.FIELD_URL_TAG,
            TemplateAbstractView.FIELD_CUSTOM_TAG, null
        ).forEach { assertFalse("tag $it", MarkdownNotesUtil.shows(it)) }
    }

    fun anEmptySetSwitchesItOff(@Suppress("UNUSED_PARAMETER") context: Context) {
        assertFalse(MarkdownNotesUtil.shows(TemplateAbstractView.FIELD_NOTES_TAG, MarkdownConfig(fields = emptySet())))
    }

    fun notesAreShownAsMarkdownAndTheStoredTextIsKept(context: Context) {
        val view = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c")
        assertEquals("a b c", view.shown().toString())
        assertTrue((view.shown() as Spanned).getSpans(0, 5, StyleSpan::class.java).isNotEmpty())
        assertEquals("a *b* c", String(view.value))
    }

    fun anotherFieldIsShownAsItIs(context: Context) {
        listOf(
            TemplateAbstractView.FIELD_USERNAME_TAG, TemplateAbstractView.FIELD_URL_TAG,
            TemplateAbstractView.FIELD_CUSTOM_TAG
        ).forEach { tag ->
            val view = field(context, tag, "a *b* c")
            assertEquals("tag $tag", "a *b* c", view.shown().toString())
            assertEquals("tag $tag", "a *b* c", String(view.value))
        }
    }

    fun aHiddenNotesFieldIsNotRenderedUntilItIsRevealed(context: Context) {
        val hidden = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c", revealed = false)
        assertEquals("a *b* c", hidden.shown().toString())
        assertEquals("a *b* c", String(hidden.value))

        val shown = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c", revealed = true)
        assertEquals("a b c", shown.shown().toString())
        assertEquals("a *b* c", String(shown.value))
    }

    fun aSecondValueReplacesTheFirst(context: Context) {
        val view = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c")
        view.value = "plain".toCharArray()
        assertEquals("plain", view.shown().toString())
        assertEquals("plain", String(view.value))
    }
}
