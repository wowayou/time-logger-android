#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""红灯检查：逐条撤掉守卫，确认对应的用例**确实会变红**（web 仓 P35 纪律）。

一条用例不会因为守卫消失而变红，就说明它其实没在测那条守卫。这里把「撤掉→跑→
还原」自动化，并且顺带检查**精度**：撤掉某条守卫时只有它对应的断言该红，别的
不许连带变红。

用法：python3 scripts/redlight.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "app/src/main/assets/bridge/quick_write.js"
SHIM = ROOT / "app/src/main/assets/bridge/store_shim.js"

# (说明, 目标文件, 原文, 改成, 期望变红的断言前缀)
# 断言前缀 "T\d+" 走 quick_write_smoke；shim 的断言没有编号，用整体红/绿判定。
CASES = [
    (
        "撤掉「今天还没有记录」守卫",
        BRIDGE,
        """  if (!dayEntries.some(e => !isPlaceholderEntry(e))) {
    return { ok: false, reason: 'fresh-day', ts, gapMinutes, dayEntries, tail };
  }""",
        "",
        ["T2"],
    ),
    (
        "撤掉空白上限守卫",
        BRIDGE,
        """  const limit = maxSilentGapMinutes();
  if (gapMinutes > limit) {
    return { ok: false, reason: 'gap-too-large', ts, gapMinutes, limit, dayEntries, tail };
  }""",
        "",
        ["T3", "T13"],
    ),
    (
        "撤掉「一键不新建标签」守卫",
        BRIDGE,
        "  if (!tagExists(tag, config)) return fail('unknown-tag', { tag });",
        "",
        ["T4"],
    ),
    (
        "让 what 允许为空（撤掉契约 §5）",
        BRIDGE,
        "  const what = fromText.what || tag;",
        "  const what = fromText.what;",
        # what 为空＝写出来的就是一条占位条，凡是写入的用例都该红（T16 是「只打
        # #标签、没有正文」那条，退化后 what 同样为空）。守卫处处承重，不是精度不够。
        ["T1", "T5", "T11", "T12", "T16"],
    ),
    (
        "撤掉同分钟修正分支",
        BRIDGE,
        """  if (tail && !isPlaceholderEntry(tail) && !tail.planned && tail.ts === nowTs) {
    return { ok: true, mode: 'same-minute-correction', ts: nowTs, gapMinutes: 0, tail, dayEntries };
  }""",
        "",
        ["T5"],
    ),
    (
        "撤掉「23:59 无空位」守卫（放它越午夜）",
        BRIDGE,
        "  if (!ts) return { ok: false, reason: 'no-slot', dayEntries, tail };",
        "",
        ["T6"],
    ),
    (
        "把 CAS 换成无条件写入",
        BRIDGE,
        """  const write = saveChecked(data, raw);
  if (!write.ok) return fail(write.reason === 'concurrent' ? 'concurrent' : 'quota');
  lastQuickWrite = { rawBefore: raw, rawAfter: write.raw, ts, tag, what };""",
        """  const write = { ok: true, raw: JSON.stringify(data) };
  localStorage.setItem('timelog.v1', write.raw);
  lastQuickWrite = { rawBefore: raw, rawAfter: write.raw, ts, tag, what };""",
        ["T7"],
    ),
    (
        "撤掉撤销的「数据已变」守卫",
        BRIDGE,
        "  if (current !== lastQuickWrite.rawAfter) return fail('changed-since');",
        "",
        ["T9"],
    ),
    (
        "让镜像无条件带上记录正文",
        BRIDGE,
        "  const showWhat = showLastWhatOnWidget();",
        "  const showWhat = true;",
        ["T12"],
    ),
    (
        "让 #标签 也能创建不存在的标签",
        BRIDGE,
        "    if (candidate && tagExists(candidate, config)) {",
        "    if (candidate) {",
        ["T15"],
    ),
    (
        "文本里的 #标签 不再优先于通知携带的标签",
        BRIDGE,
        "  const tag = fromText.tag || canonicalTagName(String(tagInput || '').trim(), config);",
        "  const tag = canonicalTagName(String(tagInput || '').trim(), config);",
        # 撤掉优先级后，「只打 #睡觉」那条（T16）也会红：标签退回通知携带的，
        # what 随之退回那个标签名。两条都该红，不是精度不够。
        ["T14", "T16"],
    ),
    (
        "撤掉 localStorage 的替换（桥形同不存在）",
        SHIM,
        """    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: function () { return shim; }
    });""",
        "",
        ["SHIM"],
    ),
    (
        "让配额失败不抛异常（storage.js 会以为写成功了）",
        SHIM,
        "      if (err) throw quotaError(String(err));",
        "",
        ["SHIM"],
    ),
    (
        "把 serviceWorker 桩换成 undefined（app.js 会对它取 addEventListener）",
        SHIM,
        "      get: function () { return swStub; }",
        "      get: function () { return undefined; }",
        ["SHIM"],
    ),
]


def run_smoke(script: str = "scripts/quick_write_smoke.py") -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, script],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return result.returncode, result.stdout + result.stderr


def failing_ids(output: str) -> set[str]:
    return set(re.findall(r"^FAIL (T\d+)", output, re.M))


def main() -> int:
    originals = {path: path.read_text(encoding="utf-8") for path in {BRIDGE, SHIM}}
    for script in ("scripts/quick_write_smoke.py", "scripts/shim_smoke.py"):
        code, out = run_smoke(script)
        if code != 0:
            print(f"基线就是红的（{script}），先修好再跑红灯：\n" + out, file=sys.stderr)
            return 2
        summary = next((l for l in out.splitlines() if l.startswith(("OK ", "FAILED "))), out.strip())
        print(f"基线通过（{script}）：" + summary)

    problems = []
    try:
        for label, path, old, new, expect in CASES:
            original = originals[path]
            if old not in original:
                problems.append(f"{label}：找不到要撤掉的那段代码（{path.name} 结构变了）")
                continue
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
            shim_case = expect == ["SHIM"]
            script = "scripts/shim_smoke.py" if shim_case else "scripts/quick_write_smoke.py"
            code, out = run_smoke(script)
            got = failing_ids(out)
            want = set() if shim_case else set(expect)
            if code == 0:
                problems.append(f"{label}：撤掉守卫后用例照样全绿——那条用例没在测它")
            elif shim_case:
                print(f"红灯 OK · {label} → shim_smoke 变红")
            elif not want <= got:
                problems.append(f"{label}：期望 {sorted(want)} 变红，实际 {sorted(got)}")
            elif got - want:
                problems.append(f"{label}：连带弄红了 {sorted(got - want)}（精度不够）")
            else:
                print(f"红灯 OK · {label} → {sorted(got)}")
            path.write_text(original, encoding="utf-8")
    finally:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")

    for script in ("scripts/quick_write_smoke.py", "scripts/shim_smoke.py"):
        after_code, after_out = run_smoke(script)
        if after_code != 0:
            problems.append(f"还原后基线没有恢复绿灯（{script}）：" + after_out)

    if problems:
        print("\n以下红灯不成立：", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1
    print(f"\n{len(CASES)} 处红灯全部点亮，且各自只红对应用例。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
