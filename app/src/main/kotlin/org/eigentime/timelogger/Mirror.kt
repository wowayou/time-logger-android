package org.eigentime.timelogger

import android.content.Context
import org.json.JSONObject
import java.util.Calendar

/**
 * 显示镜像的**只读**视图（契约 §6）。原生侧不解析 timelog.v1；这里读的是 JS 侧
 * 算好并落库的那几个字段，本类只做纯格式化。
 */
data class Mirror(
    val computedAt: String,
    val nextStartTs: String,
    val lastTs: String,
    val lastWhat: String,
    val lastTag: String,
    val tailIsPlaceholder: Boolean,
    val gapMinutes: Int,
    val suggestTags: List<String>,
    val canQuickWrite: Boolean,
    val blockedReason: String
) {
    companion object {
        val EMPTY = Mirror("", "", "", "", "", false, -1, emptyList(), false, "no-mirror")

        fun read(context: Context): Mirror {
            val raw = Store.get(context).getItem(Keys.MIRROR) ?: return EMPTY
            return try {
                val o = JSONObject(raw)
                val tags = o.optJSONArray("suggestTags")
                Mirror(
                    computedAt = o.optString("computedAt"),
                    nextStartTs = o.optString("nextStartTs"),
                    lastTs = o.optString("lastTs"),
                    lastWhat = o.optString("lastWhat"),
                    lastTag = o.optString("lastTag"),
                    tailIsPlaceholder = o.optBoolean("tailIsPlaceholder"),
                    gapMinutes = o.optInt("gapMinutes", -1),
                    suggestTags = (0 until (tags?.length() ?: 0)).mapNotNull { tags?.optString(it) }
                        .filter { it.isNotBlank() },
                    canQuickWrite = o.optBoolean("canQuickWrite"),
                    blockedReason = o.optString("blockedReason")
                )
            } catch (e: Exception) {
                // 镜像是缓存，读坏了就当没有：下一次写入会重算（契约 §6）。
                EMPTY
            }
        }

        /** 'YYYY-MM-DDTHH:mm' 本地壁钟值 → 毫秒。不做时区转换（web 仓红线）。 */
        fun parseLocal(ts: String): Long? {
            if (ts.length < 16) return null
            return try {
                val y = ts.substring(0, 4).toInt()
                val mo = ts.substring(5, 7).toInt()
                val d = ts.substring(8, 10).toInt()
                val h = ts.substring(11, 13).toInt()
                val mi = ts.substring(14, 16).toInt()
                Calendar.getInstance().apply {
                    set(y, mo - 1, d, h, mi, 0)
                    set(Calendar.MILLISECOND, 0)
                }.timeInMillis
            } catch (e: Exception) {
                null
            }
        }
    }

    /** 距下一条记录起点已经过去多少分钟；镜像缺失或时钟异常时返回 -1。 */
    fun elapsedMinutes(nowMillis: Long = System.currentTimeMillis()): Int {
        val start = parseLocal(nextStartTs) ?: return -1
        val diff = ((nowMillis - start) / 60000L)
        return if (diff < 0) -1 else diff.toInt()
    }

    fun statusLine(context: Context, nowMillis: Long = System.currentTimeMillis()): String {
        val mins = elapsedMinutes(nowMillis)
        if (nextStartTs.isEmpty()) return context.getString(R.string.status_no_mirror)
        if (mins < 0) return context.getString(R.string.status_no_mirror)
        if (mins == 0) return context.getString(R.string.status_just_now)
        return context.getString(R.string.status_since, formatDuration(context, mins))
    }
}

fun formatDuration(context: Context, minutes: Int): String {
    val h = minutes / 60
    val m = minutes % 60
    return when {
        h == 0 -> context.getString(R.string.dur_m, m)
        m == 0 -> context.getString(R.string.dur_h, h)
        else -> context.getString(R.string.dur_hm, h, m)
    }
}
