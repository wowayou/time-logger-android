package org.eigentime.timelogger

import android.content.Context
import org.json.JSONObject

/**
 * 壳自己的设备偏好，存在 `timelog.androidPrefs.v1`（契约 §4）：
 * **设备偏好不是用户数据**——不进备份、不随导入改变，与 web 端的 timelog.theme 同类。
 *
 * 这是原生侧唯一允许写入的键：它不属于时间线数据，JS 侧只读它。
 */
object AndroidPrefs {

    const val DEFAULT_MAX_SILENT_GAP = 240

    private fun read(context: Context): JSONObject = try {
        JSONObject(Store.get(context).getItem(Keys.PREFS) ?: "{}")
    } catch (e: Exception) {
        JSONObject()
    }

    private fun write(context: Context, o: JSONObject) {
        val old = Store.get(context).getItem(Keys.PREFS)
        val next = o.toString()
        if (Store.get(context).setItem(Keys.PREFS, next) == null && old != next) {
            Store.notifyChanged(Keys.PREFS, next, old, this)
        }
    }

    fun ongoingEnabled(context: Context): Boolean = read(context).optBoolean("ongoingNotification", true)

    fun setOngoingEnabled(context: Context, on: Boolean) {
        write(context, read(context).put("ongoingNotification", on))
    }

    fun showLastWhat(context: Context): Boolean = read(context).optBoolean("showLastWhatOnWidget", true)

    fun setShowLastWhat(context: Context, on: Boolean) {
        write(context, read(context).put("showLastWhatOnWidget", on))
    }

    fun notificationAsked(context: Context): Boolean = read(context).optBoolean("notificationAsked", false)

    fun setNotificationAsked(context: Context, asked: Boolean) {
        write(context, read(context).put("notificationAsked", asked))
    }

    fun maxSilentGapMinutes(context: Context): Int =
        read(context).optInt("maxSilentGapMinutes", DEFAULT_MAX_SILENT_GAP).let {
            if (it > 0) it else DEFAULT_MAX_SILENT_GAP
        }

    fun setMaxSilentGapMinutes(context: Context, minutes: Int) {
        write(context, read(context).put("maxSilentGapMinutes", minutes))
    }
}
