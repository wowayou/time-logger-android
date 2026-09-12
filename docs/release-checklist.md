# 上架清单（Google Play，**免费**上架 + 网站自愿支持）

> 状态：**未上架**。本文件是执行清单与文案草案，不是已完成的事实。
>
> ### 进度（2026-08-22，如实）
>
> | 项 | 状态 |
> |---|---|
> | 发布产物能不能出 | 2026-08-22 实测**能**（`app-release.aab` 2.09 MB / `app-release.apk` 2.10 MB，versionName `93.1`），**但当时签的是 debug 回退密钥，不可上传**。**2026-09-12 起 release 已改 fail-closed**：缺 `keystore.properties`（或字段空白/密钥文件不存在）时 Release 任务直接失败，不再产出 debug 签名的假产物——下表那次的「能出」在今天的代码上不会发生，出包前先配好 §2 的密钥 |
> | 隐私政策 | **已上线**。中英两版第 6 节「Android 应用 / Android app」，`time.eigentime.org/privacy/` 已 curl 复核 |
> | 商店图标 512×512 | **已做**：`docs/store/icon-512.png`（直接用运行时那张 512，品牌逐字节一致） |
> | 特征图 1024×500 | **已做**：`docs/store/feature-1024x500.png`（只有品牌 + 两行事实描述，无排名/促销字样） |
> | 手机截图 ≥2 张 | **已做**：`docs/store/screen-1-day.png`（日视图：结论卡 + 连续日志）、`screen-2-week.png`（周视图：四桶比例 + 每日汇总）、`screen-3-form.png`（记一条表单）。1064×2244，合成 demo 数据（本周 4 天），已裁掉状态栏与 One UI 的 Edge 面板手柄 |
> | 商标检索 | **没做成**。搜索引擎只返回通用注册常识页；Play 商店搜 `eigentime` 无同名应用（实测）。权威检索要在 USPTO TESS / EUIPO eSearch / CNIPA 上人工做，**本文件不构成商标结论** |
> | 开发者账号 / 上传密钥 | **只有维护者能做**，见 §2 |
> | 网站支持页 | **未做**，等收款渠道确定；在它上线前应用内不放链接 |
> 决策依据：web 仓 `docs/decisions.md` D26（原生载体开工）、D27（曾定 $1）与
> **D28（收窄 D27：免费上架 + 网站自愿支持，回到 D7 原意）**。

## 0. 三个前置问题的结论

**① 仓库公开还是私有 → 公开。** 三条理由，任一条都足够：

- 本应用内嵌 AGPL-3.0 的运行时，分发即触发**向接收者提供对应源码**的义务；公开仓库是最省事、最不容易出错的履行方式。
- web 仓 D2/D7 已定「仓库继续公开」，且理由至今成立：把仓库改私有**保护不了任何东西**——网页版的前端源码本来就能在浏览器里读到。
- 维护者要求「一定要诚实说明有开源的可用」。这句话要能被验证，源码必须真的可达。

**② 要不要合进现有公开仓库 → 不要，另立 `time-logger-android`。** web 仓铁律是「单页静态 / 无构建 / 无运行时依赖」，Gradle 工程进去就破了；D8 / ADR 0001 / D26 都写明另立独立仓库。两仓的关系是「上游真源 + 同步产物」，靠 `scripts/sync_runtime.py` 与 `scripts/project_audit.py` 钉住。

**③ 收不收钱 → 免费上架，钱放在网站上的自愿支持。**
D7 原文是「定位为『支持作者』……所有功能始终免费」，而 bondavi 那类做法（应用免费无广告、
PayPal 三档一次性捐赠、捐赠者不获得任何特权）与它几乎逐字一致。D27 曾定 $1，**D28 收窄**：
在还没有外部用户的阶段，$1 用最缺的东西（装机量）换几乎为零的收入；而且 AGPL 允许任何人
免费再分发，付费墙在事实层面并不存在。

**形态**：Play 免费上架；**应用内不放任何支付界面**，只在「关于本应用」里说明「免费、
无广告、无内购」＋指向网站。金钱入口是网站上的一次性支持页（渠道建议：国内爱发电、
海外 PayPal.me 或 GitHub Sponsors），并写明**不购买任何东西**。

**上架前必须查一次的政策**（会变，别照抄本文件）：Google Play 对「非营利之外的开发者在
应用内引导外部捐赠」的规则历年反复，Epic v. Google 之后美国区的外链规则也动过。
最稳的形态就是上面这条——应用内不出现支付界面，支持页只存在于网站。

## 1. 诚实声明放在哪（维护者硬要求）

三处，缺一不可：

1. **应用内**：壳设置最下方的「关于本应用」——「开源软件（AGPL-3.0）。源码与免费构建都在 GitHub」＋「免费、无广告、无内购、无订阅。所有功能永久免费」＋「支持作者完全自愿，且不购买任何东西」。已实现（`SettingsActivity` + `about_*` 字符串）。**刻意没有放支持页链接**——那个页面还不存在，宁可少一行也不给死链。
2. **商店简介**：见 §4 文案草案，第一段就说。
3. **README**：已写明。

