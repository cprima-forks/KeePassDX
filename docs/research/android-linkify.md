# Android: phone-number linkification

Research notes. Read 2026-10-02. Nothing here is a decision or a recommendation.

Status: **reported** means taken from a search summary and not checked at the source.

## Findings

- `Linkify.PHONE_NUMBERS` is deprecated. The documented replacement is `TextClassifier.generateLinks()`; an androidx backport exists. (reported)
  - <https://developer.android.com/reference/android/text/util/Linkify>
  - <https://developer.android.com/jetpack/androidx/releases/textclassifier>
- The platform's old phone-number linkification used libphonenumber's `PhoneNumberMatcher`. (reported)
  - <https://android.googlesource.com/platform/frameworks/base/+/430fc97%5E%21/>
- `Linkify.addLinks(TextView, Pattern, String scheme)` accepts a custom pattern. (reported)
- `PhoneNumberUtils.convertKeypadLettersToDigits()` maps letters to digits: `1-800-GOOG-411` becomes `1-800-4664-411`. (reported)
  - <https://developer.android.com/reference/android/telephony/PhoneNumberUtils>

## Unverified

- A search summary mentioned a built-in transform filter that reduces a match to digits and `+`. Its name and visibility in the SDK were not checked.
