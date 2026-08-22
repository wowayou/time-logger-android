package org.eigentime.timelogger

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.view.View
import android.widget.RemoteViews

/**
 * 主屏小组件：一屏放 4 个常用标签，点一下＝追认「上次记录 → 现在」。
 *
 * 它只读显示镜像（契约 §6），一行业务逻辑都没有：标签是谁、上一条是什么、距上次
 * 多久，全是 JS 侧算好写进镜像的。
 */
class TimeLoggerWidget : AppWidgetProvider() {

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val mirror = Mirror.read(context)
        ids.forEach { id -> manager.updateAppWidget(id, build(context, mirror)) }
        // 刚放上桌面时可能还没有镜像（用户从未打开过应用）：让桥算一次。
        if (mirror.nextStartTs.isEmpty()) QuickWrite.refreshMirror(context)
    }

    override fun onEnabled(context: Context) {
        QuickWrite.refreshMirror(context)
    }

    companion object {
        private val SLOTS = intArrayOf(R.id.w_tag0, R.id.w_tag1, R.id.w_tag2, R.id.w_tag3)

        fun updateAll(context: Context, mirror: Mirror) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, TimeLoggerWidget::class.java))
            if (ids.isEmpty()) return
            val views = build(context, mirror)
            ids.forEach { manager.updateAppWidget(it, views) }
        }

        private fun build(context: Context, mirror: Mirror): RemoteViews {
            val views = RemoteViews(context.packageName, R.layout.widget)
            bindElapsed(context, views, mirror)
            val last = when {
                mirror.lastWhat.isNotBlank() ->
                    "${Mirror.parseLocal(mirror.lastTs)?.let { QuickWrite.hhmm(mirror.lastTs) } ?: ""} ${mirror.lastWhat}".trim()
                mirror.lastTag.isNotBlank() -> "#${mirror.lastTag}"
                else -> ""
            }
            views.setTextViewText(R.id.w_last, last)
            views.setViewVisibility(R.id.w_last, if (last.isBlank()) View.GONE else View.VISIBLE)

            val tags = mirror.suggestTags
            SLOTS.forEachIndexed { index, viewId ->
                val tag = tags.getOrNull(index)
                if (tag == null) {
                    views.setTextViewText(viewId, "")
                    views.setViewVisibility(viewId, View.INVISIBLE)
                    views.setOnClickPendingIntent(viewId, null)
                } else {
                    views.setViewVisibility(viewId, View.VISIBLE)
                    views.setTextViewText(viewId, tag)
                    views.setOnClickPendingIntent(viewId, writeIntent(context, tag, index))
                }
            }
            // 第二排全空时整排收起，避免小尺寸下留一条空轨道。
            views.setViewVisibility(
                R.id.w_row2,
                if (tags.size > 2) View.VISIBLE else View.GONE
            )
            views.setOnClickPendingIntent(R.id.w_open, openIntent(context))
            views.setOnClickPendingIntent(R.id.w_status, openIntent(context))
            return views
        }

        /**
         * 「距上次记录多久」这一行。RemoteViews 只在写入、应用回到前台或 30 分钟周期时
         * 重画，用普通 TextView 写死一个「25 分」会一直冻在那里；Chronometer 由系统在
         * 宿主进程里自己走秒，**不需要任何唤醒或定时器**，代价是格式变成 mm:ss / h:mm:ss。
         * 拿不到起点（没打开过应用）时退回文字提示。
         */
        private fun bindElapsed(context: Context, views: RemoteViews, mirror: Mirror) {
            val startMs = Mirror.parseLocal(mirror.nextStartTs)
            if (startMs == null) {
                views.setViewVisibility(R.id.w_chrono, View.GONE)
                views.setViewVisibility(R.id.w_status, View.VISIBLE)
                views.setTextViewText(R.id.w_status, mirror.statusLine(context))
                return
            }
            views.setViewVisibility(R.id.w_status, View.GONE)
            views.setViewVisibility(R.id.w_chrono, View.VISIBLE)
            // Chronometer 的 base 是 SystemClock.elapsedRealtime() 轴上的时刻，
            // 要把壁钟差值换算过去。
            val base = android.os.SystemClock.elapsedRealtime() - (System.currentTimeMillis() - startMs)
            views.setChronometer(R.id.w_chrono, base, context.getString(R.string.status_since), true)
        }

        private fun writeIntent(context: Context, tag: String, index: Int): PendingIntent {
            val intent = Intent(context, QuickWriteActivity::class.java).apply {
                action = Actions.WRITE
                putExtra(Actions.EXTRA_TAG, tag)
                // data 参与 PendingIntent 的等价判定：不加它，四个槽会互相覆盖成同一个标签。
                data = android.net.Uri.parse("timelogger://write/$index/${android.net.Uri.encode(tag)}")
            }
            return PendingIntent.getActivity(
                context, 1000 + index, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        }

        private fun openIntent(context: Context): PendingIntent =
            PendingIntent.getActivity(
                context, 900,
                Intent(context, MainActivity::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
    }
}
