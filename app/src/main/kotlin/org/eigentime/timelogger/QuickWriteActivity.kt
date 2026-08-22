package org.eigentime.timelogger

import android.content.Intent
import android.os.Bundle
import android.widget.Toast

/**
 * 完全不可见的宿主：小组件 / 磁贴 / 快捷方式点下来的一键写入在这里执行。
 *
 * 为什么要一个 Activity 而不是纯广播：写入要跑真实的 web 模块，也就是要一个
 * WebView；WebView 需要主线程与一个活着的进程。Activity 启动是系统保证会拉起
 * 进程的路径，广播则可能在 evaluateJavascript 回来之前就被回收。主题是全透明、
 * 无动画、noHistory，所以用户看不到任何界面闪动。
 */
class QuickWriteActivity : android.app.Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val tag = intent?.getStringExtra(Actions.EXTRA_TAG)
        // 可选的 what：给「快捷方式带一句话」与自动验收用；语义与通知直接回复完全一致
        // （文本里的 `#标签` 优先于这里的 tag，判断在桥里）。
        val what = intent?.getStringExtra(Actions.EXTRA_WHAT)
        if (tag.isNullOrBlank() && what.isNullOrBlank()) {
            finish()
            return
        }
        QuickWrite.perform(this, tag.orEmpty(), what) { out ->
            runOnUiThread {
                Toast.makeText(this, QuickWrite.message(this, out), Toast.LENGTH_LONG).show()
                if (out.ok) {
                    // 点错标签是这个入口最可能的失误：给一条 20 秒后自动消失的
                    // 撤销通知，而不是把撤销藏进应用里。
                    ResultNotifier.showUndo(this, out)
                } else if (QuickWrite.needsForm(out)) {
                    // 守卫拦下时不代替用户决定：打开表单，让他确认起点（契约 §4）。
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
