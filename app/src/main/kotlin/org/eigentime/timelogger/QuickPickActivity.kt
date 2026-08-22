package org.eigentime.timelogger

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/**
 * 标签选择（磁贴与「打开应用自己填」之间的那一层）。刻意不是列表：建议标签只有
 * 4–6 个，做成大号触控行比滚动列表快。
 */
class QuickPickActivity : android.app.Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_quick_pick)
        window.setGravity(Gravity.BOTTOM)
        window.setLayout(
            android.view.WindowManager.LayoutParams.MATCH_PARENT,
            android.view.WindowManager.LayoutParams.WRAP_CONTENT
        )

        val mirror = Mirror.read(this)
        findViewById<TextView>(R.id.p_status).text = mirror.statusLine(this)
        val container = findViewById<LinearLayout>(R.id.p_tags)
        val density = resources.displayMetrics.density
        mirror.suggestTags.take(6).forEach { tag ->
            val row = TextView(this, null, 0, R.style.PickChip)
            row.text = tag
            row.setOnClickListener { write(tag) }
            // style 里的 layout_* 对**程序化创建**的 View 无效（没有 XML 父级来解析
            // LayoutParams），所以高度和外边距必须在这里给，否则行会挤成 wrap_content。
            row.layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, (56 * density).toInt()
            ).apply { topMargin = (8 * density).toInt() }
            container.addView(row)
        }
        findViewById<TextView>(R.id.p_open).setOnClickListener {
            startActivity(
                Intent(this, MainActivity::class.java).apply {
                    action = Actions.OPEN_FORM
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
            )
            finish()
        }
    }

    private fun write(tag: String) {
        QuickWrite.perform(this, tag) { out ->
            runOnUiThread {
                Toast.makeText(this, QuickWrite.message(this, out), Toast.LENGTH_LONG).show()
                if (out.ok) ResultNotifier.showUndo(this, out)
                else if (QuickWrite.needsForm(out)) {
                    startActivity(
                        Intent(this, MainActivity::class.java).apply {
                            action = Actions.WRITE
                            putExtra(Actions.EXTRA_PREFILL, tag)
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                    )
                }
                finish()
            }
        }
    }
}
