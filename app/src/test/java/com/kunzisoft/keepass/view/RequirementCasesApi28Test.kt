package com.kunzisoft.keepass.view

import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The cases of [RequirementCasesTest] on Android 9 (API 28) instead of Android 14 (API 34), with the same
 * checks. It is its own environment (see test-management/environments): the platform's linkify and
 * regular expressions differ between the two versions. A case that the case file marks
 * `differs_on_sdk: [28]` is not in this class but in [RequirementCasesKnownDefectsApi28Test].
 */
@Config(sdk = [28])
class RequirementCasesApi28Test(caseId: String) : RequirementCasesTest(caseId) {

    companion object {
        const val SDK = 28

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
        fun caseIds(): List<Array<Any>> =
            RequirementCases.headers(RequirementCasesTest.Companion::read)
                .filter { RequirementCases.isNormal(it, SDK) }.map { arrayOf<Any>(it.id) }
    }
}
