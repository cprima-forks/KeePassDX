package com.kunzisoft.keepass.linklab

import android.app.Activity
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.widget.TextView
import androidx.core.view.WindowCompat
import com.kunzisoft.keepass.R

/**
 * The legend of LinkLab: one screen, the condensed documentation of the tool. The wiki guide `LinkLab`
 * uses the same wording.
 */
class LabAboutActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.linklab_about)
        applyInsets(R.id.linklab_about_root, R.id.linklab_about_header, R.id.linklab_about_footer)
        findViewById<TextView>(R.id.linklab_about_text).text = legend()
        findViewById<TextView>(R.id.linklab_about_provenance).text =
            "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}) · ${Build.MODEL} · " +
                    "KeePassDX ${packageManager.getPackageInfo(packageName, 0).versionName} · schema ${LabSchema.VERSION}"
        // Opened by the launcher it is the start screen and leads on to the cases; opened from the cases it closes
        val button = findViewById<android.widget.Button>(R.id.linklab_about_close)
        if (intent.getBooleanExtra(EXTRA_FROM_LAB, false)) {
            button.text = "Close"
            button.setOnClickListener { finish() }
        } else {
            button.text = "Start"
            button.setOnClickListener {
                startActivity(Intent(this, LabActivity::class.java))
                finish()
            }
        }
    }

    companion object {
        const val EXTRA_FROM_LAB = "from-lab"
    }

    private fun legend(): String = """
LinkLab shows what Android does with a test value, one case at a time. It is a tool for evidence, not a test runner: it shows no pass or fail.

Header
The case (C-...), the requirements it belongs to (R-...), its level and a short title. The arrows move to the previous and the next case.

Stored value
The exact text of the test value. Invisible characters are written out, for example <U+202E>.

As KeePassDX shows it
The real KeePassDX field view. Tap a link to hand it to Android; long-press it to see the selection toolbar.

Links KeePassDX makes
The link spans on the text: the range, the linked text and the target.

Android classifier suggests
What the system text classifier returns for the link: the selection, the entity and actions such as Call. This is the data the selection toolbar is built from. It is not the toolbar.

Apps that answer the link
Installed apps that can open the target. Nothing is started.

Footer
Run probes repeats the probes for this case. Copy puts the records of the session (JSON lines) on the clipboard. Save writes them to the files of the app (linklab/<run>/diagnostics.jsonl). The last line says what you are looking at: Android version, device, app version, view kind, schema version and the hash of the test data.

This is the start screen. Start (below) opens the first case. From a computer:
adb shell am start -n $packageName/com.kunzisoft.keepass.linklab.LabActivity --es case-id C-PA-001

About LinkLab
A tool of the cprima fork of KeePassDX, made to collect evidence for a pull request about tel: links (fork issue #15). It exists in debug builds only and is not part of any KeePassDX release.
Author: Christian Prior-Mamulyan (cprima)
Source: https://github.com/cprima-forks/KeePassDX
""".trimIndent()
}
