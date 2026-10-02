# Dialer test: tel: URI with separators

Test notes. Run 2026-10-02. Nothing here is a decision or a recommendation.

## Setup

- Device: Fairphone FP4, Android 13, default dialer (the dialer app was not identified).
- Command: `adb shell am start -a android.intent.action.DIAL -d 'tel:+49(30)123-456'`
- `DIAL` only pre-fills the number. No call is placed.

## Result

The dialer shows `+49(30)123-456`. The `+`, the parentheses and the hyphen all arrive unchanged.

Evidence: [dialer-test1.png](dialer-test1.png), a screenshot taken on the device.

## Not tested

- The `.` separator.
- Letters in the number.
- Percent-encoded spaces.
- Any other dialer or device.
