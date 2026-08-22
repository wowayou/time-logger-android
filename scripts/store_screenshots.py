#!/usr/bin/env python3
# 时间尺 / Eigentime Android 壳
# SPDX-License-Identifier: AGPL-3.0-or-later
"""生成商店截图（合成 demo 数据，隐私红线：不得用真实记录）。

一条命令：播种 demo 数据 → 逐屏截图 → 裁掉状态栏 → 存到 docs/store/。
截图前请**关掉录屏**——Samsung 的录屏工具栏会浮在画面上。脚本会检测并拒绝输出。

    python3 scripts/store_screenshots.py --serial <ip:port>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADB = Path.home() / "android-toolchain/sdk/platform-tools/adb"
PKG = "org.eigentime.timelogger.debug"
OUT = ROOT / "docs/store"

# 合成 demo：覆盖**本周多天**而不只是今天——只有今天有数据时，周视图里 5 天都写着
# 「无记录 0%」，商店图看起来像坏了。过去几天各留一点空白（真实的一天本来也有空白）。
DAY_PATTERNS = [
    [("07:10", "起床洗漱", "洗漱"), ("07:40", "早饭", "吃饭"), ("08:20", "通勤", "通勤"),
     ("09:00", "写时间尺的安卓壳", "当前主线"), ("11:30", "刷手机", "刷手机"),
     ("12:00", "午饭", "吃饭"), ("12:40", "午休", "睡觉"),
     ("13:30", "写时间尺的安卓壳", "当前主线"), ("16:20", "散步", "运动健康"),
     ("17:00", "读文档", "当前主线"), ("22:40", "睡觉", "睡觉")],
    [("07:30", "洗漱早饭", "洗漱"), ("08:10", "通勤", "通勤"),
     ("08:50", "重构存储层", "当前主线"), ("12:10", "午饭", "吃饭"),
     ("13:00", "写真机验收脚本", "当前主线"), ("15:40", "刷手机", "刷手机"),
     ("16:10", "写真机验收脚本", "当前主线"), ("18:30", "做饭吃饭", "吃饭"),
     ("19:30", "读文档", "当前主线"), ("23:00", "睡觉", "睡觉")],
    [("08:00", "洗漱", "洗漱"), ("08:30", "早饭", "吃饭"),
     ("09:10", "查一个跨标签页的写入 bug", "当前主线"), ("12:00", "午饭", "吃饭"),
     ("12:50", "午休", "睡觉"), ("13:40", "补测试", "当前主线"),
     ("17:30", "运动", "运动健康"), ("18:40", "晚饭", "吃饭"),
     ("22:30", "睡觉", "睡觉")],
    [("07:50", "洗漱早饭", "洗漱"), ("08:40", "通勤", "通勤"),
     ("09:20", "改小组件排版", "当前主线"), ("11:50", "午饭", "吃饭"),
     ("13:00", "改小组件排版", "当前主线"), ("15:00", "发呆", "刷手机"),
     ("15:40", "写文档", "当前主线"), ("19:00", "晚饭", "吃饭"),
     ("22:50", "睡觉", "睡觉")],
]

CONFIG = {
    "mainline": ["当前主线"],
    "chips": [
        {"name": "睡觉", "bucket": "maintain", "longOk": True},
        {"name": "吃饭", "bucket": "maintain", "longOk": False},
        {"name": "洗漱", "bucket": "maintain", "longOk": False},
        {"name": "通勤", "bucket": "maintain", "longOk": False},
        {"name": "运动健康", "bucket": "maintain", "longOk": False},
        {"name": "刷手机", "bucket": "leak", "longOk": False},
    ],
}


def encode_key(key: str) -> str:
    return "".join(
        c if ((c.isalnum() and c.isascii()) or c in "._-")
        else "".join(f"%{b:02X}" for b in c.encode())
        for c in key
    )


class Phone:
    def __init__(self, serial: str):
        self.base = [str(ADB), "-s", serial]

    def sh(self, *args: str) -> str:
        return subprocess.run(self.base + ["shell"] + list(args),
                              capture_output=True, text=True, check=False).stdout

    def put(self, key: str, value: str) -> None:
        fd, local = tempfile.mkstemp()
        os.write(fd, value.encode()); os.close(fd)
        try:
            subprocess.run(self.base + ["push", local, "/data/local/tmp/shot.val"],
                           capture_output=True)
            self.sh("run-as", PKG, "mkdir", "-p", "files/store")
            self.sh("run-as", PKG, "cp", "/data/local/tmp/shot.val",
                    f"files/store/{encode_key(key)}.val")
        finally:
            os.unlink(local)

    def shot(self, path: Path) -> None:
        out = subprocess.run(self.base + ["exec-out", "screencap", "-p"],
                             capture_output=True, check=False)
        path.write_bytes(out.stdout)


def mostly_black(path: Path) -> bool:
    """息屏/转场时 screencap 会给出（近）全黑图。宁可失败，也不能把黑图当截图交出去。"""
    from PIL import Image
    im = Image.open(path).convert("L")
    hist = im.histogram()
    return sum(hist[:12]) / (im.size[0] * im.size[1]) > 0.98


def recorder_overlay(path: Path) -> bool:
    """Samsung 录屏工具栏是顶部居中的浅色胶囊。检测它，避免把它发到商店里。"""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, _ = im.size
    band = [im.getpixel((x, 165))[0] for x in range(int(w * 0.45), int(w * 0.75), 6)]
    return sum(1 for v in band if v > 120) > len(band) * 0.6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--allow-overlay", action="store_true", help="明知有录屏浮层也照样输出")
    args = ap.parse_args()
    from PIL import Image

    p = Phone(args.serial)
    day = time.strftime("%Y-%m-%d")
    entries = []
    for back, pattern in enumerate(DAY_PATTERNS):
        d = time.strftime("%Y-%m-%d", time.localtime(time.time() - back * 86400))
        for i, (t, w, g) in enumerate(pattern):
            if back == 0 and t >= "18:00":
                continue    # 今天只记到下午，尾部留一段未记录（真实形态）
            entries.append({"id": f"d{back}_{i}", "ts": f"{d}T{t}", "what": w, "tags": [g]})
    entries.append({"id": "tail", "ts": f"{day}T18:10", "what": "", "tags": []})
    entries.sort(key=lambda e: e["ts"])

    p.sh("svc", "power", "stayon", "true")   # 只在充电时有效，所以下面还要显式唤醒
    p.sh("input", "keyevent", "224")         # KEYCODE_WAKEUP
    p.sh("input", "keyevent", "82")          # 无密码锁屏时顺手解掉
    time.sleep(2)
    p.sh("am", "force-stop", PKG)
    p.sh("am", "start", "-n", f"{PKG}/org.eigentime.timelogger.MainActivity")
    time.sleep(6)
    p.put("timelog.v1", json.dumps({"version": 1, "entries": entries}, ensure_ascii=False))
    p.put("timelog.config", json.dumps(CONFIG, ensure_ascii=False))
    p.put("timelog.selectedDate", day)
    p.put("timelog.theme", "dark")
    # 首启的说明页与权限弹窗都会挡住画面：前者靠这个键跳过，后者预先授予
    p.put("timelog.helpSeen.v16", "1")
    p.sh("pm", "grant", PKG, "android.permission.POST_NOTIFICATIONS")
    p.sh("am", "force-stop", PKG)
    p.sh("am", "start", "-n", f"{PKG}/org.eigentime.timelogger.MainActivity")
    time.sleep(9)

    OUT.mkdir(parents=True, exist_ok=True)
    plan = [("screen-1-day.png", None), ("screen-2-week.png", (415, 329)),
            ("screen-3-form.png", (866, 2211))]
    raw = Path(tempfile.mkdtemp())
    made = []
    for name, tap in plan:
        if tap:
            if name.endswith("form.png"):
                p.sh("input", "tap", "170", "329")   # 先回天视图
                time.sleep(3)
            p.sh("input", "tap", str(tap[0]), str(tap[1]))
            time.sleep(4)
        shot = raw / name
        p.shot(shot)
        if mostly_black(shot):
            # 再唤醒一次重拍；仍然全黑就是锁屏挡着，只能让人解锁
            p.sh("input", "keyevent", "224")
            time.sleep(2)
            p.shot(shot)
        if mostly_black(shot):
            print(f"截到的是黑屏（{name}）：屏幕可能锁着。解锁手机后重跑。", file=sys.stderr)
            p.sh("svc", "power", "stayon", "false")
            return 1
        if recorder_overlay(shot) and not args.allow_overlay:
            print(f"检测到录屏工具栏浮层（{name}）——先关掉录屏再跑，或加 --allow-overlay",
                  file=sys.stderr)
            p.sh("svc", "power", "stayon", "false")
            return 1
        im = Image.open(shot).convert("RGB")
        # 裁掉状态栏（顶部 96px）与右缘 16px：右缘那条浅色竖带是 One UI 的 Edge 面板手柄，
        # 系统浮层，不该出现在商店图里（它不是我们画的，见 docs/device-acceptance.md）。
        im.crop((0, 96, im.size[0] - 16, im.size[1])).save(OUT / name)
        made.append(name)
    p.sh("input", "keyevent", "4")
    p.sh("svc", "power", "stayon", "false")
    print("已生成：" + ", ".join(made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
