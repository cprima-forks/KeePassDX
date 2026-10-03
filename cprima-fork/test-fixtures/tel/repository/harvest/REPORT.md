# Harvest of the phone's apps

Written by `harvest_ui.py`: each app was launched by an intent that cannot do harm, read, and closed. Nothing was tapped.
Predicted needs come from `predicted-needs.json`, written before the apps were opened.

## dialer (org.fossify.phone)

Launched with `-a android.intent.action.DIAL -d tel:+1234567890`; in front: `org.fossify.phone/org.fossify.phone.activities.DialpadActivity`; 50 nodes of the app on the screen.

| Predicted need | Found | Best candidate |
|---|---|---|
| number: UI-CALL: the number the dialer was handed is compared with the link | **yes** (44) | `org.fossify.phone:id/dialpad_coordinator` (ScrollView) |
| call_button: to know what is NOT to be pressed; the Call check never presses it | **yes** (43) | `org.fossify.phone:id/dialpad_coordinator` (ScrollView) |
| backspace: to leave the number in a known state | **yes** (1) | `org.fossify.phone:id/dialpad_clear_char` (ImageView) |
| contacts_placeholder: the dialer shows suggestions: they must not be mistaken for the number | **yes** (1) | `org.fossify.phone:id/dialpad_placeholder` (TextView) |

Not predicted, but present with an id or description: 40.

- `org.fossify.phone:id/action_bar_root`   (FrameLayout)
- `android:id/content`   (FrameLayout)
- `` Back  (ImageButton)
- `org.fossify.phone:id/letter_fastscroller_thumb`   (ViewGroup)
- `org.fossify.phone:id/letter_fastscroller`   (LinearLayout)
- `org.fossify.phone:id/dialpad_divider`   (TextView)
- `org.fossify.phone:id/dialpad_input`  <redacted> (EditText)
- `org.fossify.phone:id/dialpad_wrapper`   (ViewGroup)
- `org.fossify.phone:id/dialpad_1_holder` One  (RelativeLayout)
- `org.fossify.phone:id/dialpad_1`  1 (TextView)
- `org.fossify.phone:id/dialpad_2_holder` Two  (RelativeLayout)
- `org.fossify.phone:id/dialpad_2`  2 (TextView)

## browser (org.mozilla.firefox)

Launched with `-a android.intent.action.VIEW -d https://example.com`; in front: `org.mozilla.firefox/org.mozilla.fenix.HomeActivity`; 422 nodes of the app on the screen.

| Predicted need | Found | Best candidate |
|---|---|---|
| address_bar: UI-WEB: the address that opened must be the link's target, not only 'the browser came to the front' | **yes** (2) | `org.mozilla.firefox:id/composable_toolbar` (ViewGroup) |
| page_text: the page that loaded shows what was opened (Example Domain) | **yes** (1) | `Example Domain` (WebView) |
| first_run_dialog: a first start may ask about onboarding or permissions and hide the page | NO (0) | - |

Not predicted, but present with an id or description: 16.

- `org.mozilla.firefox:id/action_bar_root`   (LinearLayout)
- `android:id/content`   (FrameLayout)
- `org.mozilla.firefox:id/rootContainer`   (LinearLayout)
- `org.mozilla.firefox:id/container`   (FrameLayout)
- `org.mozilla.firefox:id/container`   (FrameLayout)
- `org.mozilla.firefox:id/gestureLayout`   (FrameLayout)
- `org.mozilla.firefox:id/browserWindow`   (ViewGroup)
- `org.mozilla.firefox:id/browserLayout`   (ViewGroup)
- `org.mozilla.firefox:id/swipeRefresh`   (ViewGroup)
- `org.mozilla.firefox:id/engineView`   (FrameLayout)
- `` Site information  (Button)
- `` New tab  (Button)

## mailer (net.thunderbird.android)

Launched with `-a android.intent.action.SENDTO -d mailto:a@example.com`; in front: `net.thunderbird.android/com.fsck.k9.activity.MessageCompose`; 22 nodes of the app on the screen.

| Predicted need | Found | Best candidate |
|---|---|---|
| to_field: UI-MAIL: the recipient that was filled in must be the link's address | **yes** (9) | `net.thunderbird.android:id/coordinator_layout` (ScrollView) |
| subject: to know the composer is the plain one (empty subject) | **yes** (1) | `net.thunderbird.android:id/subject` (EditText) |
| body: an empty body: nothing was pre-filled by the link | **yes** (3) | `android:id/content` (FrameLayout) |
| send_button: to know what is NOT to be pressed | **yes** (1) | `net.thunderbird.android:id/send` (Button) |
| navigate_up: to leave without a draft | **yes** (1) | `Navigate up` (ImageButton) |

Not predicted, but present with an id or description: 10.

- `net.thunderbird.android:id/action_bar_root`   (FrameLayout)
- `net.thunderbird.android:id/app_bar_layout`   (LinearLayout)
- `net.thunderbird.android:id/add_attachment` Add attachment  (Button)
- `` More options  (ImageView)
- `net.thunderbird.android:id/identity`  <redacted> (TextView)
- `net.thunderbird.android:id/to_wrapper`   (RelativeLayout)
- `net.thunderbird.android:id/to_label`  To (TextView)
- `net.thunderbird.android:id/to`  <redacted>,  (AutoCompleteTextView)
- `net.thunderbird.android:id/recipient_expander_container`   (ViewAnimator)
- `net.thunderbird.android:id/recipient_expander` Expand  (ImageView)

## sms (org.fossify.messages)

Launched with `-a android.intent.action.SENDTO -d sms:+1234567890?body=test`; in front: `org.fossify.messages/org.fossify.messages.activities.ThreadActivity`; 17 nodes of the app on the screen.

| Predicted need | Found | Best candidate |
|---|---|---|
| recipient: future sms: links: the recipient must be the number of the link | **yes** (2) | `org.fossify.messages:id/thread_coordinator` (ScrollView) |
| message_body: the ?body= part of an sms: link must be in the message | **yes** (13) | `org.fossify.messages:id/action_bar_root` (FrameLayout) |
| send_button: to know what is NOT to be pressed | **yes** (1) | `org.fossify.messages:id/thread_send_message` (Button) |

Not predicted, but present with an id or description: 11.

- `android:id/content`   (FrameLayout)
- `` Back  (ImageButton)
- `org.fossify.messages:id/dial_number` Dial number  (Button)
- `` More options  (ImageView)
- `org.fossify.messages:id/thread_holder`   (ViewGroup)
- `org.fossify.messages:id/thread_messages_fastscroller`   (RelativeLayout)
- `org.fossify.messages:id/thread_messages_list`   (RecyclerView)
- `org.fossify.messages:id/trackView`   (LinearLayout)
- `org.fossify.messages:id/message_holder`   (ViewGroup)
- `org.fossify.messages:id/thread_add_attachment` Attachment  (ImageView)
- `org.fossify.messages:id/thread_type_message`  test (EditText)
