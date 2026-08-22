# 一键写入数据契约（权威）

> 适用范围：`time-logger-android` 里**任何**不经过 web 表单就写入 `timelog.v1` 的入口
> ——主屏小组件、快捷设置磁贴、通知快捷动作、通知直接回复、长按图标快捷方式。
>
> 上游真源：`wowayou/time-logger`（web 运行时）。本文件只描述**约束**，不复制算法。

## 0. 一句话

一键写入的含义是「**上次记录点 → 现在**这段时间，我在做 X」——**追认刚过去的那一段**，
不是「从此刻开始做 X」。

## 1. 为什么是追认，不是开始计时

web 运行时的记录模型里，一条记录只存**起点** `ts`，时长由**下一条记录**推断
（`settlementEndFor`）。新建表单的默认起点来自 `defaultFormTimestamp(entries, dateKey)`
（`src/entry_model.js`），它返回的是**当天尾占位点**——也就是你上一次记录落下的那个时刻。
保存后 `normalizeEntries()` 会在 `now` 补一条新的空占位条。

所以「点一下」的净效果是：

```
[上次记录点, 现在)  →  标记为 X
[现在, ...)         →  新的未记录占位（等下一次记录来盖）
```

「从此刻开始做 X」在 web 运行时里是 **`planned` 分支**（计划记录，`ts` 必须晚于
`now + 5min`），语义完全不同。原生入口默认**不得**使用 planned 语义；若将来提供，
必须是用户显式选择的可选项，且在 UI 上与追认明确区分。

## 2. 硬约束：原生代码不实现业务逻辑

| 谁 | 允许 | 禁止 |
|---|---|---|
| Kotlin 侧 | 存储读写（键→字符串）、进程/线程/生命周期、通知与小组件的**呈现**、时长的纯格式化 | 解析 `timelog.v1` 的结构、计算起点/结束点/时长、判断占位条、写入任何记录字段 |
| JS 胶水（`assets/bridge/`） | `import` web 运行时的**真实模块**并调用 | 复制粘贴 web 逻辑、绕过 `normalizeEntries` / `saveChecked` |
| web 运行时（`assets/app/`） | 原封不动运行 | **一个字节都不许改**（同步脚本按 `sw.js` 的 `FILES` 逐字复制） |

理由：`defaultFormTimestamp` 的分流规则（占位条 / `ongoing` / 尾点是真实记录 / 23:59 无空位）、
`coalesceRedundant`、跨日上限、同刻唯一——这些规则在 web 仓里每个版本都在长记性
（v77、v87、v88 各改过一次）。用 Kotlin 重写一份等于给同一份数据两套真理，第一次
漂移就是静默改写用户的时间线（web 仓 D13 硬约束③）。

## 3. 写入序列（由 `assets/bridge/quick_write.mjs` 执行）

1. `loadSnapshot()` —— **一次** `getItem`，同时取回解析对象与逐字 raw（web 仓 v93）。
2. `ts = defaultFormTimestamp(entries, todayKey)`；返回空串＝当天无合法起点 → **中止**。
3. 守卫（见 §4）不通过 → **不写**，返回 `{ok:false, reason}`，由原生侧改为「打开 App 并预填」。
4. `tag = canonicalTagName(输入标签, loadConfig())`；`what = tag`（**不得为空**，见 §5）。
5. 占位条复用规则完全交给 web 逻辑：`openPlaceholderForDate` + `ts > placeholder.ts` 时不复用（v87）。
6. `findTimeConflict` 命中且不是占位条 → **中止**（返回 `reason:'conflict'`）。
7. `normalizeEntries(d, { todayKey, createId })` —— 唯一出口，恒补今天尾占位。
8. `saveChecked(d, raw)` —— CAS。`reason:'concurrent'` 表示别处（另一个 WebView / 另一次点击）
   刚写过 → **中止并如实告知**，绝不重试覆盖。
9. 成功后写显示镜像（§6）并广播 `storage` 事件，让已打开的界面自己刷新。

## 4. 守卫：什么时候「不许静默写」

