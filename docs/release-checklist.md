# 上架清单（Google Play，临时定价 $1）

> 状态：**未上架**。本文件是执行清单与文案草案，不是已完成的事实。
> 决策依据：web 仓 `docs/decisions.md` D26（原生载体开工）与 D27（付费形态，修订 D7）。

## 0. 三个前置问题的结论

**① 仓库公开还是私有 → 公开。** 三条理由，任一条都足够：

- 本应用内嵌 AGPL-3.0 的运行时，分发即触发**向接收者提供对应源码**的义务；公开仓库是最省事、最不容易出错的履行方式。
- web 仓 D2/D7 已定「仓库继续公开」，且理由至今成立：把仓库改私有**保护不了任何东西**——网页版的前端源码本来就能在浏览器里读到。
- 维护者要求「一定要诚实说明有开源的可用」。这句话要能被验证，源码必须真的可达。

**② 要不要合进现有公开仓库 → 不要，另立 `time-logger-android`。** web 仓铁律是「单页静态 / 无构建 / 无运行时依赖」，Gradle 工程进去就破了；D8 / ADR 0001 / D26 都写明另立独立仓库。两仓的关系是「上游真源 + 同步产物」，靠 `scripts/sync_runtime.py` 与 `scripts/project_audit.py` 钉住。

**③ 付费 $1 与「所有功能始终免费」冲突吗 → 不冲突，但必须显式记账。**
D7 承诺的是**功能免费**；Play 上的 $1 买的是**商店分发与自动更新**这项便利，不是功能，也不是解锁。同一份 APK 在 GitHub Release 上免费可得，源码可自行构建。D14 早已预留这条路（「免费 Web + 付费原生壳，Web 端承诺可以不破」），但要求「显式修订 D7、不能悄悄滑过去」——那就是 D27。

**必须同时说清的一条**：AGPL 允许任何人**免费再分发**你卖的这个 APK。$1 是支持作者的姿态，**不是护城河**，指望它防止免费流通是自欺。

## 1. 诚实声明放在哪（维护者硬要求）

三处，缺一不可：

1. **应用内**：壳设置最下方的「关于本应用」区块——「开源软件（AGPL-3.0）。源码与免费构建都在 GitHub —— 本应用没有任何付费功能」＋「网页版永久免费」＋「如果你在商店里付过费，买的是商店分发与自动更新，不是功能」。已实现（`SettingsActivity` + `about_*` 字符串）。
2. **商店简介**：见 §4 文案草案，第一段就说。
3. **README**：已写明。

## 2. 账号与密钥（只有维护者能做）

- [ ] Google Play 开发者账号（一次性 $25）
- [ ] **收款所需的 Payments profile**（付费应用必须；要税务信息与银行账户）
- [ ] 生成上传密钥（**离开这台机器备份，丢了就换不了包名**）：

```bash
keytool -genkeypair -v -keystore ~/keys/timelogger-upload.jks \
  -alias upload -keyalg RSA -keysize 4096 -validity 10000
```

- [ ] 在仓库根写 `keystore.properties`（已被 `.gitignore` 挡住，**永不提交**）：

```properties
storeFile=/home/<you>/keys/timelogger-upload.jks
storePassword=...
keyAlias=upload
keyPassword=...
```

- [ ] 打包：`python3 scripts/sync_runtime.py && ./gradlew bundleRelease`（Play 要 `.aab`）
- [ ] 开启 Play App Signing（Google 保管分发密钥，你保管上传密钥）

## 3. Play 后台要填的东西

| 项 | 我们的答案 |
|---|---|
| 包名 | `org.eigentime.timelogger`（**一经上架不可改**） |
| targetSdk | 36（当前 Play 要求 ≥35，达标） |
| 数据安全表单 | **不收集、不共享任何数据**；无 `INTERNET` 权限；数据只在设备本地；用户可随时导出完整备份 JSON |
| 权限说明 | 只有 `POST_NOTIFICATIONS`，用于「常驻记录入口」这一个可关闭的功能 |
| 隐私政策 URL | **还缺**：需要在 `time.eigentime.org/privacy` 增加一节「Android 应用」，说明零收集、零联网、本地存储、卸载即删除。这是 web 仓的活（改 `site/`，按 CLAUDE.md 走一次 `publish-site`） |
| 内容分级 | 全年龄；无用户生成内容对外传播、无广告、无内购 |
| 广告 | 无 |
| 定价 | $1（临时）；上架后**不能**再改成免费又改回收费（Play 允许免费→付费一次性转换有限制，先想清楚） |
| 商店资产 | 512×512 图标、1024×500 特征图、≥2 张手机截图（**必须用合成 demo 数据，不得用真实记录**——web 仓隐私红线同样适用） |

## 4. 商店文案草案

**应用名**：时间尺 / Time Logger
**简短描述（80 字符内）**：5 秒记下真实做了什么，本地离线，一天看清时间去哪了。

**完整描述（第一段就是诚实声明）**：

> 时间尺是开源软件（AGPL-3.0）。源码与免费构建都在 GitHub：
> github.com/wowayou/time-logger-android ；网页版永久免费：time.eigentime.org 。
> 在商店购买支付的是分发与自动更新的便利，**不是功能**——本应用没有任何付费功能、
> 没有订阅、没有广告、没有内购。
>
> 记一条只需要点一下。主屏小组件、快捷设置磁贴、常驻通知（可直接回复）与长按图标
> 的快捷方式，都是「追认上次记录到现在这段时间在做什么」——因为一条记录只存起点，
> 时长由下一条推断，所以一次点击就是一条完整记录。真机实测：热进程约 0.1 秒。
>
> 数据只存在你的手机上：应用**没有联网权限**，不上传、不同步、没有账号。备份是一份
> 你随时可以导出的 JSON。云备份与换机迁移已关闭，因为那会造出一份你不知道存在的副本。
>
> 四桶分类（主线 / 维持 / 偏航 / 未记录）与日周月年视图，帮你看清一天的形状。
> 「偏航」不等于错误——适时放空是必要的。

**英文版**：同上直译，`about_*` 字符串已有对应措辞。

## 5. 上架前必须跑的

```bash
python3 scripts/sync_runtime.py
python3 scripts/project_audit.py
python3 scripts/quick_write_smoke.py
python3 scripts/shim_smoke.py
python3 scripts/shell_browser_check.py
python3 scripts/redlight.py
./gradlew test bundleRelease
python3 scripts/device_check.py --serial <设备>   # release 包也要过一遍
```

## 6. 明确不做

- 不做订阅、不做内购、不做「解锁高级功能」——那会真的推翻 D7。
- 不做广告、不接分析 SDK、不加 `INTERNET` 权限。
- 不为了防止免费流通去做许可校验或联网激活（既违背 AGPL，也与本项目的定位冲突）。
- 不上 App Store：Apple 的 Usage Rules 与 GPL 系冲突（LICENSING.md §3 已记）；真要上，走那条「另行授权」的路，是另一个决策。
