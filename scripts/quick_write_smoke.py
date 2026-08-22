#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""一键写入契约的纯逻辑 smoke（docs/DATA-CONTRACT.md §3/§4/§5/§6）。

用真实的 node 导入**真实**的 web 运行时模块和 assets/bridge/quick_write.js——
桩只有 localStorage 和注入的「现在」，业务逻辑一行都不模拟。
先跑 scripts/sync_runtime.py，否则 assets/app 不在位。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
// ---- localStorage 桩（必须在 import 之前装好：模块内是懒读，装晚了也能工作，
// 但 seed 顺序会变得难以推理）----------------------------------------------
const mem = new Map();
const hooks = { readCount: new Map(), onRead: null };
globalThis.localStorage = {
  getItem(k) {
    const key = String(k);
    const n = (hooks.readCount.get(key) || 0) + 1;
    hooks.readCount.set(key, n);
    if (hooks.onRead) hooks.onRead(key, n);
    return mem.has(key) ? mem.get(key) : null;
  },
  setItem(k, v) { mem.set(String(k), String(v)); },
  removeItem(k) { mem.delete(String(k)); },
  clear() { mem.clear(); },
  key(i) { const list = [...mem.keys()]; return i < list.length ? list[i] : null; },
  get length() { return mem.size; }
};

const bridge = await import('./app/src/main/assets/bridge/quick_write.js');
const { isPlaceholderEntry } = await import('./app/src/main/assets/app/src/stats.js');

const TODAY = '2026-08-22';
const CONFIG = {
  mainline: ['当前主线'],
  chips: [
    { name: '睡觉', bucket: 'maintain', longOk: true },
    { name: '刷手机', bucket: 'leak', longOk: false }
  ]
};

let failures = 0;
let checks = 0;
function check(name, cond, detail) {
  checks += 1;
  if (!cond) {
    failures += 1;
    console.error('FAIL ' + name + (detail ? ' — ' + detail : ''));
  }
}
function real(ts, what, tag) { return { id: 'e' + ts, ts, what, tags: [tag] }; }
function placeholder(ts) { return { id: 'p' + ts, ts, what: '', tags: [] }; }
function planned(ts, what, tag) { return { id: 'x' + ts, ts, what, tags: [tag], planned: true }; }

function seed(entries) {
  mem.clear();
  hooks.readCount.clear();
  hooks.onRead = null;
  mem.set('timelog.v1', JSON.stringify({ version: 1, entries }));
  mem.set('timelog.config', JSON.stringify(CONFIG));
  return mem.get('timelog.v1');
}
function entries() { return JSON.parse(mem.get('timelog.v1')).entries; }
function at(ts) { return entries().find(e => e.ts === ts); }
function opts(now) { return { nowTs: TODAY + 'T' + now, todayKey: TODAY }; }

// ---- T1 追认语义：起点＝尾占位点，占位条被**复用**，now 处补新占位 ----------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  const out = bridge.quickWrite('睡觉', opts('10:30'));
  check('T1 写入成功', out.ok, JSON.stringify(out));
  check('T1 起点是尾占位点', out.ts === TODAY + 'T10:00', out.ts);
  check('T1 追认的是刚过去的 30 分钟', out.minutes === 30, String(out.minutes));
  const filled = at(TODAY + 'T10:00');
  check('T1 占位条被复用（id 不变）', filled && filled.id === 'p' + TODAY + 'T10:00', JSON.stringify(filled));
  check('T1 what 非空（契约 §5：空 what 在数据层就是占位条）',
    filled && !isPlaceholderEntry(filled), JSON.stringify(filled));
  check('T1 what 取标签名', filled && filled.what === '睡觉', filled && filled.what);
  const tail = entries()[entries().length - 1];
  check('T1 now 处补出新占位', tail.ts === TODAY + 'T10:30' && isPlaceholderEntry(tail), JSON.stringify(tail));
  check('T1 总条数 3（复用而非新增）', entries().length === 3, String(entries().length));
}

// ---- T2 守卫：今天一条记录都没有时不静默写（起点会落在 00:00）--------------
{
  const before = seed([real('2026-08-21T22:00', '睡觉', '睡觉')]);
  const out = bridge.quickWrite('睡觉', opts('10:30'));
  check('T2 fresh-day 被拦下', !out.ok && out.reason === 'fresh-day', JSON.stringify(out));
  check('T2 数据一个字节都没动', mem.get('timelog.v1') === before);
}

