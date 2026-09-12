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

# 商店资产白名单：显式列文件名，不用通配——`docs/store/` 是本仓唯一允许放 PNG 的地方，
# 也因此最容易变成垃圾桶（web 仓 docs/assets 踩过同一个坑）。截图必须是合成 demo 数据。
ALLOWED_STORE_ASSETS = {
    "icon-512.png": (512, 512),
    "feature-1024x500.png": (1024, 500),
    "screen-1-day.png": None,
    "screen-2-week.png": None,
    "screen-3-form.png": None,
}

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
    # versionCode 编码（build.gradle.kts）：major*10_000_000 + minor*100_000 +
    # patch*1_000 + revision。每个字段的字面值必须小于它的位权，否则跨字段进位
    # 会让两个不同版本撞出同一个 versionCode（如 patch=100 撞 minor=1、patch=0），
    # 到 Play 上传才会被拒——在这里提前拦住，出路是扩位权而不是继续 bump。
    parts = (values.get("web.version") or "").split(".")
    try:
        minor, patch = int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        fail(f"version.properties 的 web.version 不是三段式 semver："
             f"{values.get('web.version')!r}——重跑 sync_runtime.py")
    else:
        if minor > 99 or patch > 99:
            fail(f"web 版本 minor={minor}/patch={patch} 超出 versionCode 编码上界（99）"
                 "——先扩 build.gradle.kts 的位权再 bump")
    if int(revision) > 999:
        fail(f"android revision {revision} 超出 versionCode 编码上界（999）——扩位权")
    web_manifest = web_repo / "manifest.webmanifest"
    if web_manifest.exists():
        web_version = str(json.loads(read(web_manifest)).get("version", "")).strip()
        if values.get("web.version") != web_version:
            fail(f"内嵌运行时的版本 {values.get('web.version')!r} 与 web 仓当前版本 "
                 f"{web_version!r} 不一致——重跑 sync_runtime.py")
    source = read(ASSETS_APP / "RUNTIME_SOURCE.txt")
    if source:
        match = re.search(r"web version: (\d+(?:\.\d+)*)", source)
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


# 契约 selector 的安卓侧消费者（web 运行时 DOM）。新消费方出现时登记到这里。
# 提取覆盖的调用形态（单双引号均可）：getElementById(...)、querySelector(All)(...)、
# textContent(...)、waitForSelector(...)，以及 classList.contains(...) 的裸 class 名
# （按「契约里存在含该 class 的 selector」判覆盖）。**新形态出现时必须同步扩展这里**，
# 否则该依赖会静默绕过契约闸——审查发现的 body.app-ready 漏网（waitForSelector
# 形态不认识）即属此类，修复于 2026-09-12。
CONTRACT_SELECTOR_CONSUMERS = (
    ROOT / "app/src/main/kotlin/org/eigentime/timelogger/MainActivity.kt",
    ROOT / "scripts/shell_browser_check.mjs",
)

# class 名字符集（CSS 语法），用于裸 class 与契约 selector 的 class 段互认。
_CLASS_CHARS = "a-zA-Z0-9_-"


def _norm_sel(s: str) -> str:
    """把 selector 截到第一个属性值（=）之前。Kotlin 里拼接出的 JS 字面量在
    =\\" 处被切断，契约侧是完整形态（[data-tag]）；两边都截断后做边界前缀匹配。"""
    return re.split(r"=", s, maxsplit=1)[0].strip()


def _sel_covers(a: str, b: str) -> bool:
    """a 与 b 互相覆盖：相等，或短的一方是长一方的前缀且断在 selector 边界字符上
    （#timeline 与 #timeline-x 不得互认，#form-chips .chip[data-tag 与 …[data-tag] 要认）。"""
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if not long.startswith(short):
        return False
    return len(short) == len(long) or long[len(short)] in " .>[]:#"


def _class_covered(cls: str, selectors: list[str]) -> bool:
    """裸 class 名是否被某个契约 selector 的 class 段覆盖（.cls 且后随非 class 字符）。"""
    return any(re.search(r"\." + re.escape(cls) + rf"(?![{_CLASS_CHARS}])", c) for c in selectors)


