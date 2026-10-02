package com.kunzisoft.keepass.view

import android.content.Context
import android.text.Spanned
import android.text.style.URLSpan
import android.text.util.Linkify
import android.widget.TextView
import androidx.core.text.util.LinkifyCompat
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class SpikeLinkifyTest {

    /** Texts matched by the pattern, in order. */
    private fun matches(text: String): List<String> {
        val matcher = TEL_PATTERN.matcher(text)
        val found = mutableListOf<String>()
        while (matcher.find()) found.add(matcher.group())
        return found
    }

    private fun textView(text: String): TextView =
        TextView(ApplicationProvider.getApplicationContext<Context>()).apply { this.text = text }

    /** Same sequence as TextFieldView.linkify(): the mask based call first, then the spike. */
    private fun linkify(view: TextView, tag: Any?) {
        LinkifyCompat.addLinks(view, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)
        spikeLinkifyTel(view, tag)
    }

    /** Linked text and link target of every link, in text order. */
    private fun links(view: TextView): List<Pair<String, String>> {
        val spanned = view.text as? Spanned ?: return emptyList()
        return spanned.getSpans(0, spanned.length, URLSpan::class.java)
            .sortedBy { spanned.getSpanStart(it) }
            .map { span ->
                spanned.subSequence(spanned.getSpanStart(span), spanned.getSpanEnd(span))
                    .toString() to span.url
            }
    }

    // --- pattern ---

    @Test
    fun patternMatchesGlobalNumbers() {
        assertEquals(listOf("tel:+1"), matches("tel:+1"))
        assertEquals(listOf("tel:+49301234567"), matches("tel:+49301234567"))
        assertEquals(listOf("tel:+49(30)123-456"), matches("tel:+49(30)123-456"))
        assertEquals(listOf("tel:+1-201-555-0123"), matches("tel:+1-201-555-0123"))
        assertEquals(listOf("tel:+49.30.123"), matches("tel:+49.30.123"))
    }

    @Test
    fun patternIsCaseInsensitive() {
        assertEquals(listOf("TEL:+49301234567"), matches("TEL:+49301234567"))
        assertEquals(listOf("Tel:+49301234567"), matches("Tel:+49301234567"))
    }

    @Test
    fun patternStopsAtTheEndOfTheNumber() {
        assertEquals(listOf("tel:+4930123"), matches("call tel:+4930123 now"))
        assertEquals(listOf("tel:+1", "tel:+2"), matches("tel:+1 and tel:+2"))
    }

    @Test
    fun patternDoesNotAcceptSpaces() {
        assertEquals(listOf("tel:+49"), matches("tel:+49 30 123"))
    }

    @Test
    fun patternDoesNotAcceptParameters() {
        assertEquals(listOf("tel:+4930123"), matches("tel:+4930123;ext=12"))
    }

    @Test
    fun patternKeepsTrailingSeparators() {
        // RFC 3966 allows separators after the last digit; a sentence dot is therefore included.
        assertEquals(listOf("tel:+49301234567."), matches("tel:+49301234567."))
    }

    @Test
    fun patternRejectsWhatIsNotAGlobalNumber() {
        assertEquals(emptyList<String>(), matches("tel:"))
        assertEquals(emptyList<String>(), matches("tel:+"))
        assertEquals(emptyList<String>(), matches("tel:+()"))
        assertEquals(emptyList<String>(), matches("tel:+-.-"))
        assertEquals(emptyList<String>(), matches("tel:+abc"))
        assertEquals(emptyList<String>(), matches("tel:0301234567"))
        assertEquals(emptyList<String>(), matches("+49301234567"))
        assertEquals(emptyList<String>(), matches("0301234567"))
    }

    // --- link creation ---

    @Test
    fun urlFieldGetsALink() {
        val view = textView("tel:+4930123")
        linkify(view, TemplateAbstractView.FIELD_URL_TAG)
        assertEquals(listOf("tel:+4930123" to "tel:+4930123"), links(view))
    }

    @Test
    fun otherFieldsAndUnsetTagGetNoLink() {
        for (tag in listOf<Any?>(
            TemplateAbstractView.FIELD_NOTES_TAG,
            TemplateAbstractView.FIELD_CUSTOM_TAG,
            TemplateAbstractView.FIELD_USERNAME_TAG,
            null
        )) {
            val view = textView("tel:+4930123")
            linkify(view, tag)
            assertEquals("tag $tag", emptyList<Pair<String, String>>(), links(view))
        }
    }

    @Test
    fun schemeIsNormalisedInTheLinkTarget() {
        val view = textView("TEL:+4930123")
        linkify(view, TemplateAbstractView.FIELD_URL_TAG)
        assertEquals(listOf("TEL:+4930123" to "tel:+4930123"), links(view))
    }

    @Test
    fun existingWebLinkIsKept() {
        val view = textView("see https://example.com and tel:+4930123")
        linkify(view, TemplateAbstractView.FIELD_URL_TAG)
        assertEquals(
            listOf(
                "https://example.com" to "https://example.com",
                "tel:+4930123" to "tel:+4930123"
            ),
            links(view)
        )
    }

    @Test
    fun repeatedLinkifyDoesNotDuplicateLinks() {
        val view = textView("see https://example.com and tel:+4930123")
        linkify(view, TemplateAbstractView.FIELD_URL_TAG)
        linkify(view, TemplateAbstractView.FIELD_URL_TAG)
        linkify(view, TemplateAbstractView.FIELD_URL_TAG)
        assertEquals(2, links(view).size)
    }

    @Test
    fun textWithBidiControlCharacterIsNotLinked() {
        // The platform refuses to link text that contains U+202C, U+202D or U+202E.
        val view = textView("tel:+4930123‮")
        linkify(view, TemplateAbstractView.FIELD_URL_TAG)
        assertEquals(emptyList<Pair<String, String>>(), links(view))
    }
}
