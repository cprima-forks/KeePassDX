/*
 * Copyright 2026 Christian Prior-Mamulyan.
 *
 * This file is part of KeePassDX.
 *
 *  KeePassDX is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  KeePassDX is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with KeePassDX.  If not, see <http://www.gnu.org/licenses/>.
 *
 */
package com.kunzisoft.keepass.utils

import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Typeface
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.SpannedString
import android.text.style.BulletSpan
import android.text.style.QuoteSpan
import android.text.style.RelativeSizeSpan
import android.text.style.ReplacementSpan
import android.text.style.StyleSpan
import android.text.style.TypefaceSpan
import android.text.style.URLSpan
import org.commonmark.node.BlockQuote
import org.commonmark.node.BulletList
import org.commonmark.node.Code
import org.commonmark.node.Emphasis
import org.commonmark.node.HardLineBreak
import org.commonmark.node.Heading
import org.commonmark.node.HtmlInline
import org.commonmark.node.Link
import org.commonmark.node.ListBlock
import org.commonmark.node.Node
import org.commonmark.node.OrderedList
import org.commonmark.node.Paragraph
import org.commonmark.node.SoftLineBreak
import org.commonmark.node.StrongEmphasis
import org.commonmark.node.Text
import org.commonmark.node.ThematicBreak
import org.commonmark.parser.IncludeSourceSpans
import org.commonmark.parser.Parser
import java.util.Locale

/**
 * Turns the Markdown of a note into styled text, following the CommonMark rules and nothing else. What the
 * renderer does not show as formatting (code blocks, images, HTML, tables, strikethrough, setext headings) is shown
 * as the characters that were typed, so that nothing is dropped. It makes no image and opens no address.
 *
 * Blocks are separated by one empty line, the items of a list by a line break, so that a text without Markdown syntax
 * keeps its paragraphs. A single line break in a paragraph becomes a space, as CommonMark says.
 */
object MarkdownRenderer {

    /** Above one of these limits the text is returned as it is, without any span. */
    class Limits(val maxChars: Int, val maxDepth: Int) {
        companion object {
            // Placeholders until a measurement sets them
            val DEFAULT = Limits(maxChars = 50_000, maxDepth = 20)
        }
    }

    /** The relative text size of a heading of level 1 to 6. A test reads the level back from it. */
    val HEADING_SIZES = floatArrayOf(1.6f, 1.4f, 1.25f, 1.15f, 1.1f, 1.05f)

    /** The text a horizontal rule is drawn over: one no-break space. */
    const val RULE_TEXT = " "

    private const val BULLET_GAP = 24

    private val ALLOWED_SCHEMES = setOf("http", "https", "mailto", "tel")

    // The parser keeps source positions, so that what is not rendered can be shown as it was typed
    private val parser: Parser = Parser.builder()
        .includeSourceSpans(IncludeSourceSpans.BLOCKS_AND_INLINES)
        .build()

    /** The text nests deeper than the limit, or a piece of it cannot be shown as typed: the whole text stays plain. */
    private class StayPlain : RuntimeException()

    fun render(markdown: CharSequence, limits: Limits = Limits.DEFAULT): Spanned {
        val input = markdown.toString()
        if (input.length > limits.maxChars) return SpannedString(input)
        val out = SpannableStringBuilder()
        return try {
            Writer(input, out, limits.maxDepth).blocks(parser.parse(input), 0, BLOCK_SEPARATOR)
            SpannedString(out)
        } catch (stayPlain: StayPlain) {
            SpannedString(input)
        }
    }

    private const val BLOCK_SEPARATOR = "\n\n"
    private const val ITEM_SEPARATOR = "\n"

    private class Writer(private val input: String, private val out: SpannableStringBuilder, private val maxDepth: Int) {

        fun blocks(parent: Node, depth: Int, separator: String) {
            var child = parent.firstChild
            var first = true
            while (child != null) {
                if (!first) out.append(separator)
                block(child, depth)
                first = false
                child = child.next
            }
        }

        private fun block(node: Node, depth: Int) {
            when (node) {
                is Paragraph -> inlines(node)
                is Heading -> heading(node)
                is BlockQuote -> {
                    if (depth + 1 > maxDepth) throw StayPlain()
                    val start = out.length
                    blocks(node, depth + 1, BLOCK_SEPARATOR)
                    span(QuoteSpan(), start)
                }
                is BulletList -> items(node, depth, null, null)
                is OrderedList -> items(
                    node, depth,
                    node.markerStartNumber ?: node.startNumber,
                    node.markerDelimiter ?: node.delimiter.toString()
                )
                is ThematicBreak -> {
                    val start = out.length
                    out.append(RULE_TEXT)
                    span(RuleSpan(), start)
                }
                // Fenced and indented code, HTML blocks, reference definitions, anything else
                else -> typed(node)
            }
        }

