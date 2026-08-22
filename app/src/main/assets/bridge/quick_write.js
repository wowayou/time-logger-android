// 时间尺 Android 壳 —— 一键写入胶水
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// 契约见 docs/DATA-CONTRACT.md。这里只做**编排**：起点、占位条复用、同刻冲突、
// 归一化、CAS 全部调用 web 运行时的真实模块，一行业务规则都不复制。
import {
  canonicalTagName,
  loadConfig,
  loadSnapshot,
  readRaw,
  saveChecked,
  tagKey,
  uid
} from '../app/src/storage.js';
import {
  defaultFormTimestamp,
  findTimeConflict,
  normalizeEntries,
  openPlaceholderForDate
} from '../app/src/entry_model.js';
import { isPlaceholderEntry, loggedEntriesFrom } from '../app/src/stats.js';
import { nowStr, todayStr } from '../app/src/time.js';

export const MIRROR_KEY = 'timelog.widgetMirror.v1';
export const PREFS_KEY = 'timelog.androidPrefs.v1';
export const DEFAULT_MAX_SILENT_GAP = 240;

function readPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export function maxSilentGapMinutes(prefs = readPrefs()) {
  const n = Number(prefs.maxSilentGapMinutes);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : DEFAULT_MAX_SILENT_GAP;
}

export function showLastWhatOnWidget(prefs = readPrefs()) {
  return prefs.showLastWhatOnWidget !== false;
}

// 本地壁钟差值。时间戳是 'YYYY-MM-DDTHH:mm' 的本地值，不做时区转换（web 仓红线）。
function toLocalDate(ts) {
  const [datePart, timePart] = String(ts).split('T');
  const [y, m, d] = datePart.split('-').map(Number);
  const [hh, mm] = timePart.split(':').map(Number);
  return new Date(y, m - 1, d, hh, mm, 0, 0);
}

export function minutesBetween(fromTs, toTs) {
  return Math.round((toLocalDate(toTs) - toLocalDate(fromTs)) / 60000);
}

function tagExists(tag, config) {
  const key = tagKey(tag);
  if (!key) return false;
  if (config.mainline.some(item => tagKey(item) === key)) return true;
  return config.chips.some(chip => tagKey(chip.name) === key);
}

function entriesOnDay(entries, dayKey) {
  return loggedEntriesFrom(entries).filter(e => e.ts.slice(0, 10) === dayKey);
}

/**
 * 从用户敲的文本里认出 `#标签`（通知直接回复的场景：键盘已经在手上，标签不该受
 * 通知只能放 3 个动作的限制）。
 *
 * 只认**已存在**的标签（契约 §7：一键路径绝不顺手建标签）；认不出就原样留在文本里，
 * 不静默丢掉用户打的字。命中后把该 token 从 what 里去掉，剩下的才是「做了什么」。
 *
 * @returns {{tag: string, what: string}} tag 为空表示没认出来
 */