// ---- T3 守卫：空白超过上限（默认 240 分钟）时不静默写 -----------------------
{
  const before = seed([real(TODAY + 'T04:00', '睡觉', '睡觉'), placeholder(TODAY + 'T05:00')]);
  const out = bridge.quickWrite('睡觉', opts('10:30'));
  check('T3 gap-too-large 被拦下', !out.ok && out.reason === 'gap-too-large', JSON.stringify(out));
  check('T3 给出建议起点供表单预填', out.suggestTs === TODAY + 'T05:00', out.suggestTs);
  check('T3 数据未变', mem.get('timelog.v1') === before);
}

// ---- T4 一键不新建标签（契约 §7）------------------------------------------
{
  const before = seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  const out = bridge.quickWrite('还没建过的标签', opts('10:30'));
  check('T4 未知标签被拒', !out.ok && out.reason === 'unknown-tag', JSON.stringify(out));
  check('T4 数据未变', mem.get('timelog.v1') === before);
}

// ---- T5 同分钟修正：尾点是刚写下的零时长记录时改写它，而不是再堆一条 --------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), real(TODAY + 'T10:30', '睡觉', '睡觉')]);
  const out = bridge.quickWrite('刷手机', opts('10:30'));
  check('T5 走同分钟修正', out.ok && out.mode === 'same-minute-correction', JSON.stringify(out));
  check('T5 条数不变', entries().length === 2, String(entries().length));
  const tail = at(TODAY + 'T10:30');
  check('T5 标签与内容被改写', tail.what === '刷手机' && tail.tags[0] === '刷手机', JSON.stringify(tail));
}

// ---- T6 今天已记到 23:59：没有合法起点，绝不越午夜 -------------------------
{
  const before = seed([real(TODAY + 'T23:59', '睡觉', '睡觉')]);
  const out = bridge.quickWrite('睡觉', opts('22:00'));
  check('T6 no-slot 被拦下', !out.ok && out.reason === 'no-slot', JSON.stringify(out));
  check('T6 没有写进第二天', mem.get('timelog.v1') === before);
}

// ---- T7 跨端 CAS：写入前发现别处刚写过就中止（不覆盖对方）------------------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  const intruder = JSON.stringify({ version: 1, entries: [real(TODAY + 'T08:00', '别处写的', '当前主线')] });
  // 第 2 次读 timelog.v1 正是 saveChecked 里的 readRaw()——模拟另一个 WebView
  // 恰在 loadSnapshot 与写入之间落库。
  hooks.onRead = (key, n) => { if (key === 'timelog.v1' && n === 2) mem.set('timelog.v1', intruder); };
  const out = bridge.quickWrite('睡觉', opts('10:30'));
  hooks.onRead = null;
  check('T7 并发写入被 CAS 拦下', !out.ok && out.reason === 'concurrent', JSON.stringify(out));
  check('T7 对方的数据完好', mem.get('timelog.v1') === intruder);
}

// ---- T8 撤销：数据未被别处改过时逐字回滚 -----------------------------------
{
  const before = seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  const wrote = bridge.quickWrite('睡觉', opts('10:30'));
  check('T8 前置写入成功', wrote.ok, JSON.stringify(wrote));
  const undone = bridge.undoLastQuickWrite();
  check('T8 撤销成功', undone.ok, JSON.stringify(undone));
  check('T8 数据逐字回到写入前', mem.get('timelog.v1') === before, mem.get('timelog.v1'));
  check('T8 撤销不可重放', !bridge.undoLastQuickWrite().ok);
}

// ---- T9 撤销的守卫：写入之后数据又被改过就不撤销（否则连带抹掉那些改动）----
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  bridge.quickWrite('睡觉', opts('10:30'));
  const meddled = JSON.parse(mem.get('timelog.v1'));
  meddled.entries.push(real(TODAY + 'T11:00', '界面里加的', '当前主线'));
  mem.set('timelog.v1', JSON.stringify(meddled));
  const undone = bridge.undoLastQuickWrite();
  check('T9 数据已变则拒绝撤销', !undone.ok && undone.reason === 'changed-since', JSON.stringify(undone));
  check('T9 界面里那条改动还在', Boolean(at(TODAY + 'T11:00')));
}

// ---- T10 计划记录不受影响，且不会造出同刻重复 ------------------------------
{
  seed([
    real(TODAY + 'T09:00', '写代码', '当前主线'),
    placeholder(TODAY + 'T10:00'),
    planned(TODAY + 'T20:00', '面试', '当前主线')
  ]);
  const out = bridge.quickWrite('睡觉', opts('10:30'));
  check('T10 写入成功', out.ok, JSON.stringify(out));
  const plannedStill = entries().find(e => e.planned);
  check('T10 计划条原样保留', plannedStill && plannedStill.ts === TODAY + 'T20:00', JSON.stringify(plannedStill));
  const stamps = entries().map(e => e.ts);
  check('T10 同刻唯一', new Set(stamps).size === stamps.length, stamps.join(','));
}

