package com.kunzisoft.keepass.viewmodel

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The view model on the desktop JVM, with the real schema and style files of the proposal (copied unchanged to
 * `cprima-fork/app/sharedTest/resources/viewmodel/schemas`). Requirements: wiki page Requirements-Entry-View-Model.
 */
class ViewModelBuilderTest {

    private val schemas = SchemaSet.load { path ->
        javaClass.classLoader!!.getResourceAsStream("${ViewModelSamples.SCHEMA_DIRECTORY}/$path")?.bufferedReader()?.readText()
    }
    private val builder = ViewModelBuilder(schemas)

    private fun build(sample: ViewModelSamples.Sample) = builder.build(ViewModelSamples.record(sample))

    @Test
    fun everyEntityTypeOfTheCatalogIsLoadedWithItsStyle() {
        assertEquals(19, schemas.entities.size)
        assertTrue("bank-account@0" in schemas.entities && "contract@0" in schemas.entities)
        assertTrue(schemas.entities.filterValues { it.render == null }.keys.toString(), schemas.entities.values.all { it.render != null })
    }

    @Test
    fun everyEntityTypeCompilesAndRendersAnEmptyRecordWithoutFailing() {
        // VX-007: the library must read all 19 real schemas. An empty record breaks their rules, which is the point:
        // the findings are listed and nothing fails.
        for (name in schemas.entities.keys) {
            val view = builder.build(RecordNormalizer.normalize("x", linkedMapOf("_schema" to name)), Mode.EDIT)
            assertTrue(name, view.findings.isNotEmpty())
            assertTrue(name, view.sections.isNotEmpty())
        }
    }

    @Test
    fun aBankAccountIsRenderedInTheSectionsOfItsStyle() {
        val view = build(ViewModelSamples.bankAccount)
        assertEquals("Main current account", view.title)
        assertEquals(listOf("Account", "Notes"), view.sections.map { it.label })
        val account = view.sections.first()
        assertEquals(listOf("IBAN", "BIC", "account_number"), account.rows.map { it.attribute })
        assertEquals(RenderedValue.Text("DE02120300000000202051"), account.rows.first().value)
        assertTrue(account.rows.all { it.copy })
        assertTrue(view.sections.last().rows.single().multiline)
        assertEquals(emptyList<Finding>(), view.findings)
    }

    @Test
    fun aRecordThatBreaksItsSchemaIsStillShownAndTheFindingsAreListed() {
        val view = build(ViewModelSamples.brokenBankAccount)
        assertEquals("Broken example", view.title)
        // required IBAN is missing, and the date does not fit its pattern
        val keywords = view.findings.map { it.keyword }
        assertTrue(keywords.toString(), "required" in keywords)
        assertTrue(keywords.toString(), "pattern" in keywords || "format" in keywords)
        // nothing is dropped: the property that no style names comes last (VM-031)
        assertEquals("Other", view.sections.last().label)
        assertEquals(listOf("branch_code"), view.sections.last().rows.map { it.attribute })
        assertTrue(view.sections.flatMap { it.rows }.any { it.attribute == "valid_until" })
    }

    @Test
    fun anUnknownEntityTypeIsListedAndTheEntryIsStillShown() {
        val view = build(ViewModelSamples.unknownType)
        assertEquals("Not a known type", view.title)
        assertEquals(listOf("schema"), view.findings.map { it.keyword })
        assertEquals(listOf("Other"), view.sections.map { it.label })
        assertEquals(listOf("Notes"), view.sections.single().rows.map { it.attribute })
    }

    @Test
    fun twoEntityTypesFollowTheOrderOfSchemaAndShowAPropertyOnce() {
        val view = build(ViewModelSamples.bankAndLogin)
        assertEquals(listOf("Account", "Notes", "Login"), view.sections.map { it.label })
        val shown = view.sections.flatMap { it.rows }.map { it.attribute }
        assertEquals(shown.toSet().size, shown.size)
        // Notes is in both styles: it stays where the first style (bank account) puts it
        assertEquals(listOf("Account", "Notes", "Login"), view.sections.map { it.label })
    }

