package com.kunzisoft.keepass.view

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import kotlin.random.Random

/**
 * Compares the regular expression with a hand-written scanner on thousands of random strings.
 * The strings are made from the characters that matter for the pattern, so edge cases come up that
 * nobody wrote down. The seed is fixed: a failure can be reproduced.
 */
object TelPatternFuzzChecks {

    private const val NUMBER_CHARACTERS = "0123456789().-"

    /** True when the character before [index], read as a letter or a mark on a letter. */
    private fun letterBefore(text: String, index: Int): Boolean {
        if (index <= 0) return false
        val last = text[index - 1]
        val codePoint =
            if (last.isLowSurrogate() && index >= 2 && text[index - 2].isHighSurrogate())
                Character.toCodePoint(text[index - 2], last)
            else last.code
        return Character.isLetter(codePoint) || Character.getType(codePoint) == 6 // Mn
    }

    /**
     * What the pattern and the filter mean together, written without a regular expression: the
     * number after a `tel:` prefix that has no letter before it. A number inside another link is
     * not part of this check: a plain string has no links, the case file covers that.
     */
    private fun reference(text: String): List<String> {
        val found = mutableListOf<String>()
        var index = 0
        while (index + TEL_SCHEME.length < text.length) {
            val plus = index + TEL_SCHEME.length
            if (text.regionMatches(index, TEL_SCHEME, 0, TEL_SCHEME.length, ignoreCase = true) &&
                text[plus] == '+'
            ) {
                var end = plus + 1
                while (end < text.length && text[end] in NUMBER_CHARACTERS) end++
                if (text.substring(plus + 1, end).any { it in '0'..'9' }) {
                    // a rejected number is skipped like an accepted one: no prefix starts inside it
                    if (!letterBefore(text, index)) found.add(text.substring(plus, end))
                    index = end
                    continue
                }
            }
            index++
        }
        return found
    }

    private fun viaPattern(text: String): List<String> {
        val matcher = TEL_PATTERN.matcher(text)
        val found = mutableListOf<String>()
        while (matcher.find()) {
            if (TEL_MATCH_FILTER.acceptMatch(text, matcher.start(), matcher.end())) {
                found.add(matcher.group())
            }
        }
        return found
    }

    // Pieces that the strings are put together from. Single characters alone almost never form
    // "tel:+" followed by a digit, so the pattern would hardly ever match; whole prefixes make the
    // matches, and the interesting neighbours, common. A Cyrillic letter, a combining circumflex and
    // a surrogate pair (a mathematical bold x) join the Latin letters, so that the rule about a
    // letter before the prefix meets every kind of letter.
    private val PIECES = listOf(
        "tel:+4", "TEL:+1", "Tel:+(", "tel:+9", "tel:", "Tel:", "TEL:", "tel", ":", "+", "+4", "1",
        "0", "9", "(", ")", "-", ".", " ", "\n",
        ";", "x", "a", "o", "H", "T", "Ж", "̂", "𝐱", "_", "/"
    )

    fun run(iterations: Int = 5000, seed: Long = 20261002L) {
        val random = Random(seed)
        var matches = 0
        var rejected = 0
        repeat(iterations) {
            val text = buildString {
                repeat(random.nextInt(1, 12)) { append(PIECES[random.nextInt(PIECES.size)]) }
            }
            val expected = reference(text)
            assertEquals("input ${text.replace("\n", "\\n")}", expected, viaPattern(text))
            matches += expected.size
            val all = TEL_PATTERN.matcher(text)
            var patternMatches = 0
            while (all.find()) patternMatches++
            rejected += patternMatches - expected.size
        }
        // The test must not be empty: it has to meet matches, and matches that the letter rule
        // rejects, in numbers.
        assertTrue("only $matches matches in $iterations strings", matches >= iterations / 5)
        assertTrue("only $rejected rejected matches in $iterations strings", rejected >= iterations / 50)
    }
}
