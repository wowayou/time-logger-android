package org.eigentime.timelogger

import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.WebView
import android.widget.FrameLayout
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import org.json.JSONObject

/**
 * 主界面：内嵌运行时的宿主。这里**不实现任何产品逻辑**——界面、统计、表单全是
 * assets/app/ 里那份未经修改的 web 运行时。
 */
class MainActivity : android.app.Activity() {

    private lateinit var web: WebView
    private var pageReady = false
    private var pendingPrefill: String? = null
    private var pendingOpenForm = false

    private companion object {
        const val REQ_NOTIFICATIONS = 1001
    }

    private val themeListener = Store.Listener { key, _, _, _ ->
        if (key == Keys.THEME) runOnUiThread { applySystemBars() }
    }

    private val storageListener = Store.Listener { key, newValue, oldValue, source ->
        // 原生入口写入后，让界面按它自己的跨标签逻辑刷新（app.js 监听 'storage'：
        // 有 sheet 打开时显示横幅，否则直接重渲染）。source 是自己时不回声。
        if (source === bridge) return@Listener
        runOnUiThread { notifyWeb(key, newValue, oldValue) }
    }

    private val bridge: StoreBridge by lazy { StoreBridge(Store.get(this)) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.activity_main)
        val root = findViewById<FrameLayout>(R.id.root)
        // WebView 走 WebRuntime.create 装配，主界面与无界面桥页因此共用同一套设置
        // （JS 桥、资产加载器、sw.js 的 404）——各配一份必然漂移。
        web = WebRuntime.create(this, bridge) { uri -> openExternal(uri) }
        web.layoutParams = FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT
        )
        root.addView(web)

        // 系统栏内边距施加在 WebView 上：WebView 里的 env(safe-area-inset-*) 只反映
        // 刘海、不含状态栏高度，交给页面去猜必然被状态栏压住内容。
        ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            web.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }

        web.webChromeClient = object : android.webkit.WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                if (newProgress >= 100 && !pageReady) {
                    pageReady = true
                    verifyShimInstalled()
                    drainPending()
                    QuickWrite.refreshMirror(this@MainActivity)
                }
            }
        }

        if (assetsMissing()) {
            Toast.makeText(this, R.string.runtime_missing, Toast.LENGTH_LONG).show()
        }
        web.loadUrl(WebRuntime.APP_URL)
        applySystemBars()
        Store.addListener(themeListener)
        Store.addListener(storageListener)
        HeadlessRuntime.warm(this)
        maybeAskForNotifications()
        handleIntent(intent)
    }

    /**
     * 常驻通知是四个原生入口之一，而 API 33+ 起不申请 POST_NOTIFICATIONS 就永远发不出
     * 通知——`areNotificationsEnabled()` 恒为 false，入口会**静默消失**。只问一次：
     * 记过一次「问过了」，用户拒绝后不再骚扰（壳设置里仍可开关常驻入口）。
     */
    private fun maybeAskForNotifications() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (!AndroidPrefs.ongoingEnabled(this)) return
        val granted = checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) ==
            android.content.pm.PackageManager.PERMISSION_GRANTED
        if (granted || AndroidPrefs.notificationAsked(this)) return
        AndroidPrefs.setNotificationAsked(this, true)
        requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFICATIONS)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        // 刚拿到权限就把常驻入口立起来，别等下一次启动。
        if (requestCode == REQ_NOTIFICATIONS) Surfaces.refreshAll(this)
    }

    private fun assetsMissing(): Boolean = try {
        assets.open("app/index.html").close()
        false
    } catch (e: Exception) {
        true
    }

    override fun onDestroy() {
        Store.removeListener(themeListener)
        Store.removeListener(storageListener)
        super.onDestroy()
    }

    override fun onResume() {
        super.onResume()
        ShimFailure.message?.let {
            Toast.makeText(this, R.string.shim_failed, Toast.LENGTH_LONG).show()
        }
        Surfaces.refreshAll(this)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        intent ?: return
        when (intent.action) {
            Actions.OPEN_FORM -> pendingOpenForm = true
            Actions.WRITE, Intent.ACTION_VIEW -> {
                val tag = intent.getStringExtra(Actions.EXTRA_PREFILL)
                if (!tag.isNullOrBlank()) {
                    pendingPrefill = tag
                    pendingOpenForm = true
                }
            }
        }
        if (pageReady) drainPending()
    }

    /**
     * 守卫拦下的一键写入（起点太远／今天还没记录）会走到这里：打开表单，把默认
     * 起点交给用户确认。**不代替用户保存**——那正是守卫存在的理由（契约 §4）。
     */
    private fun drainPending() {
        if (!pendingOpenForm) return
        pendingOpenForm = false
        val tag = pendingPrefill
        pendingPrefill = null
        val tagJs = if (tag.isNullOrBlank()) "''" else JSONObject.quote(tag)
        web.evaluateJavascript(
            """
            (function (tag) {
              try {
                var fab = document.getElementById('add-btn');
                if (!fab || fab.hidden) return 'no-fab';
                fab.click();
                if (!tag) return 'form';
                var what = document.getElementById('form-what');
                if (what) what.value = tag;
                var chip = document.querySelector('#form-chips .chip[data-tag="' + tag.replace(/"/g, '\\"') + '"]');
                if (chip) { chip.click(); return 'form+chip'; }
                return 'form+what';
              } catch (e) { return 'err:' + e.message; }
            })($tagJs)
            """.trimIndent(), null
        )
    }

    /**
     * 桥必须真的装上了才算数。DOCUMENT_START_SCRIPT 若不可用（极老的 WebView），
     * 主界面会退回 WebView 自己的 localStorage——那时界面与小组件写的是**两份**数据，
     * 而且外表完全正常。这是必须当场说出来的故障，不能安静地分裂。
     */
    private fun verifyShimInstalled() {
        web.evaluateJavascript("(typeof window.__tlNotifyStorage === 'function')") { result ->
            Diag.log("shim installed: $result")
            if (result?.contains("true") != true) {
                ShimFailure.record("document-start script did not run")
                Toast.makeText(this, R.string.shim_failed, Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun notifyWeb(key: String, newValue: String?, oldValue: String?) {
        if (!pageReady) return
        val js = "if (window.__tlNotifyStorage) window.__tlNotifyStorage(" +
            "${JSONObject.quote(key)}, " +
            "${newValue?.let { JSONObject.quote(it) } ?: "null"}, " +
            "${oldValue?.let { JSONObject.quote(it) } ?: "null"});"
        web.evaluateJavascript(js, null)
    }

    /** 状态栏/导航栏按应用主题上色，跟随 web 端的 timelog.theme（auto/light/dark）。 */
    private fun applySystemBars() {
        val pref = Store.get(this).getItem(Keys.THEME) ?: "auto"
        val light = when (pref) {
            "light" -> true
            "dark" -> false
            else -> (resources.configuration.uiMode and
                android.content.res.Configuration.UI_MODE_NIGHT_MASK) ==
                android.content.res.Configuration.UI_MODE_NIGHT_NO
        }
        val bg = if (light) Color.parseColor("#eceef3") else Color.parseColor("#0e0f13")
        window.decorView.setBackgroundColor(bg)
        web.setBackgroundColor(bg)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = light
            isAppearanceLightNavigationBars = light
        }
    }

    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        applySystemBars()
    }

    private fun openExternal(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            Toast.makeText(this, uri.toString(), Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 返回键：sheet 打开时先关 sheet（等价于按 Esc，app.js 已有处理），否则退出。
     * 直接退出会让用户在填表时一按返回就丢掉正在写的内容。
     */
    // 平台把 onBackPressed 标了弃用，替代品是 OnBackInvokedCallback；但那套要么
    // 引入 androidx.activity（为一个返回键加一整个依赖），要么只在 API 33+ 可用。
    // 这里显式关掉预测式返回（manifest 的 enableOnBackInvokedCallback=false）并继续
    // 用这个回调，等将来真需要预测式返回动画时再换。
    @Deprecated("平台弃用；见上方注释，预测式返回已在 manifest 关闭")
    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        web.evaluateJavascript(
            """
            (function () {
              var s = document.getElementById('form-sheet');
              var open = s && !s.hasAttribute('hidden');
              if (open) {
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                return '1';
              }
              return '0';
            })()
            """.trimIndent()
        ) { result ->
            if (result?.contains("1") != true) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) finishAfterTransition() else finish()
            }
        }
    }
}
