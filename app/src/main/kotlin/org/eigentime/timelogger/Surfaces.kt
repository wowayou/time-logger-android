package org.eigentime.timelogger

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * 「外围表面」＝小组件、常驻通知、动态快捷方式。它们只读显示镜像（契约 §6），
 * 所以刷新永远是同一件事：读镜像 → 重画。
 */
object Surfaces {

    private val main = Handler(Looper.getMainLooper())

    fun refreshAll(context: Context) {
        val app = context.applicationContext
        // Store 的变更通知可能来自 JavaBridge 线程；RemoteViews / 通知都要主线程。
        main.post {
            val mirror = Mirror.read(app)
            TimeLoggerWidget.updateAll(app, mirror)
            OngoingNotifier.refresh(app, mirror)
            ShortcutSync.sync(app, mirror)
        }
    }

    fun widgetIds(context: Context): IntArray =
        AppWidgetManager.getInstance(context)
            .getAppWidgetIds(ComponentName(context, TimeLoggerWidget::class.java))
}
