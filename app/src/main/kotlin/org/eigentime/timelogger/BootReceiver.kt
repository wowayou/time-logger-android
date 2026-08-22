package org.eigentime.timelogger

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * 开机与自我升级后把外围表面重建一次：常驻通知不会自己回来，小组件的文字也
 * 停在重启前那一刻。这里不写任何数据，只重画。
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Surfaces.refreshAll(context)
    }
}
