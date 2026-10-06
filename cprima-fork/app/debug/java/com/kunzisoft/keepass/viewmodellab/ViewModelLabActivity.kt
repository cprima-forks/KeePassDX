package com.kunzisoft.keepass.viewmodellab

import android.app.Activity
import android.graphics.Typeface
import android.os.Bundle
import android.util.Log
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.text.method.PasswordTransformationMethod
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.kunzisoft.keepass.viewmodel.Finding
import com.kunzisoft.keepass.viewmodel.Input
import com.kunzisoft.keepass.viewmodel.Mode
import com.kunzisoft.keepass.viewmodel.NormalizedRecord
import com.kunzisoft.keepass.viewmodel.RenderedRecord
import com.kunzisoft.keepass.viewmodel.RenderedValue
import com.kunzisoft.keepass.viewmodel.SchemaSet
import com.kunzisoft.keepass.viewmodel.ViewModelBuilder
import com.kunzisoft.keepass.viewmodel.ViewModelSamples

/**
 * ViewModelLab (spike, requirements: wiki page Requirements-Entry-View-Model, VM-060). It shows one sample entry in
 * three parts, in this order: the rendered view, the rendered edit, and the technical blocks (stored fields,
 * normalised record, the view model as text). Both renderers build from a view model alone and know no entity
 * type. The edit changes an in-memory copy of the record and shows the findings of the validation live; nothing is
 * written back to any store.
 *
 * Debug build only, no launcher entry:
 * `adb shell am start -n com.kunzisoft.keepass.cprima_fork/com.kunzisoft.keepass.viewmodellab.ViewModelLabActivity --es case-id bank-account`
 * The case ids are those of [ViewModelSamples.all]. The real entry screen is not touched (VM-061).
 */
class ViewModelLabActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)

        val caseId = intent.getStringExtra(EXTRA_CASE_ID) ?: ViewModelSamples.bankAccount.id
        val sample = ViewModelSamples.all.firstOrNull { it.id == caseId } ?: ViewModelSamples.bankAccount

        val schemas = SchemaSet.load { path ->
            try {
                assets.open("${ViewModelSamples.SCHEMA_DIRECTORY}/$path").bufferedReader().use { it.readText() }
            } catch (e: java.io.IOException) {
                null
            }
        }
        val builder = ViewModelBuilder(schemas)
        val record = ViewModelSamples.record(sample)
        val view = builder.build(record)
        val editView = builder.build(record, Mode.EDIT)

        val content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        content.addView(heading("ViewModelLab: ${sample.id}"))
        content.addView(heading("Rendered view"))
        content.addView(render(view))
        content.addView(heading("Rendered edit"))
        content.addView(renderEdit(record, editView, builder))
        content.addView(heading("Technical"))
        content.addView(block("Stored fields", sample.fields.entries.joinToString("\n") { "${it.key} = ${it.value}" }))
        content.addView(
            block(
                "Normalised record",
                "id: ${record.id}\nschemas: ${record.schemas.joinToString(", ")}\n" +
                    record.properties.entries.joinToString("\n") { "  ${it.key} = ${it.value}" }
            )
        )
        content.addView(block("View model, view (text)", view.toText().trimEnd()))
        content.addView(block("View model, edit (text)", editView.toText().trimEnd()))

        val scroll = ScrollView(this).apply { addView(content) }
        ViewCompat.setOnApplyWindowInsetsListener(scroll) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(bars.left + dp(16), bars.top + dp(8), bars.right + dp(16), bars.bottom + dp(8))
            WindowInsetsCompat.CONSUMED
        }
        setContentView(scroll)

        Log.i(
            TAG,
            "VIEWMODELLAB_DONE case=${sample.id} title=${view.title} sections=${view.sections.size} " +
                "editRows=${editView.sections.sumOf { it.rows.size }} findings=${view.findings.size}"
        )
    }

    /** The generic renderer: it reads the view model only. No entity type, no field name is known here. */
    private fun render(view: RenderedRecord): View {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        box.addView(TextView(this).apply {
            text = view.title
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            setTypeface(typeface, Typeface.BOLD)
        })
        for (section in view.sections) {
            box.addView(TextView(this).apply {
                text = if (section.collapsed) "${section.label} (collapsed)" else section.label
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                setTypeface(typeface, Typeface.BOLD)
                setPadding(0, dp(16), 0, dp(4))
            })
            for (row in section.rows) {
                box.addView(TextView(this).apply {
                    text = row.label
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                    alpha = 0.7f
                })
                box.addView(TextView(this).apply {
                    text = when (val value = row.value) {
                        is RenderedValue.Text -> value.text
                        RenderedValue.Protected -> "••••••••"
                    }
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                    if (!row.multiline) setSingleLine(false)
                    setTextIsSelectable(row.copy)
                })
            }
        }
        if (view.findings.isNotEmpty()) {
            box.addView(TextView(this).apply {
                text = "Findings"
                setTypeface(typeface, Typeface.BOLD)
                setPadding(0, dp(16), 0, dp(4))
            })
            view.findings.forEach { box.addView(TextView(this).apply { text = describe(it) }) }
        }
        return box
    }

    /**
     * The generic edit renderer: one input per row of the edit view model. A secret row is hidden and has a reveal
     * button; its text is taken from the record, because the view model holds no secret (VM-041, VM-042). Every change
     * updates the in-memory copy of the record and the findings below; nothing is saved.
     */
    private fun renderEdit(record: NormalizedRecord, edit: RenderedRecord, builder: ViewModelBuilder): View {
        val values = LinkedHashMap(record.properties)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val findings = TextView(this).apply { typeface = Typeface.MONOSPACE; setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f) }

        fun refresh() {
            val changed = NormalizedRecord(record.id, record.schemas, values.filterValues { it.isNotEmpty() }, record.protectedNames)
            val now = builder.build(changed, Mode.EDIT).findings
            findings.text = if (now.isEmpty()) "No findings." else now.joinToString("\n") { describe(it) }
        }

        box.addView(TextView(this).apply {
            text = "An edit stays in memory. Nothing is saved."
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            alpha = 0.7f
        })
        for (section in edit.sections) {
            box.addView(TextView(this).apply {
                text = section.label
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                setTypeface(typeface, Typeface.BOLD)
                setPadding(0, dp(16), 0, dp(4))
            })
            for (row in section.rows) {
                box.addView(TextView(this).apply {
                    text = if (row.required) "${row.label} *" else row.label
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                    alpha = 0.7f
                })
                val input = EditText(this).apply {
                    setText(values[row.attribute].orEmpty())
                    when (row.input) {
                        Input.SECRET -> {
                            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                            transformationMethod = PasswordTransformationMethod.getInstance()
                        }
                        Input.MULTILINE -> {
                            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
                            minLines = 3
                            gravity = android.view.Gravity.TOP
                        }
                        Input.DATE -> {
                            inputType = InputType.TYPE_CLASS_DATETIME or InputType.TYPE_DATETIME_VARIATION_DATE
                            hint = "YYYY-MM-DD"
                        }
                        Input.TEXT -> inputType = InputType.TYPE_CLASS_TEXT
                    }
                    addTextChangedListener(object : TextWatcher {
                        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
                        override fun afterTextChanged(s: Editable?) {
                            values[row.attribute] = s?.toString().orEmpty()
                            refresh()
                        }
                    })
                }
                box.addView(input)
                if (row.input == Input.SECRET) {
                    box.addView(Button(this).apply {
                        text = "Show"
                        setOnClickListener {
                            val hidden = input.transformationMethod != null
                            input.transformationMethod = if (hidden) null else PasswordTransformationMethod.getInstance()
                            text = if (hidden) "Hide" else "Show"
                        }
                    })
                }
            }
        }
        box.addView(TextView(this).apply {
            text = "Findings (live)"
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(16), 0, dp(4))
        })
        box.addView(findings)
        refresh()
        return box
    }

    private fun describe(finding: Finding) =
        "${finding.level}: ${finding.entity} ${finding.message}${if (finding.objectPath.isEmpty()) "" else " at ${finding.objectPath}"}"

    private fun heading(text: String) = TextView(this).apply {
        this.text = text
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, dp(16), 0, dp(4))
    }

    private fun block(title: String, body: String) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        addView(heading(title))
        addView(TextView(this@ViewModelLabActivity).apply {
            text = body
            typeface = Typeface.MONOSPACE
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
        })
        layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    companion object {
        const val EXTRA_CASE_ID = "case-id"
        private const val TAG = "ViewModelLab"
    }
}
