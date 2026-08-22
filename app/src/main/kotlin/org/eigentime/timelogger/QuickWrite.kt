package org.eigentime.timelogger

import android.content.Context
import org.json.JSONObject

/**
 * 一键写入的**唯一**入口。小组件、磁贴、通知、快捷方式全部走这里；宿主不同
 * （不可见 Activity / 广播接收器），写入路径只有一条。
 *
 * 这个类不判断能不能写、起点是哪一刻、要不要复用占位条——那些全在 JS 侧的真实
 * 模块里（契约 §2/§3/§4）。它只负责把结果翻译成人话。
 */
object QuickWrite {

    data class Outcome(
        val ok: Boolean,
        val reason: String = "",
        val mode: String = "",
        val ts: String = "",
        val tag: String = "",
        val what: String = "",
        val minutes: Int = -1,
        val suggestTs: String = "",
        val conflictWhat: String = "",
        val message: String = "",
        val limit: Int = -1,
        val gapMinutes: Int = -1
    )

    private fun parse(o: JSONObject?): Outcome {
        if (o == null) return Outcome(ok = false, reason = "timeout")
        return Outcome(
            ok = o.optBoolean("ok"),
            reason = o.optString("reason"),
            mode = o.optString("mode"),
            ts = o.optString("ts"),
            tag = o.optString("tag"),
            what = o.optString("what"),
            minutes = o.optInt("minutes", -1),
            suggestTs = o.optString("suggestTs"),
            conflictWhat = o.optString("conflictWhat"),
            message = o.optString("message"),
            limit = o.optInt("limit", -1),
            gapMinutes = o.optInt("gapMinutes", -1)
        )
    }

    fun perform(context: Context, tag: String, what: String? = null, cb: (Outcome) -> Unit) {
        val js = "JSON.stringify(window.__tlBridge.quickWrite(" +
            "${HeadlessRuntime.jsString(tag)}, {what: ${HeadlessRuntime.jsString(what ?: "")}}))"
        HeadlessRuntime.eval(context, js) {
            val out = parse(it)
            // 只记枚举与数字：标签和「做了什么」是用户数据，不进 logcat。
            Diag.log("quickWrite: ok=${out.ok} reason=${out.reason} mode=${out.mode} " +
                "minutes=${out.minutes} gap=${out.gapMinutes} limit=${out.limit}")
            cb(out)
        }
    }

    fun undo(context: Context, cb: (Outcome) -> Unit) {
        HeadlessRuntime.eval(context, "JSON.stringify(window.__tlBridge.undoLastQuickWrite())") {
            val out = parse(it)
            Diag.log("undo: ok=${out.ok} reason=${out.reason}")
            cb(out)
        }
    }

    /** 重算显示镜像（数据被界面改过、或刚装上小组件时）。 */
    fun refreshMirror(context: Context, cb: (Boolean) -> Unit = {}) {
        HeadlessRuntime.eval(context, "JSON.stringify(window.__tlBridge.writeMirror())") { cb(it != null) }
    }

    fun hhmm(ts: String): String = if (ts.length >= 16) ts.substring(11, 16) else ts

    /**
     * 把结果翻成用户看得懂的一句话。守卫（fresh-day / gap-too-large）**不是错误**，
     * 是「这一下不该悄悄写」，所以文案说的是下一步该做什么。
     */
    fun message(context: Context, out: Outcome): String = when {
        out.ok && out.mode == "same-minute-correction" ->
            context.getString(R.string.written_corrected, out.tag)
        out.ok -> context.getString(R.string.written, hhmm(out.ts), out.tag)
        out.reason == "fresh-day" -> context.getString(R.string.guard_fresh_day)
        out.reason == "gap-too-large" -> context.getString(
            R.string.guard_gap,
            formatDuration(context, if (out.gapMinutes > 0) out.gapMinutes else 0)
        )
        out.reason == "no-slot" -> context.getString(R.string.guard_no_slot)
        out.reason == "conflict" -> context.getString(R.string.guard_conflict, out.conflictWhat)
        out.reason == "concurrent" -> context.getString(R.string.guard_concurrent)
        out.reason == "quota" -> context.getString(R.string.guard_quota)
        out.reason == "unknown-tag" -> context.getString(R.string.guard_unknown_tag, out.tag)
        out.reason == "timeout" -> context.getString(R.string.guard_timeout)
        // 桥的边界把未捕获异常翻成 internal：说出「出错了」而不是伪装成超时。
        out.reason == "internal" -> context.getString(R.string.guard_internal, out.message)
        else -> context.getString(R.string.guard_generic, out.reason)
    }

    /** 守卫拦下、需要用户在表单里确认起点的那几种。 */
    fun needsForm(out: Outcome): Boolean =
        !out.ok && (out.reason == "fresh-day" || out.reason == "gap-too-large")
}
