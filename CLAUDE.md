# CLAUDE.md — 时间尺 Android 壳维护规范

## 这个仓库是什么

时间尺的安卓原生载体。**单一真源在 web 仓** `wowayou/time-logger`；本仓只有：

- `app/src/main/assets/app/`：web 运行时的**同步副本**（不进版本库，由 `scripts/sync_runtime.py` 生成）
- `app/src/main/assets/bridge/`：localStorage 桥（`store_shim.js`）、无界面桥页（`headless.html`）、
  一键写入胶水（`quick_write.js`——调用真实 web 模块，不复制业务逻辑）
- `app/src/main/kotlin/`：外壳与原生入口（WebView 宿主、小组件、磁贴、通知、快捷方式、存储）
- `docs/DATA-CONTRACT.md`：**权威契约**，任何不经 web 表单的写入都必须遵守
- `scripts/`：同步、契约 smoke、红灯检查

## 红线

1. **`assets/app/` 一个字节都不许改。** 要改运行时行为，去 web 仓改，然后重新同步。
   同步脚本刻意跳过 `sw.js`（APK 里 Service Worker 只会造成「升了包还是旧界面」），
   资产加载器另对它返回 404，JS 侧还有 `navigator.serviceWorker` 桩——三道都要留着。
2. **原生代码不实现业务逻辑。** 起点、时长、占位条、桶归类、同刻唯一、归一化、CAS
   一律由 web 模块执行；Kotlin 只做存储、生命周期、呈现和纯格式化。判据见契约 §2。
3. **不声明 `INTERNET` 权限。** 权限不在，代码就无从联网。云备份与换机迁移同样关闭。
4. **原生侧唯一可写的键是 `timelog.androidPrefs.v1`**（设备偏好，不进备份）。
   时间线数据（`timelog.v1`）、标签配置（`timelog.config`）只能由 web 模块写。
5. **一键写入不许静默盖大段空白。** `fresh-day` / `gap-too-large` 两条守卫必须存在；
   拦下时改为打开表单让人确认起点，不代替用户保存。
6. **不自动确认长段、不自动建标签、不自动改主题或语言。** 与 web 仓 D13③ 一致。
7. 改 `quick_write.js` / `store_shim.js` 或任何守卫后，**必须**跑 `quick_write_smoke.py`、
   `shim_smoke.py` 与 `redlight.py`；
   新增守卫要同时新增一处红灯。红灯点不亮＝那条用例没在测它。
8. **不得有付费墙。** 应用免费上架；不得引入付费功能、订阅、内购、广告、分析 SDK，
   也不得为阻止免费流通做许可校验或联网激活（AGPL + web 仓 D28）。金钱入口只能是
   网站上的自愿支持，且必须写明「不购买任何东西」。应用内、README、商店文案三处的
   「开源 + 免费」声明不得删除或弱化；应用内不放支付界面。
9. **发版必须走仪式**：`sync_runtime.py --release`（预检：web 仓 clean/commit/版本/契约）→ 自测 → `bundleRelease`（fail-closed：缺 `keystore.properties` 直接失败）→ tag `a<web版本>.<revision>` →
   push tags → GitHub Release **并附 APK**（免费构建随手可得是 D28 的承诺，不是可选项）。
   步骤见 `docs/release-checklist.md` §5.6。
10. 版本号只能从 web 版本派生（`sync_runtime.py` 写 `app/version.properties`），
   不手写 `versionCode` / `versionName`。

## 目录边界

| 位置 | 只放 | 不放 |
|---|---|---|
| `assets/app/` | web 运行时同步副本 | 任何手工修改 |
| `assets/bridge/` | 桥与胶水（import 真实模块） | 复制来的业务规则 |
| `kotlin/.../NativeStore.kt` | 键→字符串的原子读写（纯 JVM，可单测） | Android API、JSON 解析、业务判断 |
| `kotlin/.../QuickWrite.kt` | 调桥 + 把 reason 翻成人话 | 判断能不能写 |
| `kotlin/.../Mirror.kt` | 读显示镜像 + 纯格式化 | 解析 `timelog.v1` |
| `kotlin/.../*Widget/Tile/Notifier` | 呈现与 PendingIntent | 数据写入 |

## 提交前

```bash
python3 scripts/sync_runtime.py
python3 scripts/project_audit.py
python3 scripts/quick_write_smoke.py
python3 scripts/shim_smoke.py
python3 scripts/redlight.py
python3 scripts/shell_browser_check.py
./gradlew test assembleDebug
git status --short   # 不许出现 assets/app/、*.apk、keystore、真实备份 JSON
```

## 隐私

- 不提交真实记录、真实截图、导出的 `timelog-*.json`、keystore。
- 常驻通知 `VISIBILITY_SECRET`：锁屏不展示记录内容。
- 小组件默认显示上一条正文，可在壳设置里关掉（关掉后镜像里不写正文）。

## 当前状态

- v1 已在 S23（Android 14）真机验收：自动 24/24，小组件与磁贴的一键写入端到端通过；
  热进程 0.1 秒、冷进程 0.55 秒完成一次记录。详见 `docs/device-acceptance.md`。
- 分发：当前自用侧载（debug 签名）。计划**免费**上 Google Play，金钱入口只在网站的
  自愿支持页；清单见 `docs/release-checklist.md`，决策见 web 仓 D28（收窄了 D27 的 $1）。
- 上架前还欠：release 上传密钥、商店资产（必须用合成 demo 数据）、网站支持页。
  隐私政策的「Android 应用」一节已写入 web 仓 `site/`（待发布一次生效）。
- 英文名统一为 **Eigentime**（web 仓 D29）；中文名 **时间尺**。包名 `org.eigentime.timelogger`
  上架后不可改。
