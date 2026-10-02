# How the URL field is identified in the entry view

Code reading notes. Nothing here is a decision or a recommendation.

- Read on 2026-10-02 in the checkout of `feature/1852-tel-scheme`, which adds no code to `develop` at `f799098c9` (4.5.5). Line numbers refer to that checkout.
- Everything was read from source. **Nothing was run or debugged.**
- Paths are relative to `app/src/main/java/com/kunzisoft/keepass/` (app) and `database/src/main/java/com/kunzisoft/keepass/` (database).

## 1. The identifiers

| Identifier | Value | Where |
|---|---|---|
| `TemplateField.LABEL_URL` | `"URL"` | database: `database/element/template/TemplateField.kt:30` |
| `Template.URL_ATTRIBUTE` | `TemplateAttribute(LABEL_URL, TEXT, false, options with setLink(true))` | database: `database/element/template/Template.kt:157-163` |
| `TemplateAbstractView.FIELD_URL_TAG` | `"FIELD_URL_TAG"` | app: `view/TemplateAbstractView.kt:838` |
| `EntryInfo.url` | `String`, the stored URL value | database: `model/EntryInfo.kt:59` |

## 2. How a view gets the URL tag

`TemplateAbstractView.getTagFromStandardTemplateAttribute(templateAttribute)` (`view/TemplateAbstractView.kt:195-221`) maps a template attribute to a tag by comparing its label, **ignoring case**:

```
LABEL_TITLE      -> FIELD_TITLE_TAG
LABEL_USERNAME   -> FIELD_USERNAME_TAG
LABEL_PASSWORD   -> FIELD_PASSWORD_TAG
LABEL_URL        -> FIELD_URL_TAG        (lines 207-209)
LABEL_EXPIRATION -> FIELD_EXPIRES_TAG
LABEL_NOTES      -> FIELD_NOTES_TAG
anything else    -> FIELD_CUSTOM_TAG
```

It is called while building each template attribute (lines 171-172) and for standard fields that are not in the template (line 229).

The tag is written to the view in `buildViewForTemplateField` (`view/TemplateAbstractView.kt:246-281`):

- line 263: `itemView?.id = field.name.hashCode()`
- line 264: `itemView?.tag = fieldTag`

`itemView` is the view returned by `buildLinearTextView`. In the entry view (`TemplateView`) that is a `TextFieldView`. So the `TextFieldView` instance itself carries the tag.

Custom fields built by `buildViewForCustomField` (lines 233-244) always get `FIELD_CUSTOM_TAG`.

## 3. How the URL value reaches the view

- `populateEntryFieldView(FIELD_URL_TAG, Template.URL_ATTRIBUTE, entryInfo.url, showEmptyFields)` (`view/TemplateAbstractView.kt:411-414`).
- It finds the view with `findViewWithTag(fieldTag)` (line 330). If the template has no URL view and the value is not empty, it builds one from the `templateAttribute` argument, which is `Template.URL_ATTRIBUTE` (lines 333-343).
- It sets `fieldView?.value = entryInfoValue` (line 345).
- The edit side reads the field back by the same tag: `getUrlFromView()` (lines 459-469).

## 4. Where `TextFieldView` is created and linkified

`TemplateView.buildLinearTextView` (`view/TemplateView.kt:51-123`):

- creates a `TextFieldView`, or a `PasswordTextFieldView`, `OtpTextFieldView` or `PasskeyTextFieldView` chosen from the attribute label (lines 57-72);
- sets the label (line 89): `templateAttribute.alias ?: TemplateField.getLocalizedName(context, field.name)`;
- line 92 holds the comment `// TODO Linkify`;
- sets the value (line 93): `value = field.protectedValue.charArrayValue`, with the comment "Here the value is often empty".

`TextFieldView` (`view/TextFieldView.kt`):

- the `value` setter (lines 212-222) writes the text and calls `changeProtectedValueParameters()`;
- `changeProtectedValueParameters` (lines 260-285) calls `linkify()` at line 273 (protected field, revealed) and line 281 (not protected);
- `linkify()` (lines 287-301) branches only on `labelView.text.contains(APPLICATION_ID_FIELD_NAME)`; otherwise it calls `LinkifyCompat.addLinks(valueView, Linkify.WEB_URLS or Linkify.EMAIL_ADDRESSES)` (line 298).

`TextFieldView` does not read its own `tag`, and has no property that says which field it is.

## 5. Order of events (from reading the code, not observed)

1. `buildLinearTextView` runs; inside it `value = ...` (`TemplateView.kt:93`) triggers `linkify()`.
2. `buildLinearTextView` returns; **then** `itemView?.tag = fieldTag` runs (`TemplateAbstractView.kt:264`).
3. Later, `populateEntryFieldView` sets the real value (line 345), which triggers `linkify()` again.

So by this reading the first `linkify()` call happens when the view's `tag` is still unset, and the call that carries the real URL value happens after the tag is set.

## 6. An existing "link" marker on template attributes

- `TemplateAttributeOption.isLink()` and `setLink()` exist (`database/element/template/TemplateAttributeOption.kt:108-118`).
- `setLink(true)` is called for `Template.URL_ATTRIBUTE` (`Template.kt:162`) and for custom-template attribute types "InlineURL" (`TemplateEngineCompatible.kt:149-151`) and "RichTextBox" (lines 161-165).
- A search of all `*.kt` files found **no call to `isLink()`**. The marker is written but no code reads it.

## Not covered

- `TemplateEditView` and the edit-mode text view classes.
- `GenericTextFieldView` and `TemplateField.getLocalizedName`.
- Whether the first `linkify()` call really sees an unset tag at run time.
- Other places that read `FIELD_URL_TAG`.