    @Test
    fun aProtectedValueNeverEntersTheViewModel() {
        val view = build(ViewModelSamples.bankAndLogin)
        val password = view.sections.flatMap { it.rows }.single { it.attribute == "Password" }
        assertEquals(RenderedValue.Protected, password.value)
        assertFalse(view.toString().contains(ViewModelSamples.SECRET))
        assertFalse(view.toText().contains(ViewModelSamples.SECRET))
        view.findings.forEach { assertFalse(it.toString().contains(ViewModelSamples.SECRET)) }
    }

    @Test
    fun noSecretOccursInAnyViewModelOfTheSamples() {
        for (sample in ViewModelSamples.all) {
            val view = build(sample)
            val everything = view.toString() + view.toText()
            assertFalse(sample.id, everything.contains(ViewModelSamples.SECRET))
        }
    }

    @Test
    fun theSeverityOfARuleComesFromTheLevelNextToIt() {
        // online account: a password or a passkey is an error rule; the URL hint "https" is a warning
        val fields = linkedMapOf("_schema" to "online-account@0", "Title" to "T", "UserName" to "u", "URL" to "http://example.org/")
        val view = builder.build(RecordNormalizer.normalize("x", fields))
        val byKeyword = view.findings.groupBy { it.keyword }
        assertTrue(view.findings.toString(), view.findings.any { it.level == Level.WARN })
        assertTrue(view.findings.toString(), view.findings.any { it.level == Level.ERROR })
        assertTrue(byKeyword.isNotEmpty())
    }

    private fun buildEdit(sample: ViewModelSamples.Sample) = builder.build(ViewModelSamples.record(sample), Mode.EDIT)

    @Test
    fun theEditModeListsTheRowsThatHaveNoValueYet() {
        // the bank account has no "valid_until": the view skips it, the edit lists it so that it can be typed into
        val view = build(ViewModelSamples.bankAccount)
        val edit = buildEdit(ViewModelSamples.bankAccount)
        assertFalse(view.sections.flatMap { it.rows }.any { it.attribute == "valid_until" })
        val validUntil = edit.sections.flatMap { it.rows }.single { it.attribute == "valid_until" }
        assertEquals(RenderedValue.Text(""), validUntil.value)
        assertEquals(Input.DATE, validUntil.input)
    }

    @Test
    fun theEditModeMarksRequiredRowsAndTheKindOfInput() {
        val rows = buildEdit(ViewModelSamples.bankAccount).sections.flatMap { it.rows }.associateBy { it.attribute }
        assertTrue(rows.getValue("IBAN").required)
        assertFalse(rows.getValue("BIC").required)
        assertEquals(Input.MULTILINE, rows.getValue("Notes").input)
        assertEquals(Input.TEXT, rows.getValue("IBAN").input)
    }

    @Test
    fun aSecretIsAnInputOfItsKindButNeverInTheEditViewModel() {
        val edit = buildEdit(ViewModelSamples.bankAndLogin)
        val password = edit.sections.flatMap { it.rows }.single { it.attribute == "Password" }
        assertEquals(Input.SECRET, password.input)
        assertEquals(RenderedValue.Protected, password.value)
        assertFalse(edit.toText().contains(ViewModelSamples.SECRET))
        assertFalse(edit.toString().contains(ViewModelSamples.SECRET))
    }

    @Test
    fun theEditModeFindsMissingRequiredValuesAfterAChange() {
        val fields = LinkedHashMap(ViewModelSamples.bankAccount.fields).apply { remove("IBAN") }
        val edit = builder.build(RecordNormalizer.normalize("x", fields), Mode.EDIT)
        assertTrue(edit.findings.toString(), edit.findings.any { it.keyword == "required" })
    }
}
