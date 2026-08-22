package org.eigentime.timelogger

import android.content.Context
import android.content.Intent
import android.content.pm.ShortcutInfo
import android.content.pm.ShortcutManager
import android.graphics.drawable.Icon
import android.os.Build

/**
 * 长按启动图标的动态快捷方式：前三个建议标签各一条，点一下＝一次一键写入。
 * 标签是用户数据，所以只能动态生成，不能写进 res/xml/shortcuts.xml。
 */
object ShortcutSync {

    fun sync(context: Context, mirror: Mirror) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N_MR1) return
        val manager = context.getSystemService(ShortcutManager::class.java) ?: return
        val tags = mirror.suggestTags.take(3)
        val list = tags.mapIndexed { index, tag ->
            val intent = Intent(context, QuickWriteActivity::class.java).apply {
                action = Actions.WRITE
                putExtra(Actions.EXTRA_TAG, tag)
                // 快捷方式必须携带 NEW_TASK：它是从启动器直接拉起来的。
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
            ShortcutInfo.Builder(context, "tag-$index")
                .setShortLabel(tag)
                .setLongLabel(tag)
                .setIcon(Icon.createWithResource(context, R.drawable.ic_stat_timelogger))
                .setIntent(intent)
                .setRank(index)
                .build()
        }
        val settings = ShortcutInfo.Builder(context, "shell-settings")
            .setShortLabel(context.getString(R.string.shortcut_settings_short))
            .setLongLabel(context.getString(R.string.settings_title))
            .setIcon(Icon.createWithResource(context, R.drawable.ic_stat_timelogger))
            .setIntent(
                Intent(context, SettingsActivity::class.java).apply {
                    action = Intent.ACTION_VIEW
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
            )
            .setRank(list.size)
            .build()
        try {
            manager.dynamicShortcuts = list + settings
        } catch (e: Exception) {
            // 超过系统上限或频率限制时放弃即可，快捷方式不是关键路径。
        }
    }
}

object Actions {
    const val WRITE = "org.eigentime.timelogger.action.WRITE"
    const val REPLY = "org.eigentime.timelogger.action.REPLY"
    const val UNDO = "org.eigentime.timelogger.action.UNDO"
    const val REFRESH = "org.eigentime.timelogger.action.REFRESH"
    const val OPEN_FORM = "org.eigentime.timelogger.action.OPEN_FORM"
    const val DISABLE_ONGOING = "org.eigentime.timelogger.action.DISABLE_ONGOING"
    const val EXTRA_TAG = "tag"
    const val EXTRA_PREFILL = "prefill_tag"
    const val REPLY_KEY = "reply_what"
}
