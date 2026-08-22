package org.eigentime.timelogger

import android.annotation.SuppressLint
import android.content.Context
import android.net.Uri
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import java.io.ByteArrayInputStream

/**
 * 内嵌运行时的装配处。
 *
 * - 运行时文件由 scripts/sync_runtime.py 从 web 仓逐字节复制到 assets/app/，
 *   这里**不改一个字节**，只在页面脚本之前注入 localStorage 桥（store_shim.js）。
 * - 用 WebViewAssetLoader 的保留虚拟域名（https 源）而不是 file://：ES modules、
 *   sessionStorage、`crypto` 这些都要求安全上下文，file:// 会全线报错。
 * - assets 里**没有** sw.js（同步脚本刻意跳过），这里再对它返回 404：Service Worker
 *   在 APK 里只会造成「升了包还是旧界面」。
 */
object WebRuntime {

    const val ORIGIN = "https://appassets.androidplatform.net"
    const val APP_URL = "$ORIGIN/app/index.html"
    const val BRIDGE_URL = "$ORIGIN/bridge/headless.html"

    private fun shimSource(context: Context): String =
        context.assets.open("bridge/store_shim.js").use { it.readBytes().toString(Charsets.UTF_8) }

    @SuppressLint("SetJavaScriptEnabled")
    fun create(
        context: Context,
        bridge: StoreBridge,
        onExternalUrl: ((Uri) -> Unit)? = null
    ): WebView {
        val web = WebView(context)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true          // sessionStorage：v53 的刷新接帧快照要用
            allowFileAccess = false
            allowContentAccess = false
            mediaPlaybackRequiresUserGesture = true
            // 不声明 INTERNET 权限，这里再关一道混合内容通道，行为上等于「只跑本地资产」
            cacheMode = android.webkit.WebSettings.LOAD_NO_CACHE
        }
        web.setBackgroundColor(0xFF0E0F13.toInt())
        // WebView 在 View 层自己画滚动条，CSS 的 `scrollbar-width:none` /
        // `::-webkit-scrollbar` 管不到它。web 仓 v86 已裁定「手机上不显示滚动条」，
        // 这里让原生侧与那个决定一致（否则拖动时仍会闪出一条）。
        //
        // 诚实记录：加这两行时我以为它能消掉真机右缘那条浅色竖带——**没有**。
        // 对照实验：关掉滚动条后竖带位置（y 480–820）与之前逐像素相同，且系统设置
        // 页面的同几列也有同样的浅色渐变，所以那是 One UI 的 Edge 面板手柄，属系统侧
        // （与 web 仓 D23「退出动效白边是系统行为」同一类误判）。这两行保留，理由是
        // 上面那条与 v86 的一致性，不是那条竖带。
        web.isVerticalScrollBarEnabled = false
        web.isHorizontalScrollBarEnabled = false
        web.addJavascriptInterface(bridge, "__tlNative")

        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/", WebViewAssetLoader.AssetsPathHandler(context))
            .build()

        web.webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest
            ): WebResourceResponse? {
                val url = request.url
                // 页面会顺手要一次 /favicon.ico；没有 INTERNET 权限，让它去发起网络请求
                // 只会在日志里留一条 code=-1 的错误。直接给 404 更干净。
                if (url.path?.endsWith("/favicon.ico") == true ||
                    url.path?.endsWith("/sw.js") == true
                ) {
                    return WebResourceResponse(
                        "text/plain", "utf-8", 404, "Not Found",
                        emptyMap(), ByteArrayInputStream(ByteArray(0))
                    )
                }
                return loader.shouldInterceptRequest(url)
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: androidx.webkit.WebResourceErrorCompat
            ) {
                Diag.log("webview error: ${request.url.lastPathSegment} code=${error.errorCode}")
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url
                if (url.toString().startsWith(ORIGIN)) return false
                // 站点标识那个 GitHub 链接不该把 WebView 导航出应用：交给系统浏览器。
                onExternalUrl?.invoke(url)
                return true
            }
        }

        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            WebViewCompat.addDocumentStartJavaScript(web, shimSource(context), setOf(ORIGIN))
        }
        // 特性缺失时的兜底只覆盖桥页：headless.html 自己带一个 <script src="store_shim.js">，
        // 一键写入这条关键路径因此不依赖 DOCUMENT_START_SCRIPT。主界面此时会退回
        // WebView 自己的 localStorage，StoreBridge.onShimFailed / 缺失检查会让它可见，
        // 而不是安静地写到另一份数据里。
        return web
    }
}
