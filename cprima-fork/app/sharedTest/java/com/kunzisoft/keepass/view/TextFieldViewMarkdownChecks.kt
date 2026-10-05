package com.kunzisoft.keepass.view

import android.content.Context
import android.os.Build
import android.text.Spanned
import android.text.method.LinkMovementMethod
import android.text.style.StyleSpan
import android.text.style.URLSpan
import android.text.util.Linkify
import android.view.ContextThemeWrapper
import android.widget.TextView
import androidx.core.text.util.LinkifyCompat
import com.kunzisoft.keepass.R
import com.kunzisoft.keepass.utils.MARKDOWN_CONFIG
import com.kunzisoft.keepass.utils.MarkdownConfig
import com.kunzisoft.keepass.utils.MarkdownField
import com.kunzisoft.keepass.utils.MarkdownNotesUtil
import com.kunzisoft.keepass.utils.MarkdownRenderer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue

/**
 * The checks of the Markdown wiring in TextFieldView, shared by the desktop JVM test and the instrumented test: only
 * the notes field shows its text as Markdown, the stored text stays what `value` returns, a hidden field is not
 * rendered, and below the minimum Android version nothing is rendered. A view belongs to the main thread; the
 * instrumented test calls these from there.
 *
 * A check that needs the rendering is skipped on a device below the minimum version, and the one that needs the
 * plain text is skipped on a device at or above it.
 */
object TextFieldViewMarkdownChecks {

    private class Probe(context: Context) : TextFieldView(context) {
        fun shown(): CharSequence = valueView.text
        fun linksTappable(): Boolean = valueView.movementMethod is LinkMovementMethod
        fun linkTargets(): List<String> =
            (valueView.text as Spanned).getSpans(0, valueView.text.length, URLSpan::class.java).map { it.url }
    }

    // The view reads attributes of the theme of the app, which a plain application context may not have
    private fun themed(base: Context): Context = ContextThemeWrapper(base, R.style.KeepassDXStyle_Night)

    private fun field(base: Context, tag: Any?, text: String, revealed: Boolean? = null): Probe =
        Probe(themed(base)).apply {
            this.tag = tag
            if (revealed != null) setProtection(isProtected = true, isRevealedByDefault = revealed, needUserVerificationToReveal = false)
            value = text.toCharArray()
        }

    private fun assumeRendering() =
        assumeTrue("rendering needs Android ${MARKDOWN_CONFIG.minSdk}", Build.VERSION.SDK_INT >= MARKDOWN_CONFIG.minSdk)

    val ALL: Map<String, (Context) -> Unit> = linkedMapOf(
        "shippedFlagsAreTheNotesOnly" to ::shippedFlagsAreTheNotesOnly,
        "onlyTheNotesTagIsAMarkdownField" to ::onlyTheNotesTagIsAMarkdownField,
        "anEmptySetSwitchesItOff" to ::anEmptySetSwitchesItOff,
        "theMinimumVersionGatesTheField" to ::theMinimumVersionGatesTheField,
        "belowTheMinimumTheNotesStayPlain" to ::belowTheMinimumTheNotesStayPlain,
        "notesAreShownAsMarkdownAndTheStoredTextIsKept" to ::notesAreShownAsMarkdownAndTheStoredTextIsKept,
        "anotherFieldIsShownAsItIs" to ::anotherFieldIsShownAsItIs,
        "aHiddenNotesFieldIsNotRenderedUntilItIsRevealed" to ::aHiddenNotesFieldIsNotRenderedUntilItIsRevealed,
        "aSecondValueReplacesTheFirst" to ::aSecondValueReplacesTheFirst,
        "theLinksOfTheNotesCanBeTapped" to ::theLinksOfTheNotesCanBeTapped,
        "aBareAddressInRenderedNotesIsNotLinkified" to ::aBareAddressInRenderedNotesIsNotLinkified,
        "linkifyingAgainRemovesTheLinksOfTheMarkdown" to ::linkifyingAgainRemovesTheLinksOfTheMarkdown
    )

    fun shippedFlagsAreTheNotesOnly(@Suppress("UNUSED_PARAMETER") context: Context) {
        assertEquals(setOf(MarkdownField.NOTES), MARKDOWN_CONFIG.fields)
        // Android 7.0 is the lowest version on which the rendering was measured to work
        assertEquals(24, MARKDOWN_CONFIG.minSdk)
    }

    fun onlyTheNotesTagIsAMarkdownField(@Suppress("UNUSED_PARAMETER") context: Context) {
        // With the version given, so that the check does not depend on the device
        val sdk = MARKDOWN_CONFIG.minSdk
        assertTrue(MarkdownNotesUtil.shows(TemplateAbstractView.FIELD_NOTES_TAG, sdk = sdk))
        listOf(
            TemplateAbstractView.FIELD_TITLE_TAG, TemplateAbstractView.FIELD_USERNAME_TAG,
            TemplateAbstractView.FIELD_PASSWORD_TAG, TemplateAbstractView.FIELD_URL_TAG,
            TemplateAbstractView.FIELD_CUSTOM_TAG, null
        ).forEach { assertFalse("tag $it", MarkdownNotesUtil.shows(it, sdk = sdk)) }
    }

