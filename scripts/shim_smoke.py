#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""localStorage 桥（assets/bridge/store_shim.js）的纯逻辑 smoke。

桥是「web 运行时零改动」这件事的全部依托：它必须在 window 上盖住原生的
localStorage、把同步语义逐条转给 @JavascriptInterface，并在写不下时**抛异常**
（storage.js 的 save() 只判断抛没抛）。这里用一个行为对齐 NativeStore 的假原生对象
把这些逐条钉住，然后让**真实的 storage.js** 通过桥读写一遍。

node 没有 StorageEvent，所以顺带覆盖了桥里的降级分支。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
import { readFileSync } from 'node:fs';

let failures = 0, checks = 0;
function check(name, cond, detail) {
  checks += 1;
  if (!cond) { failures += 1; console.error('FAIL ' + name + (detail ? ' — ' + detail : '')); }
}

// ---- 行为对齐 NativeStore.kt 的假原生对象 ---------------------------------
const files = new Map();
let quotaFrom = null;              // 设成某个键名后，对它的写入返回配额错误
const native = {
  getItem: k => (files.has(k) ? files.get(k) : null),
  setItem: (k, v) => {
    if (quotaFrom && k === quotaFrom) return 'QuotaExceededError';   // 与 Kotlin 侧同款返回值
    files.set(k, v);
    return null;
  },
  removeItem: k => { files.delete(k); },
  clear: () => files.clear(),
  key: i => { const list = [...files.keys()]; return i < list.length ? list[i] : null; },
  length: () => files.size,
  onShimFailed: m => { shimFailed = m; }
};
let shimFailed = null;

// ---- 假 window：localStorage 是**原型上的 getter**（浏览器里就是这样），
// 这样才能真的验证 defineProperty 能不能盖住它 ----------------------------
const builtinStorage = { getItem: () => 'WEBVIEW-OWN-STORAGE', setItem: () => {}, removeItem: () => {} };
class FakeWindow extends EventTarget {}
Object.defineProperty(FakeWindow.prototype, 'localStorage', { get: () => builtinStorage, configurable: true });
const win = new FakeWindow();
win.__tlNative = native;
const navProto = {};
Object.defineProperty(navProto, 'serviceWorker', { get: () => ({ real: true }), configurable: true });
const nav = Object.create(navProto);
globalThis.window = win;
// node 24 自带一个只有 getter 的全局 navigator，只能 defineProperty 覆盖
Object.defineProperty(globalThis, 'navigator', { value: nav, configurable: true, writable: true });
check('前置：原型上的 localStorage 生效', win.localStorage.getItem('x') === 'WEBVIEW-OWN-STORAGE');

// ---- 装桥（就是 WebView 里 document-start 注入的那份源码，不是副本）--------
const shimSrc = readFileSync('./app/src/main/assets/bridge/store_shim.js', 'utf8');
new Function('window', 'navigator', shimSrc)(win, nav);

check('桥盖住了原生 localStorage', win.localStorage.getItem('x') === null, String(win.localStorage.getItem('x')));
check('桥没有报告安装失败', shimFailed === null, String(shimFailed));

// ---- 同步语义逐条 -------------------------------------------------------
const ls = win.localStorage;
ls.setItem('timelog.v1', '{"entries":[]}');
check('setItem/getItem 往返', ls.getItem('timelog.v1') === '{"entries":[]}');
check('缺失的键是 null 而不是空串', ls.getItem('timelog.nope') === null, JSON.stringify(ls.getItem('timelog.nope')));
ls.setItem('a', '1');
check('length 反映原生侧', ls.length === 2, String(ls.length));
check('key(i) 可枚举', [ls.key(0), ls.key(1)].includes('a'), JSON.stringify([ls.key(0), ls.key(1)]));
ls.removeItem('a');
check('removeItem 生效', ls.getItem('a') === null && ls.length === 1);

// ---- 配额：必须**抛**，否则 storage.js 的 save() 会以为写成功了 -----------
quotaFrom = 'timelog.v1';
let threw = null;
try { ls.setItem('timelog.v1', 'x'); } catch (e) { threw = e; }
check('写不下时抛异常', threw !== null);
check('异常名是 QuotaExceededError', threw && threw.name === 'QuotaExceededError', threw && threw.name);
quotaFrom = null;

// ---- Service Worker 桩：'in' 仍为 true，且 register() 是可被 catch 的 reject ----
check("'serviceWorker' in navigator 仍为 true（app.js 先判断的正是这个）",
  ('serviceWorker' in navigator) === true);
check('拿到的是桩不是真实对象', navigator.serviceWorker.real === undefined);
check('addEventListener 不抛', (() => { try { navigator.serviceWorker.addEventListener('x', () => {}); return true; } catch (e) { return false; } })());
let registerRejected = false;
await navigator.serviceWorker.register('sw.js').catch(() => { registerRejected = true; });
check('register() 走 reject（app.js 那边有 .catch）', registerRejected);
check('getRegistration() 给 undefined（app.js 那边有 if (!reg)）',
  (await navigator.serviceWorker.getRegistration()) === undefined);

// ---- 变更通知：原生写入后要能让界面按跨标签逻辑刷新 ----------------------
let seen = null;
win.addEventListener('storage', e => { seen = { key: e.key, newValue: e.newValue }; });
win.__tlNotifyStorage('timelog.v1', '{"entries":[1]}', '{"entries":[]}');
check('storage 事件到达（node 无 StorageEvent，走降级分支）',
  seen && seen.key === 'timelog.v1' && seen.newValue === '{"entries":[1]}', JSON.stringify(seen));

// ---- 真实 storage.js 通过桥读写一遍 -------------------------------------
globalThis.localStorage = win.localStorage;   // 模块里用的是全局 localStorage
const storage = await import('./app/src/main/assets/app/src/storage.js');
files.clear();
const entry = { id: 'a1', ts: '2026-08-22T09:00', what: '写代码', tags: ['当前主线'] };
check('save() 成功', storage.save({ version: 1, entries: [entry] }) === true);
const snap = storage.loadSnapshot();
check('loadSnapshot 拿到同一份数据', snap.data.entries[0].what === '写代码');
check('raw 与原生文件逐字一致（CAS 的前提）', snap.raw === files.get('timelog.v1'));
check('saveChecked 在 raw 匹配时通过', storage.saveChecked({ version: 1, entries: [] }, snap.raw).ok === true);
check('saveChecked 在 raw 不匹配时中止', storage.saveChecked({ version: 1, entries: [] }, '过期的raw').reason === 'concurrent');
quotaFrom = 'timelog.v1';
check('配额失败时 save() 返回 false 而不是抛出去', storage.save({ version: 1, entries: [] }) === false);
quotaFrom = null;

console.log((failures ? 'FAILED ' : 'OK ') + (checks - failures) + '/' + checks + ' 断言通过');
if (failures) process.exit(1);
'''


def main() -> int:
    if not (ROOT / "app/src/main/assets/app/src/storage.js").exists():
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
