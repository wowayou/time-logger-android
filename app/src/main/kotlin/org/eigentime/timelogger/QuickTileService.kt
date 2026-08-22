package org.eigentime.timelogger

import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService

/**
 * 快捷设置磁贴：下拉通知栏点一下 → 弹出标签选择 → 再点一下就记完。
 *
 * 磁贴只有一个动作位，所以它不直接写入——「用哪个标签」是必须由人回答的问题，
 * 替用户猜一个默认标签写下去，正是契约 §4 要拦的那类静默写入。
 */
class QuickTileService : TileService() {

    override fun onStartListening() {
        super.onStartListening()
        val mirror = Mirror.read(this)
        qsTile?.apply {
            label = getString(R.string.tile_label)
            state = Tile.STATE_ACTIVE
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                subtitle = mirror.statusLine(this@QuickTileService)
            }
            updateTile()
        }
    }

    override fun onClick() {
        super.onClick()
        val intent = Intent(this, QuickPickActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            val pending = PendingIntent.getActivity(
                this, 600, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            startActivityAndCollapse(pending)
        } else {
            @Suppress("DEPRECATION")
            startActivityAndCollapse(intent)
        }
    }
}
