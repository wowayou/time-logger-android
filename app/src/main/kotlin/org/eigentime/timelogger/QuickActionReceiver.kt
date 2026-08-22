package org.eigentime.timelogger

import android.app.RemoteInput
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.widget.Toast

/**
 * 通知里的动作：一键写入、直接回复、撤销、关闭常驻入口。
 *
 * 直接回复必须走广播（系统要用 PendingIntent 的结果回填 RemoteInput 状态），
 * 所以这条路不能像小组件那样用 Activity。goAsync 把接收器的生命期延长到写入完成，
 * 否则 evaluateJavascript 的回调可能落在已经结束的接收器上。
 */
class QuickActionReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val app = context.applicationContext
        when (intent.action) {
            Actions.WRITE, Actions.REPLY -> {
                val tag = intent.getStringExtra(Actions.EXTRA_TAG).orEmpty()
                val typed = RemoteInput.getResultsFromIntent(intent)
                    ?.getCharSequence(Actions.REPLY_KEY)?.toString()?.trim()
                if (tag.isBlank() && typed.isNullOrBlank()) return
                val pending = goAsync()
                // 直接回复里用户敲的是「做了什么」；标签仍取通知携带的那个。
                QuickWrite.perform(app, tag, typed) { out ->
                    toast(app, QuickWrite.message(app, out))
                    if (out.ok) ResultNotifier.showUndo(app, out)
                    OngoingNotifier.refresh(app, Mirror.read(app))
                    pending.finish()
                }
            }

            Actions.UNDO -> {
                val pending = goAsync()
                QuickWrite.undo(app) { out ->
                    val msg = when {
                        out.ok -> app.getString(R.string.undone)
                        out.reason == "changed-since" -> app.getString(R.string.undo_changed)
                        out.reason == "nothing-to-undo" -> app.getString(R.string.undo_none)
                        else -> QuickWrite.message(app, out)
                    }
                    toast(app, msg)
                    ResultNotifier.dismiss(app)
                    pending.finish()
                }
            }

            Actions.DISABLE_ONGOING -> {
                AndroidPrefs.setOngoingEnabled(app, false)
                OngoingNotifier.cancel(app)
            }

            Actions.REFRESH -> Surfaces.refreshAll(app)
        }
    }

    private fun toast(context: Context, message: String) {
        Handler(Looper.getMainLooper()).post {
            Toast.makeText(context, message, Toast.LENGTH_LONG).show()
        }
    }
}
