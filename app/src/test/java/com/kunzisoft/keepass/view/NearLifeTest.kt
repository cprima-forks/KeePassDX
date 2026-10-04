package com.kunzisoft.keepass.view

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The near-life set (near-life.json): every entry names a value of tel-values.json, and that value has a
 * code case in the URL field. For an entry whose case is not known to differ, the links of the value are
 * those the case expects. The entries whose case is known to differ are only resolved here: their result is
 * in RequirementCasesKnownDefectsTest.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@Config(sdk = [34])
class NearLifeTest(private val title: String, private val valueId: String) {

    companion object {
        private fun read(path: String): String = RequirementCasesTest.read(path)

        // Only text parsing here: the parameters are created outside the Robolectric sandbox, where org.json is not available
        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun entries(): List<Array<Any>> =
            Regex("\"title\": \"([^\"]+)\", \"value\": \"(V-[0-9]+)\"").findAll(read("near-life.json"))
                .map { arrayOf<Any>(it.groupValues[1], it.groupValues[2]) }.toList()
    }

    @Test
    fun entry() {
        val (values, cases) = RequirementCases.load(::read)
        val value = values[valueId]
        assertNotNull("[$title] the value $valueId is not in tel-values.json", value)
        val urlCases = cases.filter { it.level == RqLevel.CODE && it.value == valueId && it.field == TelLinkCases.URL_FIELD }
        assert(urlCases.isNotEmpty()) { "[$title] no code case in the URL field for $valueId" }
        val headers = RequirementCases.headers(::read).associateBy { it.id }
        urlCases.filter { RequirementCases.isNormal(headers.getValue(it.id)) }.forEach { case ->
            assertEquals(
                "[$title ${case.id}] links",
                case.links,
                TelLinkCaseChecks.linksIn(ApplicationProvider.getApplicationContext<Context>(), value!!.text, case.field)
            )
        }
    }
}
