#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""浏览器级验收：真实 Chromium + APK 的资产布局 + 真实桥。

回答「这套装配跑不跑得起来」：ES modules 能否从 assets 加载、桥会不会挡住启动、
原生写入后界面会不会刷新、sw.js 有没有被注册。真机验收仍不能免——小组件、磁贴、
通知、系统栏内边距只有设备上才算数。

Playwright 复用 web 仓（同机、开发期）已经装好的那一份，本仓不引入 npm 依赖：
    python3 scripts/shell_browser_check.py [--web-repo ../time-logger]
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app/src/main/assets"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        # 与 WebViewAssetLoader 一致：本地资产不缓存
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web-repo", default=str(ROOT.parent / "time-logger"))
    args = ap.parse_args()
    node_modules = Path(args.web_repo).resolve() / "node_modules"
    if not (node_modules / "playwright").exists():
        print(f"找不到 Playwright：{node_modules}/playwright（web 仓里跑过 npm i 吗？）", file=sys.stderr)
        return 2
    if not (ASSETS / "app/index.html").exists():
        print("内嵌运行时不在位：先跑 python3 scripts/sync_runtime.py", file=sys.stderr)
        return 2

    handler = functools.partial(QuietHandler, directory=str(ASSETS))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        env = dict(os.environ)
        env["SHELL_CHECK_PLAYWRIGHT"] = str(node_modules / "playwright" / "index.js")
        env["SHELL_CHECK_BASE"] = f"http://127.0.0.1:{port}"
        env["SHELL_CHECK_ASSETS"] = str(ASSETS)
        result = subprocess.run(
            ["node", str(ROOT / "scripts/shell_browser_check.mjs")],
            cwd=ROOT, env=env, check=False,
        )
        httpd.shutdown()
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
