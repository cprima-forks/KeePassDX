package com.kunzisoft.keepass.view

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Hygiene of the case files: what the runners rely on, checked once. It does not run a case.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RequirementCaseFilesTest {

    private fun read(path: String): String =
        RequirementCaseFilesTest::class.java.classLoader!!
            .getResourceAsStream(path)!!
            .bufferedReader().use { it.readText() }

    private val values get() = RequirementCases.parseValues(read(RequirementCases.VALUES_FILE))
    private val cases get() = RequirementCases.TOPICS.flatMap { RequirementCases.parseCases(read(RequirementCases.pathOf(it))) }

    @Test
    fun topicListMatchesTheFolder() {
        val folder = RequirementCaseFilesTest::class.java.classLoader!!.getResource("tel-cases")!!
        assertEquals("file", folder.protocol)
        val files = File(folder.toURI()).list()!!.map { it.removeSuffix(".json") }.sorted()
        assertEquals(RequirementCases.TOPICS.sorted(), files)
    }

    @Test
    fun filesHoldOnlyAscii() {
        // Invisible characters are written as \uXXXX escapes, so that nobody has to see them
        (listOf(RequirementCases.VALUES_FILE) + RequirementCases.TOPICS.map(RequirementCases::pathOf)).forEach { path ->
            val bad = read(path).filter { it.code > 126 }
            assertTrue("$path holds non-ASCII characters: ${bad.map { "U+%04X".format(it.code) }}", bad.isEmpty())
        }
    }

    @Test
    fun idsAreUniqueAndWellFormed() {
        val values = values
        assertTrue(values.keys.all { Regex("V-\\d{4,}").matches(it) })
        assertEquals(values.size, RequirementCases.parseValues(read(RequirementCases.VALUES_FILE)).size)
        val ids = cases.map { it.id }
        assertEquals("duplicate case ids", ids.size, ids.toSet().size)
        assertTrue(ids.all { Regex("C-[A-Z]{2}-\\d{3,}").matches(it) })
    }

    @Test
    fun everyCaseHasAnExistingValueAndEveryValueIsUsed() {
        val values = values
        val cases = cases
        val unknown = cases.filter { it.value !in values }.map { it.id }
        assertTrue("cases with an unknown value: $unknown", unknown.isEmpty())
        val unused = values.keys - cases.map { it.value }.toSet()
        assertTrue("unused values: $unused", unused.isEmpty())
    }

    @Test
    fun headersAgreeWithTheParser() {
        // The task split reads the headers without a JSON parser: it must see every case once
        val headers = RequirementCases.headers(::read)
        val cases = cases
        assertEquals(cases.map { it.id }, headers.map { it.id })
        assertEquals(cases.map { it.level }, headers.map { it.level })
        assertEquals(cases.map { it.current }, headers.map { it.current })
        assertEquals(cases.map { it.differsOnSdk.toSet() }, headers.map { it.differsOnSdk })
    }

    @Test
    fun levelsAndCurrentStatesAreKnown() {
        val cases = cases
        assertTrue(cases.all { it.level in listOf(RqLevel.CODE, RqLevel.DEVICE, RqLevel.MANUAL) })
        assertTrue(cases.all { it.current in listOf(RqCurrent.MATCHES, RqCurrent.DIFFERS, RqCurrent.UNKNOWN) })
        assertTrue(cases.all { it.requirements.isNotEmpty() && it.requirements.all { r -> Regex("R-\\d{3,}").matches(r) } })
        assertTrue("a code case without expected links", cases.filter { it.level == RqLevel.CODE }.all { it.links != null })
    }
}
