#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""结构闸：把 CLAUDE.md 里的红线变成可执行判据。

存在的理由：版本锚点、隐私边界和「原生不实现业务逻辑」这三件事改错了都不会让任何
测试变红——它们不是行为，是结构。这里逐条查。

    python3 scripts/project_audit.py [--web-repo ../time-logger]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KOTLIN = sorted((ROOT / "app/src/main/kotlin").rglob("*.kt"))
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"
BRIDGE = ROOT / "app/src/main/assets/bridge/quick_write.js"
SHIM = ROOT / "app/src/main/assets/bridge/store_shim.js"
ASSETS_APP = ROOT / "app/src/main/assets/app"

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def audit_version_anchors(web_repo: Path) -> None:
    revision_file = ROOT / "app/android_revision.txt"
    revision = read(revision_file).strip()
    if not revision.isdigit() or int(revision) < 1:
        fail(f"app/android_revision.txt 必须是 >=1 的整数，实际 {revision!r}")
    props = read(ROOT / "app/version.properties")
    if not props:
        return  # 还没同步过运行时；构建时 assertRuntimeSynced 会拦
    values = dict(
        line.split("=", 1) for line in props.splitlines() if "=" in line
    )
    if values.get("android.revision") != revision:
        fail("version.properties 的 android.revision 与 app/android_revision.txt 不一致"
             f"（{values.get('android.revision')!r} vs {revision!r}）——重跑 sync_runtime.py")
    web_manifest = web_repo / "manifest.webmanifest"
    if web_manifest.exists():
        web_version = str(json.loads(read(web_manifest)).get("version", "")).strip()
        if values.get("web.version") != web_version:
            fail(f"内嵌运行时的版本 {values.get('web.version')!r} 与 web 仓当前版本 "
                 f"{web_version!r} 不一致——重跑 sync_runtime.py")
    source = read(ASSETS_APP / "RUNTIME_SOURCE.txt")
    if source:
        match = re.search(r"web version: (\d+)", source)
        if match and match.group(1) != values.get("web.version"):
            fail("assets/app/RUNTIME_SOURCE.txt 与 version.properties 的 web 版本不一致")


def audit_privacy_and_runtime() -> None:
    manifest = read(MANIFEST)
    if not manifest:
        fail("AndroidManifest.xml 缺失")
        return
    # 红线③：不声明 INTERNET。权限不在，代码就无从联网。
    if "android.permission.INTERNET" in manifest:
        fail("清单里出现了 INTERNET 权限（红线③）")
    for needed in ('android:allowBackup="false"', "data_extraction_rules"):
        if needed not in manifest:
            fail(f"清单缺少 {needed}（记录数据不得进云备份/换机迁移）")
    # 红线①：APK 里不得有 sw.js
    if (ASSETS_APP / "sw.js").exists():
        fail("assets/app/sw.js 存在——同步脚本必须跳过它（否则升级后仍吐旧代码）")
    if ASSETS_APP.exists() and not (ASSETS_APP / "index.html").exists():
        fail("assets/app/ 存在却没有 index.html——同步产物不完整")


def audit_native_has_no_business_logic() -> None:
    """红线②/④：原生只做存储与呈现；时间线数据只能由 web 模块写。"""
    for path in KOTLIN:
        text = read(path)
        for pattern, why in (
            (r"setItem\(\s*Keys\.DATA", "原生不得写 timelog.v1"),
            (r"setItem\(\s*Keys\.CONFIG", "原生不得写 timelog.config"),
            (r'setItem\(\s*"timelog\.(v1|config)"', "原生不得写时间线数据或标签配置"),
        ):
            if re.search(pattern, text):
                fail(f"{path.relative_to(ROOT)}：{why}（红线④）")
        # 显示镜像之外不许解析业务数据结构
        if path.name not in ("Mirror.kt",) and "JSONObject(" in text and "Keys.MIRROR" in text:
            fail(f"{path.relative_to(ROOT)}：只有 Mirror.kt 可以解析显示镜像")
    # 诊断日志不得带用户数据
    for path in KOTLIN:
        for line_no, line in enumerate(read(path).splitlines(), 1):
            # 变量可能写成 $tag，也可能是 ${out.tag} —— 第一版只认前者，
            # 红灯检查里「日志带标签」那条因此没点亮（判据本身漏了 . 后面的形态）。
            if "Diag.log(" in line and re.search(r"\$\{?[\w.]*\b(tag|what|conflictWhat|lastWhat)\b", line):
                fail(f"{path.relative_to(ROOT)}:{line_no} 诊断日志里出现了标签/正文（隐私）")


def audit_bridge_uses_real_modules() -> None:
    bridge = read(BRIDGE)
    if not bridge:
        fail("assets/bridge/quick_write.js 缺失")
        return
    for symbol in ("defaultFormTimestamp", "normalizeEntries", "saveChecked",
                   "openPlaceholderForDate", "findTimeConflict", "loadSnapshot"):
        if not re.search(rf"^\s*{symbol},?$", bridge, re.M):
            fail(f"桥没有从真实模块 import {symbol}（红线②：不得复制业务逻辑）")
        if re.search(rf"function {symbol}\b", bridge):
            fail(f"桥里自己实现了 {symbol}——那是 web 仓的逻辑，只能 import")
    if "../app/src/" not in bridge:
        fail("桥必须从 ../app/src/ 导入运行时模块")
    # 红线⑤：两条守卫必须在
    for reason in ("fresh-day", "gap-too-large", "no-slot", "unknown-tag"):
        if f"'{reason}'" not in bridge:
            fail(f"桥里找不到守卫/原因码 {reason}（红线⑤）")
    shim = read(SHIM)
    if "defineProperty(window, 'localStorage'" not in shim:
        fail("store_shim.js 必须替换 window.localStorage")
    if "serviceWorker" not in shim:
        fail("store_shim.js 必须给 navigator.serviceWorker 上桩（红线①第三道）")


def audit_strings_parity() -> None:
    default = ROOT / "app/src/main/res/values/strings.xml"
    zh = ROOT / "app/src/main/res/values-zh/strings.xml"
    keys = {}
    for label, path in (("default(en)", default), ("zh", zh)):
        text = read(path)
        if not text:
            fail(f"{path.relative_to(ROOT)} 缺失")
            return
        keys[label] = set(re.findall(r'<string name="([^"]+)"', text))
    missing_zh = keys["default(en)"] - keys["zh"]
    missing_en = keys["zh"] - keys["default(en)"]
    if missing_zh:
        fail(f"values-zh 缺少：{sorted(missing_zh)}")
    if missing_en:
        fail(f"默认(英文) 缺少：{sorted(missing_en)}")
    # 每个 reason 都要有话可说：QuickWrite.message 用到的 guard_* 必须存在
    used = set()
    for path in KOTLIN:
        used |= set(re.findall(r"R\.string\.(\w+)", read(path)))
    unknown = {k for k in used if k not in keys["default(en)"]}
    if unknown:
        fail(f"代码引用了不存在的字符串：{sorted(unknown)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web-repo", default=str(ROOT.parent / "time-logger"))
    args = ap.parse_args()
    audit_version_anchors(Path(args.web_repo).resolve())
    audit_privacy_and_runtime()
    audit_native_has_no_business_logic()
    audit_bridge_uses_real_modules()
    audit_strings_parity()
    if errors:
        print("android project audit FAILED:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    print("android project audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
