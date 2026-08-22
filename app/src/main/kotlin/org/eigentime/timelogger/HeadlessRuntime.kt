package org.eigentime.timelogger

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.webkit.WebView
import org.json.JSONObject
import org.json.JSONTokener

/**
 * 进程内常驻的无界面 WebView：让小组件 / 磁贴 / 通知的一键写入跑**真实**的 web 模块
 * （契约 §2）。热的时候一次调用只有几毫秒；冷启动要等桥页加载（实测量级 200–400ms），
 * 这段时间里请求排队，不丢。
 */
object HeadlessRuntime {

    private val main = Handler(Looper.getMainLooper())
    private var web: WebView? = null
    private var ready = false
    private var createdAt = 0L
    private val queue = ArrayDeque<(WebView) -> Unit>()

    /** 必须在主线程调用。 */
    private fun ensure(context: Context) {
        if (web != null) return
        val app = context.applicationContext
        val bridge = StoreBridge(Store.get(app)) {
            // onBridgeReady 来自 JavaBridge 线程，切回主线程再动队列。
            main.post {
                ready = true
                Diag.log("headless: bridge ready in ${Diag.ms(createdAt)}ms, queued=${queue.size}")
                val pending = queue.toList()
                queue.clear()
                web?.let { wv -> pending.forEach { it(wv) } }
            }
        }
        val wv = WebRuntime.create(app, bridge)
        web = wv
        createdAt = System.currentTimeMillis()
        Diag.log("headless: creating bridge webview")
        wv.loadUrl(WebRuntime.BRIDGE_URL)
    }

    fun warm(context: Context) {
        main.post { ensure(context) }
    }

    /**
     * 执行一段 JS，结果按 JSON 回调。
     * @param js 必须是一个求值为字符串的表达式（约定用 JSON.stringify(...) 包起来）
     */
    fun eval(context: Context, js: String, timeoutMs: Long = 8000, cb: (JSONObject?) -> Unit) {
        var answered = false
        val answer = { value: JSONObject? ->
            if (!answered) {
                answered = true
                cb(value)
            }
        }
        main.post {
            ensure(context)
            val startedAt = System.currentTimeMillis()
            val task: (WebView) -> Unit = { wv ->
                wv.evaluateJavascript(js) { raw ->
                    Diag.log("headless: eval returned in ${Diag.ms(startedAt)}ms, chars=${raw?.length ?: -1}")
                    answer(parse(raw))
                }
            }
            if (ready) task(web!!) else {
                Diag.log("headless: bridge not ready yet, queueing call")
                queue.add(task)
            }
            main.postDelayed({
                if (!answered) Diag.log("headless: TIMEOUT after ${timeoutMs}ms")
                answer(null)
            }, timeoutMs)
        }
    }

    /**
     * evaluateJavascript 给回来的是 JSON 编码后的值；我们的表达式返回的是一个
     * JSON **字符串**，所以要先解一层引号再解析对象。
     */
    private fun parse(raw: String?): JSONObject? {
        if (raw == null || raw == "null") return null
        return try {
            val unquoted = JSONTokener(raw).nextValue()
            when (unquoted) {
                is String -> JSONObject(unquoted)
                is JSONObject -> unquoted
                else -> null
            }
        } catch (e: Exception) {
            null
        }
    }

    fun jsString(value: String): String = JSONObject.quote(value)
}
