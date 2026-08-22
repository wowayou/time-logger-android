package org.eigentime.timelogger

import android.webkit.JavascriptInterface

/**
 * 注入到 WebView 里的 `window.__tlNative`。方法体刻意只有存储读写——
 * JavascriptInterface 的调用是**同步**且能返回值的，所以 localStorage 的同步语义
 * 可以逐条对上（见 assets/bridge/store_shim.js）。
 *
 * 线程：这些方法运行在 WebView 的 JavaBridge 线程上，不是主线程。NativeStore 自带锁；
 * 需要碰 UI 的事情一律 post 回主线程。
 */
class StoreBridge(
    private val store: NativeStore,
    private val onBridgeReadyCallback: (() -> Unit)? = null
) {

    @JavascriptInterface
    fun getItem(key: String): String? = store.getItem(key)

    @JavascriptInterface
    fun setItem(key: String, value: String): String? {
        val old = store.getItem(key)
        val err = store.setItem(key, value)
        if (err == null && old != value) Store.notifyChanged(key, value, old, this)
        return err
    }

    @JavascriptInterface
    fun removeItem(key: String) {
        val old = store.getItem(key)
        store.removeItem(key)
        if (old != null) Store.notifyChanged(key, null, old, this)
    }

    @JavascriptInterface
    fun clear() {
        store.clear()
        Store.notifyChanged("", null, null, this)
    }

    @JavascriptInterface
    fun key(index: Int): String? = store.key(index)

    @JavascriptInterface
    fun length(): Int = store.length()

    /** 桥页（headless.html）加载完毕的信号，见 HeadlessRuntime。 */
    @JavascriptInterface
    fun onBridgeReady() {
        onBridgeReadyCallback?.invoke()
    }

    /**
     * localStorage 换不上时的告警通道。真发生了就意味着原生入口与界面在写两份数据，
     * 必须让用户知道，而不是安静地分裂。
     */
    @JavascriptInterface
    fun onShimFailed(message: String) {
        ShimFailure.record(message)
    }
}

object ShimFailure {
    @Volatile
    var message: String? = null
        private set

    fun record(m: String) {
        message = m
    }
}