| 条件 | 处置 | 为什么 |
|---|---|---|
| 默认起点距现在 > `maxSilentGapMinutes`（默认 **240**） | 打开 App 预填表单 | 一次点击就给 4 小时以上的空白盖一个标签，用户没有看见起点的机会 |
| 当天一条记录都没有（起点 = 当日 00:00） | 打开 App 预填表单 | 同上，且必然横跨整夜 |
| `defaultFormTimestamp` 返回空串（尾点已压到 23:59） | 提示「今天没有可写的起点」，不跨午夜 | web 仓 v77：绝不把默认值越过午夜写进第二天 |
| 同刻已有**非占位**记录 | 中止并提示 | 同刻唯一是导入/事务 planner 的共同前提（v88） |
| 尾点是**零时长**记录（`ts == now`，刚刚一键写下的那条） | 允许**改写它的标签与 what**（同分钟修正） | 那条记录覆盖 0 分钟，改它不丢任何时间；否则用户点错标签后无法补救 |
| `saveChecked` 返回 `concurrent` / 配额失败 | 中止并提示 | 不重试、不无条件 `save()`（web 仓 v92/v93） |

`maxSilentGapMinutes` 存在 `timelog.androidPrefs.v1`（**设备偏好，不进备份**，与
`timelog.theme` 同类），可在 App 内调整；不得随备份导出/导入。

## 5. `what` 不能为空

`isPlaceholderEntry()`（`src/stats.js`）的判据是 `what.trim() === ''`，**不看 tags**。
也就是说「空 what + 有标签」在数据层就是一条**未记录占位条**，不是记录。
所以一键写入必须给 `what` 填内容；取值是**按钮上的标签名本身**，与用户在表单里
手敲同一个词的结果逐字相同（`canonicalTagName` 先把拼写规范化，见 web 仓 v85）。

通知直接回复提供了真正的文本：此时 `what` = 用户输入，`tag` = 该通知携带的标签。

## 6. 显示镜像 `timelog.widgetMirror.v1`

小组件/磁贴需要显示「距上次记录多久」和常用标签，但原生侧不许解析 `timelog.v1`。
因此每次写入后由 JS 胶水计算并写入镜像键：

```json
{
  "v": 1,
  "computedAt": "2026-08-22T13:05",
  "lastTs": "2026-08-22T12:40",
  "lastWhat": "写代码",
  "lastTag": "当前主线",
  "tailIsPlaceholder": true,
  "suggestTags": ["当前主线", "睡觉", "吃饭", "刷手机"],
  "canQuickWrite": true,
  "blockedReason": ""
}
```

- 原生侧只做**纯格式化**：`now - lastTs` 的分时换算与本地化字符串。
- 镜像**不进备份**、不参与统计、丢了可以重算；它是缓存，不是数据。
- 镜像里**不得**出现记录正文以外的任何用户数据；`lastWhat` 会显示在小组件上，
  用户可在 App 内关闭「小组件显示上一条内容」（默认开），关闭后镜像只写标签。

## 7. 不许做的事（对齐 web 仓红线）

- 不自动盖「长段确认」章：`longConfirm` 只能由用户显式确认写入（web 仓 v87 撤销 C7A）。
- 不静默扩张前一条记录的覆盖范围（v87 占位条守卫）。
- 不自动创建、合并、删除标签配置；一键写入只能用**已存在**的标签。
  通知直接回复里出现的新词只写进 `what`，不新建标签。
- 不上传、不联网。APK 内嵌全部运行时，`INTERNET` 权限不声明。
- 不替用户开启 `longReview`；不修改 `timelog.theme` / `timelog.locale`。

## 8. 测试要求

- `scripts/quick_write_smoke.py`：用 node 导入**真实** web 模块 + `quick_write.mjs`，
  对 §3/§4 每一条分支各断言一次（含反向哨兵：起点早于占位点时仍复用）。
- 每条守卫必须有一次「**撤掉守卫就变红**」的记录（web 仓 P35 纪律）。
- JVM 单测覆盖 `NativeStore` 的原子写、并发读写、raw 逐字一致。
