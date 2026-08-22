// 时间尺 Android 壳 (time-logger-android)
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// 浏览器级验收：在真实 Chromium 里按 **APK 的资产布局** 加载未经修改的 web 运行时，
// 只把 localStorage 换成桥。它回答的是「这套装配到底跑不跑得起来」——
// 模块能不能加载、桥会不会挡住启动、原生写入后界面会不会刷新、sw.js 有没有被注册。
//
// 由 scripts/shell_browser_check.py 启动（它负责起静态服务器并注入 NODE_PATH）。
// 假的原生存储用页面**原始**的 localStorage 加前缀实现：同源、同步、两页共享，
// 与 NativeStore 的可见行为一致（NativeStore 自身有 JVM 单测）。
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const BASE = process.env.SHELL_CHECK_BASE;
const ASSETS = process.env.SHELL_CHECK_ASSETS;
const PW = process.env.SHELL_CHECK_PLAYWRIGHT;
if (!BASE || !ASSETS || !PW) throw new Error('缺少 SHELL_CHECK_BASE / SHELL_CHECK_ASSETS / SHELL_CHECK_PLAYWRIGHT');
// ESM 不认 NODE_PATH，所以按绝对路径动态导入 web 仓里那份 Playwright（同机开发期复用）。
const pwModule = await import(pathToFileURL(PW).href);
const { chromium } = pwModule.default ?? pwModule;

const shimSrc = readFileSync(`${ASSETS}/bridge/store_shim.js`, 'utf8');
const TODAY = new Date();
const pad = n => String(n).padStart(2, '0');
const dayKey = `${TODAY.getFullYear()}-${pad(TODAY.getMonth() + 1)}-${pad(TODAY.getDate())}`;

let failures = 0, checks = 0;
function check(name, cond, detail) {
  checks += 1;
  if (!cond) { failures += 1; console.error('FAIL ' + name + (detail ? ' — ' + detail : '')); }
}

// 页面里的假原生对象：必须在 shim 之前就位，并且抓住**原始** localStorage
const FAKE_NATIVE = `
(function () {
  var raw = window.localStorage;
  var P = 'native:';
  window.__tlNative = {
    getItem: function (k) { var v = raw.getItem(P + k); return v === null ? null : v; },
    setItem: function (k, v) { raw.setItem(P + k, v); return null; },
    removeItem: function (k) { raw.removeItem(P + k); },
    clear: function () { raw.clear(); },
    key: function (i) {
      var keys = [];
      for (var n = 0; n < raw.length; n++) { var kk = raw.key(n); if (kk.indexOf(P) === 0) keys.push(kk.slice(P.length)); }
      keys.sort();
      return i < keys.length ? keys[i] : null;
    },
    length: function () {
      var c = 0;
      for (var n = 0; n < raw.length; n++) { if (raw.key(n).indexOf(P) === 0) c++; }
      return c;
    },
    onBridgeReady: function () { window.__tlBridgeReadySignal = true; },
    onShimFailed: function (m) { window.__tlShimFailed = m; }
  };
})();
`;

const browser = await chromium.launch();
const context = await browser.newContext();
await context.addInitScript(FAKE_NATIVE);
await context.addInitScript(shimSrc);

const swRequests = [];
context.on('request', req => { if (req.url().endsWith('sw.js')) swRequests.push(req.url()); });