def audit_contract_covers_dependencies(web_repo: Path) -> None:
    """对侧契约闸。web 仓的 audit 只保证「契约声明的在 web 侧存在」——删掉一条
    契约条目 web audit 照样绿，壳会在某次运行时同步后静默失效。这里从安卓侧反查：
    ① 桥 import 的每个 (模块, 符号) 必须已登记；② 契约 export 必须真被桥 import；
    ③ 消费方用到的每个 web DOM selector 必须被契约覆盖；④ 契约 selector 必须真有
    消费者。契约文件＝web 仓 native-contract.json。"""
    contract_path = web_repo / "native-contract.json"
    raw = read(contract_path)
    if not raw:
        fail(f"web 仓契约文件缺失：{contract_path}")
        return
    try:
        contract = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"native-contract.json 不是合法 JSON：{exc}")
        return

    bridge = read(BRIDGE)
    if not bridge:
        return  # 桥缺失由 audit_bridge_uses_real_modules 报，不重复
    imported: dict[str, set[str]] = {}
    for symbols, module in re.findall(
        r"import\s*\{([^}]*)\}\s*from\s*'\.\./app/src/([\w.]+)'", bridge, re.S
    ):
        imported.setdefault(f"src/{module}", set()).update(
            s.strip() for s in symbols.split(",") if s.strip()
        )

    declared = contract.get("modules", {})
    for mod in sorted(set(imported) | set(declared)):
        got = imported.get(mod, set())
        want = set(declared.get(mod, {}).get("exports", []))
        for sym in sorted(got - want):
            fail(f"桥从 {mod} import 了 {sym}，native-contract.json 未登记"
                 "——先在 web 仓登记契约，再同步运行时")
        for sym in sorted(want - got):
            fail(f"native-contract.json 声明的 {mod}:{sym} 没有任何桥 import（死条目）"
                 "——从契约删掉，或补上消费方")

    used: list[str] = []
    used_classes: list[str] = []
    for path in CONTRACT_SELECTOR_CONSUMERS:
        text = read(path)
        if not text:
            fail(f"{path.relative_to(ROOT)} 缺失——契约 selector 消费者清单需要它")
            continue
        # 单双引号各写一条模式，且只要求引号闭合、不要求紧跟右括号——waitForSelector
        # 的实参后跟 ', {…}'，Kotlin 拼接的实参后跟 ' + tag…'。也别用
        # (['"])([^'"]+)\1 一条搞定：单引号字符串里合法地含双引号
        # （querySelector('#form-chips .chip[data-tag="' + …）,[^'"] 会把它拦腰截断，
        # 第一版就栽在这里，两个 selector 全部漏提取。
        for pat in (r"getElementById\('([^']+)'", r'getElementById\("([^"]+)"'):
            used += ["#" + m for m in re.findall(pat, text)]
        for pat in (r"(?:querySelector(?:All)?|textContent|waitForSelector)\('([^']+)'",
                    r'(?:querySelector(?:All)?|textContent|waitForSelector)\("([^"]+)"'):
            used += re.findall(pat, text)
        for pat in (r"classList\.contains\('([^']+)'", r'classList\.contains\("([^"]+)"'):
            used_classes += re.findall(pat, text)
    selectors = [str(s) for s in contract.get("selectors", [])]
    for u in sorted(set(used)):
        if not any(_sel_covers(_norm_sel(u), _norm_sel(c)) for c in selectors):
            fail(f"消费方使用了未登记的 web selector {u!r}——先在 web 仓登记契约")
    for cls in sorted(set(used_classes)):
        if not _class_covered(cls, selectors):
            fail(f"消费方等待的 body class {cls!r} 未被任何契约 selector 的 class 段覆盖"
                 "——先在 web 仓登记契约")
    for c in selectors:
        if not any(_sel_covers(_norm_sel(c), _norm_sel(u)) for u in used):
            fail(f"契约 selector {c!r} 在安卓侧没有任何消费者（死条目）——从契约删掉，或补上消费方")


def audit_release_signing_fail_closed() -> None:
    """v1.0.0 计划项：release 构建不得在缺 keystore.properties 时静默回退 debug
    签名——那会产出一次「成功」却永远无法上架、且与已分发包签名不同的产物。
    守卫在 build.gradle.kts 的任务图就绪检查里；「拒绝静默回退」是结构锚点，
    被挪走即守卫被拆。"""
    text = read(ROOT / "app" / "build.gradle.kts")
    if "拒绝静默回退" not in text:
        fail("build.gradle.kts 缺 fail-closed 签名守卫（「拒绝静默回退」锚点不在）——"
             "缺 keystore.properties 时 Release 任务必须失败，而不是产出 debug 签名产物")
    if 'whenReady' not in text or '"packageRelease"' not in text or 'validateSigningRelease' not in text:
        fail("build.gradle.kts 的签名守卫未挂在任务图就绪、或触发面未收窄到签名产物任务"
             "（packageRelease/packageReleaseBundle/validateSigningRelease）——"
             "按名字含 Release 拦会误伤 testReleaseUnitTest，日常自测在无密钥机器上跑不了")


def png_size(path: Path) -> tuple[int, int]:
    import struct
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", head[16:24])


def audit_store_assets() -> None:
    store = ROOT / "docs/store"
    if not store.is_dir():
        return
    for path in sorted(store.glob("*.png")):
        if path.name not in ALLOWED_STORE_ASSETS:
            fail(f"docs/store/{path.name} 未登记（改 ALLOWED_STORE_ASSETS；且必须是合成 demo 数据）")
            continue
        expected = ALLOWED_STORE_ASSETS[path.name]
        if expected is None:
            continue
        try:
            actual = png_size(path)
        except Exception as exc:
            fail(f"docs/store/{path.name} 读不出尺寸：{exc}")
            continue
        if actual != expected:
            fail(f"docs/store/{path.name} 尺寸应为 {expected}，实际 {actual}（Play 会拒绝）")


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
    audit_contract_covers_dependencies(Path(args.web_repo).resolve())
    audit_release_signing_fail_closed()
    audit_strings_parity()
    audit_store_assets()
    if errors:
        print("android project audit FAILED:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1
    print("android project audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