        private fun heading(node: Heading) {
            // Only a heading with # is shown as a heading. One underlined with === or --- is shown as typed.
            if (!isAtx(node)) {
                typed(node)
                return
            }
            val start = out.length
            inlines(node)
            span(RelativeSizeSpan(HEADING_SIZES[node.level.coerceIn(1, 6) - 1]), start)
            span(StyleSpan(Typeface.BOLD), start)
        }

        private fun isAtx(node: Node): Boolean {
            val first = node.sourceSpans.firstOrNull() ?: throw StayPlain()
            return input.substring(first.inputIndex, first.inputIndex + first.length).trimStart().startsWith("#")
        }

        private fun items(list: ListBlock, depth: Int, startNumber: Int?, delimiter: String?) {
            if (depth + 1 > maxDepth) throw StayPlain()
            var number = startNumber
            var item = list.firstChild
            var first = true
            while (item != null) {
                if (!first) out.append(ITEM_SEPARATOR)
                val start = out.length
                if (number != null) {
                    out.append(number.toString()).append(delimiter).append(' ')
                    number++
                }
                blocks(item, depth + 1, ITEM_SEPARATOR)
                if (startNumber == null) span(BulletSpan(BULLET_GAP), start)
                first = false
                item = item.next
            }
        }

        private fun inlines(parent: Node) {
            var node = parent.firstChild
            while (node != null) {
                inline(node)
                node = node.next
            }
        }

        private fun inline(node: Node) {
            when (node) {
                is Text -> out.append(node.literal)
                is SoftLineBreak -> out.append(' ')
                is HardLineBreak -> out.append('\n')
                is Code -> {
                    val start = out.length
                    out.append(node.literal)
                    span(TypefaceSpan("monospace"), start)
                }
                is Emphasis -> styled(node, StyleSpan(Typeface.ITALIC))
                is StrongEmphasis -> styled(node, StyleSpan(Typeface.BOLD))
                is Link -> link(node)
                is HtmlInline -> out.append(node.literal)
                // Images, and anything else that is not rendered
                else -> if (node.firstChild == null || node is org.commonmark.node.Image) typed(node) else inlines(node)
            }
        }

        private fun styled(node: Node, span: Any) {
            val start = out.length
            inlines(node)
            span(span, start)
        }

        private fun link(node: Link) {
            val start = out.length
            inlines(node)
            val destination = node.destination
            // Only an address that starts with an allowed scheme can be tapped. The tap covers the text only.
            if (isAllowed(destination)) span(URLSpan(destination), start)
            // The address is always shown after the text, unless the text already is the address (an autolink)
            if (!isSameAddress(out.substring(start), destination)) out.append(" (").append(destination).append(")")
        }

        /** The text is the address, with or without its scheme: `https://a.example`, or `a@b.example` for `mailto:a@b.example`. */
        private fun isSameAddress(text: String, destination: String) =
            text == destination || text == destination.substringAfter(':', "")

        private fun isAllowed(destination: String): Boolean {
            val colon = destination.indexOf(':')
            return colon > 0 && destination.substring(0, colon).lowercase(Locale.ROOT) in ALLOWED_SCHEMES
        }

        /** The node as it was typed, cut from the input by its source positions. */
        private fun typed(node: Node) {
            val spans = node.sourceSpans
            if (spans.isEmpty()) throw StayPlain()
            out.append(spans.joinToString("\n") { input.substring(it.inputIndex, it.inputIndex + it.length) })
        }

        private fun span(what: Any, start: Int) {
            if (out.length > start) out.setSpan(what, start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
    }
}

/** A horizontal rule: a line over the width of the text, drawn instead of the text it covers. */
class RuleSpan : ReplacementSpan() {

    override fun getSize(paint: Paint, text: CharSequence?, start: Int, end: Int, fm: Paint.FontMetricsInt?): Int =
        paint.measureText(text, start, end).toInt()

    override fun draw(
        canvas: Canvas, text: CharSequence?, start: Int, end: Int,
        x: Float, top: Int, y: Int, bottom: Int, paint: Paint
    ) {
        val middle = (top + bottom) / 2f
        canvas.drawLine(x, middle, canvas.clipBounds.right.toFloat(), middle, paint)
    }
}
