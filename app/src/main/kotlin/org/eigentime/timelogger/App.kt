package org.eigentime.timelogger

import android.app.Application
import android.content.Context
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/**
 * 进程级单例：原生存储 + 变更广播。
 *
 * 所有数据写入都发生在 JS 侧（契约 §2：原生不实现业务逻辑），但**通知谁刷新**是
 * 原生的事：主界面 WebView 要按它自己的跨标签逻辑刷新，小组件与通知要重画。
 */
object Store {

    @Volatile
    private var impl: NativeStore? = null

    private val listeners = CopyOnWriteArrayList<Listener>()

    /** source 是发起这次写入的对象（通常是某个 StoreBridge），用来避免自己通知自己。 */
    fun interface Listener {
        fun onChanged(key: String, newValue: String?, oldValue: String?, source: Any?)
    }

    fun get(context: Context): NativeStore {
        impl?.let { return it }
        return synchronized(this) {
            impl ?: NativeStore(File(context.applicationContext.filesDir, "store")).also { impl = it }
        }
    }

    fun addListener(l: Listener) = listeners.add(l)
    fun removeListener(l: Listener) = listeners.remove(l)

    fun notifyChanged(key: String, newValue: String?, oldValue: String?, source: Any?) {
        listeners.forEach { it.onChanged(key, newValue, oldValue, source) }
    }
}

object Keys {
    const val DATA = "timelog.v1"
    const val CONFIG = "timelog.config"
    const val THEME = "timelog.theme"
    const val MIRROR = "timelog.widgetMirror.v1"
    const val PREFS = "timelog.androidPrefs.v1"
}

class TimeLoggerApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Store.get(this)
        // 数据或镜像一变就重画外围表面。小组件/通知只读镜像（契约 §6），
        // 但 timelog.v1 变了而镜像还没写完时也先刷一次，宁可多画一次。
        Store.addListener { key, _, _, _ ->
            if (key == Keys.MIRROR || key == Keys.DATA || key == Keys.CONFIG) {
                Surfaces.refreshAll(this)
            }
        }
    }
}