// ---- T11 显示镜像（契约 §6）：原生侧要的字段齐、且不含多余数据 --------------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  bridge.quickWrite('睡觉', opts('10:30'));
  const mirror = JSON.parse(mem.get('timelog.widgetMirror.v1'));
  check('T11 下一次起点＝此刻', mirror.nextStartTs === TODAY + 'T10:30', mirror.nextStartTs);
  check('T11 上一条是刚写的那条', mirror.lastWhat === '睡觉' && mirror.lastTs === TODAY + 'T10:00',
    JSON.stringify(mirror));
  check('T11 建议标签以当前主线开头', mirror.suggestTags[0] === '当前主线', JSON.stringify(mirror.suggestTags));
  check('T11 建议标签只含已存在的标签',
    mirror.suggestTags.every(t => t === '当前主线' || t === '睡觉' || t === '刷手机'),
    JSON.stringify(mirror.suggestTags));
  check('T11 可以继续一键写', mirror.canQuickWrite === true, JSON.stringify(mirror));
  const keys = Object.keys(mirror).sort().join(',');
  check('T11 镜像字段固定（改了要同步契约 §6）',
    keys === 'blockedReason,canQuickWrite,computedAt,gapMinutes,lastTag,lastTs,lastWhat,nextStartTs,'
      + 'suggestTags,tailIsPlaceholder,v', keys);
}

// ---- T12 关掉「小组件显示上一条内容」后镜像里不带正文 ----------------------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  mem.set('timelog.androidPrefs.v1', JSON.stringify({ showLastWhatOnWidget: false }));
  bridge.quickWrite('睡觉', opts('10:30'));
  const mirror = JSON.parse(mem.get('timelog.widgetMirror.v1'));
  check('T12 镜像不含记录正文', mirror.lastWhat === '', JSON.stringify(mirror));
  check('T12 标签仍在（小组件要显示归类）', mirror.lastTag === '睡觉', JSON.stringify(mirror));
}

// ---- T13 上限可调：调低后同一份数据就该被拦下 ------------------------------
{
  const before = seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  mem.set('timelog.androidPrefs.v1', JSON.stringify({ maxSilentGapMinutes: 10 }));
  const out = bridge.quickWrite('睡觉', opts('10:30'));
  check('T13 自定义上限生效', !out.ok && out.reason === 'gap-too-large' && out.limit === 10, JSON.stringify(out));
  check('T13 数据未变', mem.get('timelog.v1') === before);
}

// ---- T14 通知直接回复：文本里的 #标签 优先，且 token 从 what 里去掉 -----------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  const out = bridge.quickWrite('当前主线', Object.assign(opts('10:30'), { what: '#刷手机 刷了会儿新闻' }));
  check('T14 写入成功', out.ok, JSON.stringify(out));
  check('T14 采用文本里的标签而不是通知携带的', out.tag === '刷手机', out.tag);
  const filled = at(TODAY + 'T10:00');
  check('T14 token 已从 what 里去掉', filled && filled.what === '刷了会儿新闻', filled && filled.what);
}

// ---- T15 认不出的 #xxx 原样留在文本里，标签退回通知携带的那个 ----------------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  const out = bridge.quickWrite('睡觉', Object.assign(opts('10:30'), { what: '#1 优先级的事' }));
  check('T15 写入成功', out.ok, JSON.stringify(out));
  check('T15 标签仍是通知携带的', out.tag === '睡觉', out.tag);
  const filled = at(TODAY + 'T10:00');
  check('T15 用户打的字一个都没丢', filled && filled.what === '#1 优先级的事', filled && filled.what);
}

// ---- T16 只打 #标签、没有正文时，what 退回标签名（不能变成占位条）------------
{
  seed([real(TODAY + 'T09:00', '写代码', '当前主线'), placeholder(TODAY + 'T10:00')]);
  const out = bridge.quickWrite('当前主线', Object.assign(opts('10:30'), { what: '#睡觉' }));
  const filled = at(TODAY + 'T10:00');
  check('T16 what 非空', out.ok && filled && filled.what === '睡觉', JSON.stringify(filled));
  check('T16 不是占位条', filled && !isPlaceholderEntry(filled));
}

console.log((failures ? 'FAILED ' : 'OK ') + (checks - failures) + '/' + checks + ' 断言通过');
if (failures) process.exit(1);
'''


def main() -> int:
    if not (ROOT / "app/src/main/assets/app/src/stats.js").exists():
        print("内嵌运行时不在位：先跑 python3 scripts/sync_runtime.py", file=sys.stderr)
        return 2
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=HARNESS, text=True, encoding="utf-8",
        capture_output=True, cwd=ROOT, check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