const errors = [];
const page = await context.newPage();
page.on('pageerror', e => errors.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

// ---- 1. 播种数据（走桥写入，等于原生侧先有一份数据）----------------------
await page.goto(`${BASE}/app/index.html`, { waitUntil: 'domcontentloaded' });
await page.evaluate(({ dayKey }) => {
  const data = {
    version: 1,
    entries: [
      { id: 'seed1', ts: dayKey + 'T09:00', what: '写代码', tags: ['当前主线'] },
      { id: 'seed2', ts: dayKey + 'T10:00', what: '', tags: [] }
    ]
  };
  const config = {
    mainline: ['当前主线'],
    chips: [
      { name: '睡觉', bucket: 'maintain', longOk: true },
      { name: '刷手机', bucket: 'leak', longOk: false }
    ]
  };
  window.__tlNative.setItem('timelog.v1', JSON.stringify(data));
  window.__tlNative.setItem('timelog.config', JSON.stringify(config));
  window.__tlNative.setItem('timelog.selectedDate', dayKey);
}, { dayKey });

await page.reload({ waitUntil: 'load' });
await page.waitForSelector('body.app-ready', { timeout: 15000 });
check('运行时在桥上正常启动（app-ready）', true);
check('启动过程没有页面异常', errors.length === 0, errors.slice(0, 2).join(' | '));

// ---- 2. 数据确实是从桥读的 ------------------------------------------------
const timeline = await page.textContent('#timeline');
check('时间轴渲染出桥里的记录', timeline.includes('写代码'), timeline.slice(0, 120));
const usesShim = await page.evaluate(() => {
  // 桥装上后，localStorage 不再是 WebView 自己那份：写一个键，它应该出现在原生侧
  localStorage.setItem('probe.key', 'v');
  return window.__tlNative.getItem('probe.key') === 'v';
});
check('页面的 localStorage 走的是桥', usesShim);

// ---- 3. Service Worker 没有被注册（APK 里它只会造成「升了包还是旧界面」）----
const swState = await page.evaluate(async () => ({
  present: 'serviceWorker' in navigator,
  reg: await navigator.serviceWorker.getRegistration().then(r => (r ? 'has' : 'none')).catch(() => 'threw')
}));
check("'serviceWorker' in navigator 仍为 true", swState.present === true);
check('没有任何注册', swState.reg === 'none', String(swState.reg));
check('页面没有去取 sw.js', swRequests.length === 0, swRequests.join(','));

// ---- 4. 无界面桥页在同源里一键写入 --------------------------------------
const bridgePage = await context.newPage();
const bridgeErrors = [];
bridgePage.on('pageerror', e => bridgeErrors.push(e.message));
await bridgePage.goto(`${BASE}/bridge/headless.html`, { waitUntil: 'load' });
await bridgePage.waitForFunction(() => window.__tlBridgeReady === true, null, { timeout: 10000 });
check('桥页就绪（模块从 assets 加载成功）', true);
check('桥页向原生报告过 ready', await bridgePage.evaluate(() => window.__tlBridgeReadySignal === true));
check('桥页没有异常', bridgeErrors.length === 0, bridgeErrors.join(' | '));

const out = await bridgePage.evaluate(({ dayKey }) => {
  const now = dayKey + 'T10:30';
  return window.__tlBridge.quickWrite('睡觉', { nowTs: now, todayKey: dayKey });
}, { dayKey });
check('一键写入成功', out && out.ok === true, JSON.stringify(out));
check('起点是尾占位点', out && out.ts === dayKey + 'T10:00', out && out.ts);

const stored = await bridgePage.evaluate(() => JSON.parse(window.__tlNative.getItem('timelog.v1')));
const written = stored.entries.find(e => e.ts === dayKey + 'T10:00');
check('数据落在同一份存储里', written && written.what === '睡觉', JSON.stringify(written));
const mirror = await bridgePage.evaluate(() => JSON.parse(window.__tlNative.getItem('timelog.widgetMirror.v1')));
check('显示镜像已写入（小组件的数据源）', mirror && mirror.nextStartTs === dayKey + 'T10:30', JSON.stringify(mirror));

// ---- 5. 原生写入后界面刷新（Kotlin 侧就是这么通知的）--------------------
const before = await page.textContent('#timeline');
check('刷新前界面还没有那条记录', !before.includes('睡觉'), before.slice(0, 120));
await page.evaluate(({ raw }) => {
  window.__tlNotifyStorage('timelog.v1', raw, null);
}, { raw: JSON.stringify(stored) });
await page.waitForFunction(() => document.getElementById('timeline').textContent.includes('睡觉'), null, { timeout: 5000 })
  .then(() => check('storage 事件让界面重渲染', true))
  .catch(() => check('storage 事件让界面重渲染', false, '5 秒内没出现'));

// ---- 6. 外链不会把 WebView 导航走（Kotlin 侧拦 shouldOverrideUrlLoading，
// 这里只确认页面里确实有那个外链，改名了要知道）--------------------------
const externalHref = await page.evaluate(() => {
  const a = document.querySelector('a[href^="https://github.com"]');
  return a ? a.getAttribute('href') : '';
});
check('站点标识的 GitHub 外链仍在（壳靠它判断要不要交给系统浏览器）',
  externalHref.startsWith('https://github.com'), externalHref);

await browser.close();
console.log((failures ? 'FAILED ' : 'OK ') + (checks - failures) + '/' + checks + ' 断言通过');
process.exit(failures ? 1 : 0);
