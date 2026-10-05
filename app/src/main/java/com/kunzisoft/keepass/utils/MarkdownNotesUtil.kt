/*
 * Copyright 2026 Christian Prior-Mamulyan.
 *
 * This file is part of KeePassDX.
 *
 *  KeePassDX is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  KeePassDX is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with KeePassDX.  If not, see <http://www.gnu.org/licenses/>.
 *
 */
package com.kunzisoft.keepass.utils

import com.kunzisoft.keepass.view.TemplateAbstractView

/** The fields of an entry that can be shown as Markdown. Only the notes are a candidate. */
enum class MarkdownField { NOTES }

/**
 * The feature flags of the Markdown rendering. They are constants, not settings: a build decides, the user does not.
 * An empty [fields] set switches the rendering off everywhere. The code stays, nothing is rendered.
 */
class MarkdownConfig(
    val fields: Set<MarkdownField> = setOf(MarkdownField.NOTES)
)

/** The flags of this build. */
val MARKDOWN_CONFIG = MarkdownConfig()

object MarkdownNotesUtil {

    /** The field that a view of the entry shows, by the tag the template gives it, or null for any other field. */
    fun markdownFieldOf(fieldTag: Any?): MarkdownField? = when (fieldTag) {
        TemplateAbstractView.FIELD_NOTES_TAG -> MarkdownField.NOTES
        else -> null
    }

    /** True if the field with this tag is shown as Markdown with the given flags. */
    fun shows(fieldTag: Any?, config: MarkdownConfig = MARKDOWN_CONFIG): Boolean =
        markdownFieldOf(fieldTag) in config.fields
}
