package com.kunzisoft.keepass.viewmodel

/**
 * Entries of the spike, written as fields (name and value), the way a store holds them. They are fictional. The same
 * samples are shown by the lab screen and checked by the tests.
 */
object ViewModelSamples {

    /** Where the schema files are, below the resources (test) or the assets (lab). */
    const val SCHEMA_DIRECTORY = "viewmodel/schemas"

    class Sample(val id: String, val fields: Map<String, String>, val protectedFields: Set<String> = emptySet())

    /** An ordinary bank account (the goal of the first step). IBAN: the example number that German banks publish. */
    val bankAccount = Sample(
        id = "bank-account",
        fields = linkedMapOf(
            "_schema" to "bank-account@0",
            "Title" to "Main current account",
            "IBAN" to "DE02120300000000202051",
            "BIC" to "BYLADEM1001",
            "account_number" to "202051",
            "Notes" to "Household current account"
        )
    )

    /** One entry of two entity types, with a password that the schema protects (VM-004, VM-033, VM-041). */
    const val SECRET = "correct horse battery staple"
    val bankAndLogin = Sample(
        id = "bank-and-login",
        fields = linkedMapOf(
            "_schema" to "bank-account@0, online-account@0",
            "Title" to "Example Bank",
            "IBAN" to "DE02120300000000202051",
            "BIC" to "BYLADEM1001",
            "UserName" to "alice",
            "URL" to "https://bank.example/login",
            "Password" to SECRET,
            "Notes" to "Both a bank account and an online account"
        )
    )

    /** A bank account that breaks its schema (no IBAN, a bad date) and has a property that no style names. */
    val brokenBankAccount = Sample(
        id = "broken-bank-account",
        fields = linkedMapOf(
            "_schema" to "bank-account@0",
            "Title" to "Broken example",
            "valid_until" to "tomorrow",
            "branch_code" to "4711"
        )
    )

    /** An entity type that no file describes (VM-014). */
    val unknownType = Sample(
        id = "unknown-type",
        fields = linkedMapOf("_schema" to "spaceship@7", "Title" to "Not a known type", "Notes" to "still shown")
    )

    val all = listOf(bankAccount, bankAndLogin, brokenBankAccount, unknownType)

    fun record(sample: Sample): NormalizedRecord =
        RecordNormalizer.normalize(sample.id, sample.fields, sample.protectedFields)
}
