package org.eigentime.timelogger

import android.util.Log

/**
 * 诊断日志。真机上一次「点了没反应」曾让我只能靠猜——Toast 一闪而过、logcat 里
 * 一个字都没有。所以这里留一条固定通道。
 *
 * 纪律与 web 仓的启动诊断一致：**只记枚举、计时、布尔和条数，绝不记录内容、
 * 标签文本或备份数据**。标签是用户数据，出现在 logcat 里就等于泄漏。
 */
object Diag {
    const val TAG = "timelogger"

    fun log(message: String) {
        Log.i(TAG, message)
    }

    fun ms(started: Long): Long = System.currentTimeMillis() - started
}
