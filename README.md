# 时间尺 · Android 壳（time-logger-android）

时间尺（[wowayou/time-logger](https://github.com/wowayou/time-logger)）的安卓原生载体。
存在的**唯一理由**是降低记录阻力：把「记一条」从「解锁 → 找图标 → 等启动 → 点 FAB →
填表 → 保存」压缩到**主屏点一下**。

界面、统计、表单、导入导出全部是 web 运行时原封不动的那一份；本仓只提供原生外壳
与原生入口。

## 它不是套壳

| | |
|---|---|
| 运行时 | **随包内嵌**（`assets/app/`，来自 web 仓 `sw.js` 的 `FILES` 清单，逐字节复制），离线不依赖任何域名 |
| 数据 | 存在应用私有目录（`filesDir/store/`），web 运行时通过 localStorage 桥读写**同一份** |
| 原生能力 | 主屏小组件、快捷设置磁贴、常驻通知（含直接回复）、长按图标快捷方式 |
| 联网 | **不声明 `INTERNET` 权限**——没有任何上传路径 |
| 云备份 | 关闭（`data_extraction_rules.xml`）；备份的唯一正当出口是应用内的「完整备份」JSON |

## 一键记录的语义

点一下＝**追认「上次记录点 → 现在」这段时间在做什么**，不是「从此刻开始计时」。
因为 web 运行时的记录只存起点、时长由下一条推断，所以一次点击就是一条完整记录。

守卫（`docs/DATA-CONTRACT.md` §4）：起点距现在超过 4 小时、或今天还一条记录都没有时，
**不静默写入**，改为打开表单让人确认起点。一次点击给一大段空白盖标签，比漏记更糟。

写错了？一键写入后会弹一条 20 秒的通知，点「撤销」即可原样回滚（数据在这期间被
界面改过就不撤销，如实告知）。

## 与 web 仓的关系

- **单一真源是 web 仓。** `assets/app/` 是同步产物，不进版本库（`.gitignore` 挡住），
  由 `scripts/sync_runtime.py` 从 `../time-logger` 逐字节复制并记录来源 commit。
- 一键写入的所有判断（起点、占位条复用、同刻唯一、归一化、CAS）都由 web 运行时的
  **真实模块**执行；原生侧不实现业务逻辑。契约见 `docs/DATA-CONTRACT.md`。
- 版本号从 web 版本派生：`versionName = <web 版本>.<本仓 revision>`，
  `versionCode = web*100 + revision`。改 `app/android_revision.txt` 再同步即可。

## 构建

需要 JDK 17 + Android SDK（platform 36 / build-tools 36.0.0）。本机工具链装在
`~/android-toolchain/`（`local.properties` 已指向它）。

```bash
python3 scripts/sync_runtime.py          # 从 ../time-logger 同步内嵌运行时（必做）
./gradlew assembleDebug                  # 产物：app/build/outputs/apk/debug/
./gradlew assembleRelease                # 有 keystore.properties 时用真实密钥，否则用 debug 签名
```

没同步运行时就构建会**直接失败**（`assertRuntimeSynced`），不会产出白屏 APK。

## 自测

```bash
python3 scripts/project_audit.py         # 结构闸：版本锚点、隐私边界、原生不实现业务逻辑
python3 scripts/quick_write_smoke.py     # 契约的纯逻辑 smoke：真实 web 模块 + 真实桥（41 条断言）
python3 scripts/shim_smoke.py            # localStorage 桥：同步语义、配额抛错、SW 桩、变更通知（22 条）
python3 scripts/redlight.py              # 逐条撤掉守卫，确认对应用例确实会变红（12 处，P35 纪律）
python3 scripts/shell_browser_check.py   # 真实 Chromium + APK 资产布局：启动、桥、镜像、刷新（17 条）
./gradlew test                           # NativeStore 的原子写与并发读写（6 条）
```

真机验收仍不能免：小组件、磁贴、通知、系统栏内边距只有设备上才算数。

## 入口一览

| 入口 | 手势 | 结果 |
|---|---|---|
| 主屏小组件 | 点标签（一下） | 直接写入 + 撤销通知 |
| 快捷设置磁贴 | 下拉 → 点磁贴 → 点标签 | 从任何界面两下 |
| 常驻通知 | 下拉 → 点标签，或「写一句」直接回复 | 直接回复是安卓上输入自由文本阻力最低的形态 |
| 长按启动图标 | 长按 → 标签 / 壳设置 | 前三个建议标签 |

建议标签来自显示镜像：当前主线永远第一，其后按最近 7 天使用频次。

## 壳设置

长按启动图标 → 「壳设置」：常驻通知开关、小组件是否显示上一条正文、安静写入上限
（60/120/240/480 分钟）、重算小组件数据。产品设置（主题、语言、标签、格言）全在
web 界面里，这里一个都不重复。

## 边界（当前不做）

- 不做云同步、账号、后端（继承 web 仓铁律）。
- 不做「从此刻开始计时」为默认语义；计划记录仍在 web 界面里。
- 不在原生侧重实现任何统计或渲染。
- 迁移靠「完整备份」JSON：手机上的 Chrome PWA 与本应用是**两份独立数据**，
  不要两边同时记。

## 许可与钱（诚实说明）

**AGPL-3.0-or-later**，与 web 仓一致——内嵌的运行时就是那份代码，所以整个 APK 都是同一份
许可下的作品。

- **源码在这里，免费构建也在这里。** 本仓公开，任何人都可以自己编译、自己安装、自由再分发。
- **应用免费、无广告、无内购、无订阅**，计划以**免费**形式上 Google Play。网页版
  （<https://time.eigentime.org>）同样永久免费。
- 若将来设置金钱入口，形态是**网站上的自愿一次性支持**（参照 bondavi 那类做法），
  **不买任何东西**——不买功能、不买优先权、不买产品路线的影响力（web 仓 D7/D28）。
  应用内不放支付界面。
- 曾考虑过「商店定价 $1」，**已放弃**：在还没有外部用户的阶段，它用最缺的东西（装机量）
  去换几乎为零的收入；而且 AGPL 本身允许任何人免费再分发，付费墙在事实层面并不存在。
  决策与理由记在 web 仓 `docs/decisions.md` D28。
- 应用内也说了同样的话：壳设置 → 关于本应用。

上架清单与文案草案见 `docs/release-checklist.md`；付费形态的决策记在 web 仓
`docs/decisions.md` D27（显式修订 D7）。
