#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""把 web 运行时同步进 app/src/main/assets/app/（确定性复制，不是构建）。

单一真源是 web 仓（默认 ../time-logger）的 `sw.js` FILES 数组——那份清单本来
就是「运行时资产」的权威定义，这里直接解析它，不另维护一份拷贝清单
（与 web 仓 scripts/build_site.py 同一手法）。

- 逐文件**逐字节**复制，不压缩、不转换、不改写；
- 唯一的例外是 `sw.js`：**故意不复制**。APK 里的运行时是本地资产，Service Worker
  没有任何用处，而它 cache-first 的缓存会在 APK 升级后继续吐旧代码（升了包却
  还是旧界面）。文件不存在 + 资产加载器对 sw.js 返回 404，让注册必然失败；
  JS 侧另有 navigator.serviceWorker 桩，两道都堵上。
- 写 app/version.properties（web 版本号 + 本地 revision + 源 commit），供
  Gradle 派生 versionCode / versionName；
- 写 assets/app/RUNTIME_SOURCE.txt 记录来源，便于日后取证。

用法：
    python3 scripts/sync_runtime.py                 # 默认从 ../time-logger 同步
    python3 scripts/sync_runtime.py --from /path/to/time-logger
    python3 scripts/sync_runtime.py --release       # 发版预检模式（见下）

--release（发版仪式第一步，2026-09-12 落地 v1.0.0 计划项）：先做完整预检——
web 仓工作区 clean、commit 可解析、版本三段式、native-contract.json 结构有效——
**全部通过才替换资产**。旧顺序是先复制文件后查 git 来源，失败时已经改了工作区；
且 git 调用异常时把 dirty 标记一起清空，把「查不出来」写成了「干净」。任何模式的
git 来源都先于改动收集，查不出来一律按 dirty 对待。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "src" / "main" / "assets" / "app"
# 见模块 docstring：Service Worker 在 APK 里只会造成「升了包还是旧界面」。
SKIP = {"./sw.js"}


def parse_files(sw_js: str) -> list[str]:
    match = re.search(r"const FILES = \[(.*?)\];", sw_js, re.S)
    if not match:
        raise SystemExit("无法在 sw.js 里定位 FILES 数组——web 仓结构变了，先看一眼再改这里")
    entries = re.findall(r"'([^']+)'", match.group(1))
    if not entries:
        raise SystemExit("FILES 数组解析结果为空")
    return entries


def gather_git_source(src: Path) -> tuple[str, str, bool]:
    """返回 (commit, dirty_text, git_ok)。异常不算 clean：查不出来按 dirty 对待。"""
    try:
        commit = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(src), "status", "--porcelain"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return commit, dirty, True
    except Exception:
        return "unknown", "git status 不可用", False


def contract_problems(src: Path) -> list[str]:
    """native-contract.json 的结构有效性（深度校验在两仓各自的 audit）。"""
    path = src / "native-contract.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["web 仓缺 native-contract.json（安卓壳依赖它）"]
    except json.JSONDecodeError as exc:
        return [f"native-contract.json 不是合法 JSON：{exc}"]
    problems: list[str] = []
    if contract.get("version") != 1:
        problems.append("契约 version 必须是 1")
    modules = contract.get("modules") or {}
    if not modules:
        problems.append("契约 modules 为空")
    for mod, spec in modules.items():
        if not (src / mod).is_file():
            problems.append(f"契约声明的模块不存在：{mod}")
        elif not (spec or {}).get("exports"):
            problems.append(f"契约 {mod} 的 exports 为空")
    if not contract.get("selectors"):
        problems.append("契约 selectors 为空")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default=str(ROOT.parent / "time-logger"),
                    help="web 仓路径（默认 ../time-logger）")
    ap.add_argument("--release", action="store_true",
                    help="发版预检模式：clean/commit/版本/契约全部通过才替换资产")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    if not (src / "sw.js").exists():
        raise SystemExit(f"{src} 看起来不是 time-logger web 仓（缺 sw.js）")

    commit, dirty, git_ok = gather_git_source(src)
    files = parse_files((src / "sw.js").read_text(encoding="utf-8"))
    manifest = json.loads((src / "manifest.webmanifest").read_text(encoding="utf-8"))
    web_version = str(manifest.get("version", "")).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", web_version):
        raise SystemExit(f"manifest version 不是三段式 semver：{web_version!r}")

    if args.release:
        problems: list[str] = []
        if not git_ok:
            problems.append(f"无法从 web 仓取得 git 来源：{dirty}")
        else:
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                problems.append(f"commit 不可解析：{commit!r}")
            if dirty:
                problems.append("web 仓工作区不干净——发版产物必须对应已提交的版本")
        problems.extend(contract_problems(src))
        if problems:
            for p in problems:
                print(f"--release 预检失败：{p}", file=sys.stderr)
            raise SystemExit("预检未通过，未改动任何资产")

    if ASSETS.exists():
        shutil.rmtree(ASSETS)
    ASSETS.mkdir(parents=True)

    copied = []
    for rel in files:
        if rel in SKIP or rel == "./":
            continue
        source = (src / rel.lstrip("./")).resolve()
        if not source.is_file():
            raise SystemExit(f"FILES 里列了但文件不存在：{rel}")
        dest = ASSETS / rel.lstrip("./")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        copied.append(rel.lstrip("./"))

    treated_dirty = bool(dirty) or not git_ok
    (ASSETS / "RUNTIME_SOURCE.txt").write_text(
        "source: wowayou/time-logger\n"
        f"commit: {commit}{' (dirty)' if treated_dirty else ''}\n"
        f"web version: {web_version}\n"
        f"files: {len(copied)}\n"
        "note: sw.js is intentionally absent (see scripts/sync_runtime.py)\n",
        encoding="utf-8")

    revision = (ROOT / "app" / "android_revision.txt").read_text(encoding="utf-8").strip() or "1"
    (ROOT / "app" / "version.properties").write_text(
        f"web.version={web_version}\n"
        f"android.revision={revision}\n"
        f"web.commit={commit}\n",
        encoding="utf-8")

    print(f"同步 {len(copied)} 个运行时文件 → {ASSETS.relative_to(ROOT)}")
    print(f"web 版本 {web_version} · android revision {revision} · commit {commit[:8]}"
          + (" · 源仓有未提交改动" if treated_dirty else ""))
    if treated_dirty:
        print("警告：web 仓来源不干净或不可解析，内嵌的运行时不对应任何已发布提交",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