    fun anEmptySetSwitchesItOff(@Suppress("UNUSED_PARAMETER") context: Context) {
        assertFalse(
            MarkdownNotesUtil.shows(
                TemplateAbstractView.FIELD_NOTES_TAG, MarkdownConfig(fields = emptySet()), sdk = MARKDOWN_CONFIG.minSdk
            )
        )
    }

    /** The minimum version is a flag too: below it the notes are not a Markdown field, at it they are. */
    fun theMinimumVersionGatesTheField(@Suppress("UNUSED_PARAMETER") context: Context) {
        val notes = TemplateAbstractView.FIELD_NOTES_TAG
        val minimum = MARKDOWN_CONFIG.minSdk
        assertFalse("one below the minimum", MarkdownNotesUtil.shows(notes, sdk = minimum - 1))
        assertTrue("at the minimum", MarkdownNotesUtil.shows(notes, sdk = minimum))
        assertTrue("the minimum is a flag", MarkdownNotesUtil.shows(notes, MarkdownConfig(minSdk = 19), sdk = 19))
        assertFalse("the minimum is a flag", MarkdownNotesUtil.shows(notes, MarkdownConfig(minSdk = 33), sdk = 28))
    }

    /**
     * On a device below the minimum version the notes field shows its text as it is, with the normal link detection of
     * upstream, and never touches the Markdown library (which cannot run there). Skipped at or above the minimum.
     */
    fun belowTheMinimumTheNotesStayPlain(context: Context) {
        assumeTrue("this check is for Android below ${MARKDOWN_CONFIG.minSdk}", Build.VERSION.SDK_INT < MARKDOWN_CONFIG.minSdk)
        val view = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c https://example.com")
        assertEquals("a *b* c https://example.com", view.shown().toString())
        assertEquals("a *b* c https://example.com", String(view.value))
        assertEquals(listOf("https://example.com"), view.linkTargets())
    }

    fun notesAreShownAsMarkdownAndTheStoredTextIsKept(context: Context) {
        assumeRendering()
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
        assumeRendering()
        val hidden = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c", revealed = false)
        assertEquals("a *b* c", hidden.shown().toString())
        assertEquals("a *b* c", String(hidden.value))

        val shown = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c", revealed = true)
        assertEquals("a b c", shown.shown().toString())
        assertEquals("a *b* c", String(shown.value))
    }

    fun aSecondValueReplacesTheFirst(context: Context) {
        assumeRendering()
        val view = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "a *b* c")
        view.value = "plain".toCharArray()
        assertEquals("plain", view.shown().toString())
        assertEquals("plain", String(view.value))
    }

    /**
     * The links of the notes can be tapped: the field has the link movement method, and the links point to tel:,
     * mailto: and https:. The tap itself, which opens the dialer, the mailer or the browser, is Android's. It is
     * not run here; it was tried by hand on a phone.
     */
    fun theLinksOfTheNotesCanBeTapped(context: Context) {
        assumeRendering()
        val view = field(context, TemplateAbstractView.FIELD_NOTES_TAG, "[a](tel:+4930123) [b](mailto:x@example.com) [c](https://example.com)")
        assertTrue("link movement method", view.linksTappable())
        assertEquals(listOf("tel:+4930123", "mailto:x@example.com", "https://example.com"), view.linkTargets())
    }

    /**
     * Upstream's link detection does not run on a rendered Notes field, so a bare web address or email in it is
     * not a link. In another field, with the same text, it still is: that shows that the detection works here.
     */
    fun aBareAddressInRenderedNotesIsNotLinkified(context: Context) {
        assumeRendering()
        val text = "see https://example.com and mail a@example.com"
        assertEquals(emptyList<String>(), field(context, TemplateAbstractView.FIELD_NOTES_TAG, text).linkTargets())
        assertEquals(
            listOf("https://example.com", "mailto:a@example.com"),
            field(context, TemplateAbstractView.FIELD_CUSTOM_TAG, text).linkTargets()
        )
    }

    /**
     * The reason why a rendered notes field skips upstream's link detection: linkifying a text again removes the
     * links it already has. The check does what TextFieldView would do if it did not skip it, and expects that the
     * link of the Markdown is gone afterwards.
     */
    fun linkifyingAgainRemovesTheLinksOfTheMarkdown(context: Context) {
        assumeRendering()
        fun urlsOf(view: TextView) =
            (view.text as Spanned).getSpans(0, view.text.length, URLSpan::class.java).map { it.url }

        val view = TextView(context)
        view.text = MarkdownRenderer.render("[a](tel:+4930123) and https://example.com")
        assertEquals(listOf("tel:+4930123"), urlsOf(view))
        LinkifyCompat.addLinks(view, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        assertEquals(listOf("https://example.com"), urlsOf(view))
    }
}