## 2. 账号与密钥（只有维护者能做）

- [ ] Google Play 开发者账号（一次性 $25）
- [ ] ~~收款所需的 Payments profile~~ **免费上架不需要**（D28 之后省掉了税务与银行这一整段）
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
| 定价 | **免费**。注意 Play 的「免费 → 付费」是**不可逆**的（一个免费应用之后不能改成付费），所以先免费恰好是保留选择权的那一边 |
| 商店资产 | 512×512 图标、1024×500 特征图、≥2 张手机截图（**必须用合成 demo 数据，不得用真实记录**——web 仓隐私红线同样适用） |

## 4. 商店文案草案

**应用名（按语言分别设置，Play 支持逐语言标题，上限 30 字符）**：
- `zh-CN`：**时间尺**
- `en-US`：**Eigentime**（不要用 "Time Logger"——通用词，搜不到、也正是 Apple 自己的
  命名指南明确劝退的那种；描述性文字放简短描述里，标题里放品牌）
- 决策与理由见 web 仓 D29；包名 `org.eigentime.timelogger` **保持不变**（反向域名、
  用户看不见、上架后不可改，没有churn 的收益）
**简短描述（80 字符内）**：5 秒记下真实做了什么，本地离线，一天看清时间去哪了。

**完整描述（第一段就是诚实声明）**：

> 时间尺是开源软件（AGPL-3.0）。源码与免费构建都在 GitHub：
> github.com/wowayou/time-logger-android ；网页版同样永久免费：time.eigentime.org 。
> **免费、没有广告、没有内购、没有订阅**——所有功能永久免费。若愿意支持作者，
> 网站上有一次性支持入口；支持不购买任何东西（不买功能、不买优先权、不买路线影响力）。
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

## 5.5 上架前还欠的非代码项

- [ ] `time.eigentime.org/privacy` 增补一节「Android 应用」（零收集、零联网、本地存储、卸载即删除）
- [ ] **网站支持页**（一次性金额；写明不购买任何东西）——页面上线后再把应用内那一行指过去
- [ ] release 上传密钥（离机备份）
- [ ] 商店资产（512 图标、1024×500 特征图、≥2 张截图，**必须合成 demo 数据**）

## 5.6 发版仪式（与 web 仓对齐）

安卓仓此前没有 tag 与 release 流程，版本锚点全靠 `android_revision.txt` + 同步脚本，
改错了不会有任何检查发红——这是当前最脆的一环。固定流程：

1. `python3 scripts/sync_runtime.py --release`（发版预检：web 仓 clean、commit 可解析、版本三段式、契约有效，全过才写 `app/version.properties` 与资产；日常开发同步用不带 `--release` 的普通模式）
2. 跑满自测（§5 那一串）
3. `./gradlew bundleRelease assembleRelease`（缺 `keystore.properties` 时任务图守卫直接失败——不会再出 debug 签名的假产物）
4. 打 tag：`git tag a<web版本>.<revision>`（web 仓 1.0.0 起是三段式 semver，例如 `a1.0.0.1`；与 web 仓的 `v1.0.0` tag 区分开）
5. `git push origin main --tags`
6. 建 GitHub Release，标题同 tag，**附上 `app-release.apk`**——这就是「免费构建随手可得」
   那句承诺的兑现方式（D28）
7. Release notes 三段：用户影响、内部治理、验证结果；不贴真实数据或截图

## 6. versionCode 方案（2026-09-12 定案）

**取 web semver 派生**：`versionCode = major*10_000_000 + minor*100_000 + patch*1_000 + revision`
（`1.0.0.1` = 10_001_001，大于旧单整数方案产生过的 9301，跨格式不回退；编码上界 minor/patch ≤ 99、
revision ≤ 999 由 android `project_audit.py` 锁住，防跨字段进位撞码）。

**否决** `app/release.properties` 显式计数器方案（v1.0.0 预写条目曾设想）：需要额外出一个状态文件、
自己维护单调性，而 semver 派生零状态、可复算、天然随上游版本走——定案后不再两案并存。
变更只能走 `android_revision.txt` +1（同 web 版本的壳修订）或 web 版本号升级。

## 7. 明确不做

- 不做订阅、不做内购、不做「解锁高级功能」、不做付费上架——那会真的推翻 D7/D28。
- 应用内不放支付界面（连「去支持」按钮都不放支付流程，只放指向网站的普通链接）。
- 不做广告、不接分析 SDK、不加 `INTERNET` 权限。
- 不为了防止免费流通去做许可校验或联网激活（既违背 AGPL，也与本项目的定位冲突）。
- 不上 App Store：Apple 的 Usage Rules 与 GPL 系冲突（LICENSING.md §3 已记）；真要上，走那条「另行授权」的路，是另一个决策。
