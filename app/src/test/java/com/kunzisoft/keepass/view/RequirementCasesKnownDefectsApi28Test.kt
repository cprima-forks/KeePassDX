package com.kunzisoft.keepass.view

import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The cases that are known to differ on Android 9 (API 28): those marked `current: differs` and those marked
 * `differs_on_sdk: [28]`. Like [RequirementCasesKnownDefectsTest] they are expected to fail, are only run
 * with `-PknownDefects`, and are never skipped or rewritten. The name contains `KnownDefects`, which is
 * what the test task filters on.
 */
@Config(sdk = [28])
class RequirementCasesKnownDefectsApi28Test(caseId: String) : RequirementCasesKnownDefectsTest(caseId) {

    companion object {
        const val SDK = 28

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            RequirementCases.headers(RequirementCasesKnownDefectsTest.Companion::read)
                .filter { RequirementCases.isKnownDefect(it, SDK) }.map { arrayOf<Any>(it.id) }
    }
}