export function resolveTagFromText(text, config) {
  const raw = String(text || '');
  const tokens = raw.match(/#[^\s#]+/g) || [];
  for (const token of tokens) {
    const candidate = canonicalTagName(token.slice(1), config);
    if (candidate && tagExists(candidate, config)) {
      const what = raw.replace(token, ' ').replace(/\s+/g, ' ').trim();
      return { tag: candidate, what };
    }
  }
  return { tag: '', what: raw.trim() };
}

function fail(reason, extra = {}) {
  return Object.assign({ ok: false, reason }, extra);
}

// 撤销只覆盖「刚刚这一次一键写入」，且只在数据从那以后没被别处改过时才允许。
// 存在进程里而不是存进 localStorage：进程被系统回收后撤销窗口自然结束，
// 不留一个能在任意时刻回滚数据的持久后门。
let lastQuickWrite = null;

/**
 * 只回答「此刻一键写会发生什么」，不写入。quickWrite 与显示镜像共用它——守卫条件
 * 只有这一份，免得「小组件说能写」和「真的写」在两处漂移。
 */
function probeWith(data, nowTs, todayKey) {
  const dayEntries = entriesOnDay(data.entries, todayKey);
  const tail = dayEntries.length ? dayEntries[dayEntries.length - 1] : null;
  // 同分钟修正（契约 §4）：尾点是刚刚一键写下的那条零时长记录。
  if (tail && !isPlaceholderEntry(tail) && !tail.planned && tail.ts === nowTs) {
    return { ok: true, mode: 'same-minute-correction', ts: nowTs, gapMinutes: 0, tail, dayEntries };
  }
  const ts = defaultFormTimestamp(data.entries, todayKey);
  // v77：尾点压到 23:59 时当天没有合法起点，绝不越午夜写进第二天。
  if (!ts) return { ok: false, reason: 'no-slot', dayEntries, tail };
  const gapMinutes = minutesBetween(ts, nowTs);
  if (gapMinutes < 0) return { ok: false, reason: 'start-in-future', ts, gapMinutes, dayEntries, tail };
  // 契约 §4：这两种情况下「一键」会给一大段空白盖标签，而用户没有看见起点的机会。
  if (!dayEntries.some(e => !isPlaceholderEntry(e))) {
    return { ok: false, reason: 'fresh-day', ts, gapMinutes, dayEntries, tail };
  }
  const limit = maxSilentGapMinutes();
  if (gapMinutes > limit) {
    return { ok: false, reason: 'gap-too-large', ts, gapMinutes, limit, dayEntries, tail };
  }
  return { ok: true, mode: 'append', ts, gapMinutes, dayEntries, tail };
}

export function probe(opts = {}) {
  const nowTs = opts.nowTs || nowStr();
  const todayKey = opts.todayKey || todayStr();
  const snapshot = loadSnapshot();
  return Object.assign(probeWith(snapshot.data, nowTs, todayKey), {
    data: snapshot.data,
    raw: snapshot.raw,
    nowTs,
    todayKey
  });
}

/**
 * 追认「上次记录点 → 现在」这段时间。
 * @param {string} tagInput 标签名（必须已存在于 config）
 * @param {{what?: string, nowTs?: string, todayKey?: string}} [opts]
 */
function quickWriteImpl(tagInput, opts = {}) {
  const config = loadConfig();
  // 直接回复里打的 `#标签` 优先于通知携带的那个：键盘已经在手上，用户显式指定了。
  const fromText = resolveTagFromText(opts.what, config);
  const tag = fromText.tag || canonicalTagName(String(tagInput || '').trim(), config);
  if (!tag) return fail('empty-tag');
  // 契约 §7：一键写入只能用已存在的标签，绝不顺手建标签。
  if (!tagExists(tag, config)) return fail('unknown-tag', { tag });
  // 契约 §5：what 为空的记录在数据层就是一条未记录占位条，不是记录。
  const what = fromText.what || tag;

  const p = probe(opts);
  if (!p.ok) {
    return fail(p.reason, { suggestTs: p.ts || '', gapMinutes: p.gapMinutes, limit: p.limit, tag, what });
  }
  const { data, raw, nowTs, todayKey } = p;

  if (p.mode === 'same-minute-correction') {
    p.tail.what = what;
    p.tail.tags = [tag];
    delete p.tail.longConfirm;
    normalizeEntries(data, { todayKey, nowTs, createId: uid });
    const rewrite = saveChecked(data, raw);
    if (!rewrite.ok) return fail(rewrite.reason === 'concurrent' ? 'concurrent' : 'quota');
    lastQuickWrite = { rawBefore: raw, rawAfter: rewrite.raw, ts: p.tail.ts, tag, what };
    return {
      ok: true, mode: 'same-minute-correction', ts: p.tail.ts, tag, what, minutes: 0,
      mirror: safeMirror({ nowTs, todayKey })
    };
  }

  const ts = p.ts;
  let placeholder = openPlaceholderForDate(data.entries, ts.slice(0, 10));
  // v87 守卫：占位条只有在新起点不晚于它时才可以复用（往后挪＝把「确实没记」
  // 静默改写成前一条的标签）。一键路径下 ts 恒等于占位点，走不到这一行；照抄
  // 规则是为了将来允许自定义起点时不会漏掉它。
  if (placeholder && ts > placeholder.ts) placeholder = null;

  const conflict = findTimeConflict(data.entries, ts, placeholder ? placeholder.id : '');
  if (conflict) {
    if (isPlaceholderEntry(conflict)) placeholder = conflict;
    else return fail('conflict', { conflictWhat: String(conflict.what || '').slice(0, 36) });
  }

  if (placeholder) {
    placeholder.ts = ts;
    placeholder.what = what;
    placeholder.tags = [tag];
    delete placeholder.longConfirm;
    delete placeholder.planned;
  } else {
    data.entries.push({ id: uid(), ts, what, tags: [tag] });
  }
  normalizeEntries(data, { todayKey, nowTs, createId: uid });
  const write = saveChecked(data, raw);
  if (!write.ok) return fail(write.reason === 'concurrent' ? 'concurrent' : 'quota');
  lastQuickWrite = { rawBefore: raw, rawAfter: write.raw, ts, tag, what };

  return {
    ok: true, mode: 'append', ts, tag, what, minutes: p.gapMinutes,
    mirror: safeMirror({ nowTs, todayKey })
  };
}

// --- 显示镜像（契约 §6）---------------------------------------------------
// 原生侧不许解析 timelog.v1，所以小组件/磁贴需要的那几个字段由这里算好落到
// 一个独立的键上。它是缓存：不进备份、不参与统计、丢了随时可重算。

function recentTagCounts(entries, todayKey, days = 7) {
  const since = toLocalDate(`${todayKey}T00:00`);
  since.setDate(since.getDate() - (days - 1));
  const counts = new Map();
  loggedEntriesFrom(entries).forEach(e => {
    if (isPlaceholderEntry(e)) return;
    if (toLocalDate(e.ts) < since) return;
    (e.tags || []).forEach(raw => {
      const key = tagKey(raw);
      if (!key) return;
      const seen = counts.get(key);
      counts.set(key, { name: seen ? seen.name : raw, n: (seen ? seen.n : 0) + 1 });
    });
  });
  return [...counts.values()].sort((a, b) => b.n - a.n).map(item => item.name);
}

export function buildMirror(opts = {}) {
  const nowTs = opts.nowTs || nowStr();
  const todayKey = opts.todayKey || todayStr();
  const config = loadConfig();
  const p = probe({ nowTs, todayKey });
  const dayEntries = p.dayEntries || [];
  const lastReal = [...dayEntries].reverse().find(e => !isPlaceholderEntry(e)) || null;
  const showWhat = showLastWhatOnWidget();

  // 建议标签：当前主线（config.mainline[0]）永远第一，其后按最近 7 天使用频次，
  // 再用 config 里的 chips 兜底填满。全部经 canonicalTagName 走权威拼写。
  const ordered = [];
  const push = name => {
    const canonical = canonicalTagName(name, config);
    if (!canonical || !tagExists(canonical, config)) return;
    if (ordered.some(item => tagKey(item) === tagKey(canonical))) return;
    ordered.push(canonical);
  };
  if (config.mainline.length) push(config.mainline[0]);
  recentTagCounts(p.data.entries, todayKey).forEach(push);
  config.chips.forEach(chip => push(chip.name));

  return {
    v: 1,
    computedAt: nowTs,
    nextStartTs: p.ts || '',
    lastTs: lastReal ? lastReal.ts : '',
    lastWhat: showWhat && lastReal ? String(lastReal.what || '') : '',
    lastTag: lastReal && Array.isArray(lastReal.tags) && lastReal.tags.length ? lastReal.tags[0] : '',
    tailIsPlaceholder: Boolean(p.tail && isPlaceholderEntry(p.tail)),
    gapMinutes: Number.isFinite(p.gapMinutes) ? p.gapMinutes : -1,
    suggestTags: ordered.slice(0, 6),
    canQuickWrite: Boolean(p.ok),
    blockedReason: p.ok ? '' : String(p.reason || '')
  };
}

function writeMirrorImpl(opts = {}) {
  const mirror = buildMirror(opts);
  try {
    localStorage.setItem(MIRROR_KEY, JSON.stringify(mirror));
  } catch {
    // 镜像写不下不影响记录本身，静默即可（数据写入早已在上一步完成）。
  }
  return mirror;
}

/**
 * 撤销刚刚那一次一键写入。判据是「数据从那次写入之后一个字节都没变过」——
 * 变过就说明用户在界面里又做了别的事，此时回滚会连带抹掉那些改动。
 */
function undoLastQuickWriteImpl() {
  if (!lastQuickWrite) return fail('nothing-to-undo');
  const current = readRaw();
  if (current !== lastQuickWrite.rawAfter) return fail('changed-since');
  let before;
  try {
    before = JSON.parse(lastQuickWrite.rawBefore);
  } catch {
    return fail('unparsable-before');
  }
  const write = saveChecked(before, current);
  if (!write.ok) return fail(write.reason === 'concurrent' ? 'concurrent' : 'quota');
  const undone = lastQuickWrite;
  lastQuickWrite = null;
  safeMirror();
  return { ok: true, ts: undone.ts, tag: undone.tag, what: undone.what };
}

export function undoAvailable() {
  return Boolean(lastQuickWrite) && readRaw() === lastQuickWrite.rawAfter;
}

// --- 桥的边界 -------------------------------------------------------------
// 任何未捕获异常都必须变成一个**说得出原因**的返回值。抛出去的话
// evaluateJavascript 只会给原生侧一个 null，用户看到的是「应用没能及时响应」——
// 与真的超时无法区分（web 仓 C18 登记的正是「未捕获异常几乎没有探测器」这一类）。
function boundary(fn) {
  return function () {
    try {
      return fn.apply(null, arguments);
    } catch (e) {
      return { ok: false, reason: 'internal', message: String((e && e.message) || e) };
    }
  };
}

// 镜像只是缓存：算错了不该把一次已经落库的写入报成失败。
function safeMirror(opts) {
  try {
    return writeMirrorImpl(opts || {});
  } catch (e) {
    return null;
  }
}

export const quickWrite = boundary(quickWriteImpl);
export const undoLastQuickWrite = boundary(undoLastQuickWriteImpl);
export const writeMirror = boundary(writeMirrorImpl);
