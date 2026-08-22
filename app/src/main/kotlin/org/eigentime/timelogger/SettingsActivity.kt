package org.eigentime.timelogger

import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast

/**
 * 壳自己的设置：只有原生入口相关的三项。产品设置（主题、语言、标签、格言……）
 * 全在 web 界面里，这里一个都不重复——重复一次就是两处真相。
 *
 * 布局用代码搭而不是 XML：三行开关不值得一套资源文件。
 */
class SettingsActivity : android.app.Activity() {

    private lateinit var rows: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this)
        scroll.setBackgroundColor(0xFF0E0F13.toInt())
        rows = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(28), dp(20), dp(28))
        }
        scroll.addView(rows)
        setContentView(scroll)
        render()
    }

    private fun render() {
        rows.removeAllViews()
        title(getString(R.string.settings_title))

        toggle(
            getString(R.string.settings_ongoing),
            getString(R.string.settings_ongoing_hint),
            AndroidPrefs.ongoingEnabled(this)
        ) {
            AndroidPrefs.setOngoingEnabled(this, !AndroidPrefs.ongoingEnabled(this))
            Surfaces.refreshAll(this)
            render()
        }

        toggle(
            getString(R.string.settings_show_what),
            getString(R.string.settings_show_what_hint),
            AndroidPrefs.showLastWhat(this)
        ) {
            AndroidPrefs.setShowLastWhat(this, !AndroidPrefs.showLastWhat(this))
            // 镜像里存着 lastWhat，改了偏好要重算一次才生效。
            QuickWrite.refreshMirror(this) { Surfaces.refreshAll(this) }
            render()
        }

        val gap = AndroidPrefs.maxSilentGapMinutes(this)
        row(
            getString(R.string.settings_gap),
            getString(R.string.settings_gap_hint, formatDuration(this, gap))
        ) {
            val steps = intArrayOf(60, 120, 240, 480)
            val next = steps[(steps.indexOf(gap).takeIf { it >= 0 } ?: 2).plus(1) % steps.size]
            AndroidPrefs.setMaxSilentGapMinutes(this, next)
            QuickWrite.refreshMirror(this) { Surfaces.refreshAll(this) }
            render()
        }

        row(getString(R.string.settings_recompute), getString(R.string.settings_recompute_hint)) {
            QuickWrite.refreshMirror(this) { ok ->
                runOnUiThread {
                    Toast.makeText(
                        this,
                        if (ok) R.string.settings_recomputed else R.string.guard_timeout,
                        Toast.LENGTH_SHORT
                    ).show()
                    Surfaces.refreshAll(this)
                }
            }
        }

        // 诚实声明（维护者要求）：付费只买商店分发，功能与源码始终免费可得。
        // 放在壳设置最下方而不是首屏——它是事实说明，不是营销位。
        title(getString(R.string.about_title))
        row(getString(R.string.about_open_source), getString(R.string.about_repo)) {
            open("https://github.com/wowayou/time-logger-android")
        }
        row(getString(R.string.about_web), getString(R.string.about_paid_note)) {
            open("https://time.eigentime.org/")
        }

        val source = try {
            assets.open("app/RUNTIME_SOURCE.txt").use { it.readBytes().toString(Charsets.UTF_8) }
        } catch (e: Exception) {
            getString(R.string.runtime_missing)
        }
        val info = TextView(this).apply {
            text = source.trim()
            setTextColor(0xFF6E7484.toInt())
            textSize = 12f
            setPadding(0, dp(24), 0, 0)
        }
        rows.addView(info)
    }

    private fun title(text: String) {
        rows.addView(TextView(this).apply {
            this.text = text
            setTextColor(0xFFE8EAF0.toInt())
            textSize = 22f
            setPadding(0, 0, 0, dp(16))
        })
    }

    private fun row(label: String, hint: String, onClick: () -> Unit) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.chip_bg)
            setPadding(dp(16), dp(14), dp(16), dp(14))
            isClickable = true
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = dp(10) }
        }
        box.addView(TextView(this).apply {
            text = label
            setTextColor(0xFFE8EAF0.toInt())
            textSize = 16f
        })
        box.addView(TextView(this).apply {
            text = hint
            setTextColor(0xFF8B90A0.toInt())
            textSize = 13f
        })
        rows.addView(box)
    }

    private fun toggle(label: String, hint: String, on: Boolean, onClick: () -> Unit) {
        val state = getString(if (on) R.string.settings_on else R.string.settings_off)
        row("$label · $state", hint, onClick)
    }

    /** 打开外部链接。不需要 INTERNET 权限——取网页的是浏览器，不是我们。 */
    private fun open(url: String) {
        try {
            startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW,
                android.net.Uri.parse(url)))
        } catch (e: Exception) {
            Toast.makeText(this, url, Toast.LENGTH_LONG).show()
        }
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
}
