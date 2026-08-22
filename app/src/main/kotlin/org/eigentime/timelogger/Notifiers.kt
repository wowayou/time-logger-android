package org.eigentime.timelogger

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.RemoteInput

private const val CHANNEL_ONGOING = "ongoing"
private const val CHANNEL_RESULT = "result"
private const val ID_ONGOING = 1
private const val ID_RESULT = 2

private fun ensureChannels(context: Context) {
    val manager = context.getSystemService(NotificationManager::class.java) ?: return
    if (manager.getNotificationChannel(CHANNEL_ONGOING) == null) {
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ONGOING,
                context.getString(R.string.notif_channel_ongoing),
                NotificationManager.IMPORTANCE_LOW   // 常驻入口不该响、不该弹
            ).apply {
                description = context.getString(R.string.notif_channel_ongoing_desc)
                setShowBadge(false)
            }
        )
    }
    if (manager.getNotificationChannel(CHANNEL_RESULT) == null) {
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_RESULT,
                context.getString(R.string.notif_channel_result),
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = context.getString(R.string.notif_channel_result_desc) }
        )
    }
}

private fun canPost(context: Context): Boolean =
    NotificationManagerCompat.from(context).areNotificationsEnabled()

private fun broadcast(context: Context, action: String, requestCode: Int, tag: String? = null): PendingIntent {
    val intent = Intent(context, QuickActionReceiver::class.java).apply {
        this.action = action
        if (tag != null) putExtra(Actions.EXTRA_TAG, tag)
        data = android.net.Uri.parse("timelogger://action/$action/${tag.orEmpty()}")
    }
    return PendingIntent.getBroadcast(
        context, requestCode, intent,
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
    )
}

/**
 * 常驻通知：从任何界面下拉一次就能记一条，直接回复框是安卓上**输入自由文本阻力
 * 最低**的形态（不切应用、不等冷启动）。低优先级、静音、不占角标。
 */
object OngoingNotifier {

    fun refresh(context: Context, mirror: Mirror) {
        if (!AndroidPrefs.ongoingEnabled(context) || !canPost(context)) {
            cancel(context)
            return
        }
        ensureChannels(context)
        val tags = mirror.suggestTags
        val builder = NotificationCompat.Builder(context, CHANNEL_ONGOING)
            .setSmallIcon(R.drawable.ic_stat_timelogger)
            .setContentTitle(mirror.statusLine(context))
            .setContentText(
                if (mirror.lastWhat.isNotBlank())
                    "${QuickWrite.hhmm(mirror.lastTs)} ${mirror.lastWhat}"
                else mirror.lastTag.let { if (it.isBlank()) "" else "#$it" }
            )
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)  // 锁屏不展示记录内容
            .setContentIntent(
                PendingIntent.getActivity(
                    context, 800, Intent(context, MainActivity::class.java),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
            )
        // 展开态放标签网格：系统只给 3 个 action 位，标签塞在 action 里必然放不下
        // （真机反馈：「没办法选更多的标签」）。自定义视图里的按钮不受这个限制，
        // DecoratedCustomViewStyle 会把它套进系统模板，Android 12+ 亦然。
        if (tags.size > 2) {
            builder.setStyle(NotificationCompat.DecoratedCustomViewStyle())
            builder.setCustomBigContentView(tagGrid(context, mirror))
        }
        // 折叠态仍然只有 3 个动作：两个最常用标签 + 直接回复。
        tags.take(2).forEachIndexed { index, tag ->
            builder.addAction(
                NotificationCompat.Action.Builder(0, tag, broadcast(context, Actions.WRITE, 700 + index, tag)).build()
            )
        }
        val replyTag = tags.firstOrNull()
        if (replyTag != null) {
            val input = RemoteInput.Builder(Actions.REPLY_KEY)
                .setLabel(context.getString(R.string.notif_reply_hint))
                .build()
            builder.addAction(
                NotificationCompat.Action.Builder(
                    0, context.getString(R.string.notif_reply_label),
                    broadcast(context, Actions.REPLY, 710, replyTag)
                ).addRemoteInput(input).setAllowGeneratedReplies(false).build()
            )
        }
        try {
            NotificationManagerCompat.from(context).notify(ID_ONGOING, builder.build())
        } catch (e: SecurityException) {
            // 权限被撤销时静默退出：这是入口，不是数据。
        }
    }

    private val GRID_SLOTS = intArrayOf(
        R.id.n_tag0, R.id.n_tag1, R.id.n_tag2, R.id.n_tag3, R.id.n_tag4, R.id.n_tag5
    )

    /** 展开态的标签网格。只读镜像里的建议标签（契约 §6），呈现而已。 */
    private fun tagGrid(context: Context, mirror: Mirror): android.widget.RemoteViews {
        val views = android.widget.RemoteViews(context.packageName, R.layout.notif_tags)
        views.setTextViewText(R.id.n_hint, mirror.statusLine(context))
        val tags = mirror.suggestTags
        GRID_SLOTS.forEachIndexed { index, id ->
            val tag = tags.getOrNull(index)
            if (tag == null) {
                views.setViewVisibility(id, android.view.View.INVISIBLE)
                views.setOnClickPendingIntent(id, null)
            } else {
                views.setViewVisibility(id, android.view.View.VISIBLE)
                views.setTextViewText(id, tag)
                views.setOnClickPendingIntent(id, broadcast(context, Actions.WRITE, 730 + index, tag))
            }
        }
        views.setViewVisibility(
            R.id.n_row2,
            if (tags.size > 3) android.view.View.VISIBLE else android.view.View.GONE
        )
        return views
    }

    fun cancel(context: Context) {
        NotificationManagerCompat.from(context).cancel(ID_ONGOING)
    }
}

/** 一键写入后的确认 + 撤销，20 秒后自己消失。 */
object ResultNotifier {

    fun showUndo(context: Context, out: QuickWrite.Outcome) {
        if (!canPost(context)) return
        ensureChannels(context)
        val builder = NotificationCompat.Builder(context, CHANNEL_RESULT)
            .setSmallIcon(R.drawable.ic_stat_timelogger)
            .setContentTitle(QuickWrite.message(context, out))
            .setSilent(true)
            .setShowWhen(false)
            .setAutoCancel(true)
            .setTimeoutAfter(20_000)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)
            .addAction(
                NotificationCompat.Action.Builder(
                    0, context.getString(R.string.undo), broadcast(context, Actions.UNDO, 720)
                ).build()
            )
        try {
            NotificationManagerCompat.from(context).notify(ID_RESULT, builder.build())
        } catch (e: SecurityException) {
        }
    }

    fun dismiss(context: Context) {
        NotificationManagerCompat.from(context).cancel(ID_RESULT)
    }
}
