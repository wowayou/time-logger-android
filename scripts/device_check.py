#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""真机 / 模拟器上的自动验收：把一键写入这条链路端到端跑一遍。

不需要 UI 自动化框架——debug 包可 `run-as`，所以能直接读回应用私有目录里的存储，
判据是**数据到底有没有落库**，而不是截图像不像。

    python3 scripts/device_check.py                 # 用当前唯一的 adb 设备
    python3 scripts/device_check.py --serial emulator-5554

前置：已 `./gradlew assembleDebug`，设备已连上（`adb devices` 能看到）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADB = Path.home() / "android-toolchain/sdk/platform-tools/adb"
PKG = "org.eigentime.timelogger.debug"
APK = ROOT / "app/build/outputs/apk/debug/app-debug.apk"

failures: list[str] = []
checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not ok:
        failures.append(f"{name}{' — ' + detail if detail else ''}")
        print(f"FAIL {name}" + (f" — {detail}" if detail else ""))
    else:
        print(f"ok   {name}")


class Device:
    def __init__(self, serial: str | None):
        self.base = [str(ADB)] + (["-s", serial] if serial else [])

    def sh(self, *args: str, timeout: int = 60) -> str:
        out = subprocess.run(self.base + ["shell"] + list(args),
                             capture_output=True, text=True, timeout=timeout, check=False)
        return (out.stdout or "") + (out.stderr or "")

    def run(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(self.base + list(args), capture_output=True, text=True,
                              timeout=timeout, check=False)

    def posted_notifications(self) -> int:
        """已发布通知的条数。判据取自设备实测的 dumpsys 格式：
        `NotificationRecord(0x…: pkg=<包名> user=… id=… …)`。
        不能用「包名出现在 dumpsys 里」——它也会出现在频道定义、权限记录和日志行里。"""
        out = self.sh("dumpsys", "notification", "--noredact")
        return len([1 for line in out.splitlines()
                    if "NotificationRecord(" in line and f"pkg={PKG} " in line])

    def notification_record(self) -> str:
        """取出本应用那条通知记录的完整片段（含 actions 明细），供逐项断言。"""
        out = self.sh("dumpsys", "notification", "--noredact").splitlines()
        start = next((i for i, line in enumerate(out)
                      if "NotificationRecord(" in line and f"pkg={PKG} " in line), None)
        if start is None:
            return ""
        end = start + 1
        while end < len(out) and "NotificationRecord(" not in out[end]:
            end += 1
        return "\n".join(out[start:end])

    def read_store(self, key: str) -> str | None:
        out = self.sh("run-as", PKG, "cat", f"files/store/{encode_key(key)}.val")
        if "No such file" in out or "Permission denied" in out or not out.strip():
            return None
        return out

    def write_store(self, key: str, value: str) -> None:
        name = encode_key(key)
        import tempfile
        import os as _os
        fd, local = tempfile.mkstemp(suffix=".val")
        with _os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value)
        try:
            # 全 argv、零 shell 元字符：adb shell 会把命令行在设备上**重新解析**，
            # 任何引号/管道/重定向都可能在那一步散掉（第一版就是这么静默失败的）。
            self.run("push", local, "/data/local/tmp/tl_seed.val")
            self.sh("run-as", PKG, "mkdir", "-p", "files/store")
            self.sh("run-as", PKG, "cp", "/data/local/tmp/tl_seed.val", f"files/store/{name}.val")
        finally:
            _os.unlink(local)


def encode_key(key: str) -> str:
    """键 → 文件名，规则必须与 NativeStore.kt 的 fileFor() 一致。"""
    return "".join(
        c if ((c.isalnum() and c.isascii()) or c in "._-")
        else "".join(f"%{b:02X}" for b in c.encode())
        for c in key
    )


def today_key() -> str:
    return time.strftime("%Y-%m-%d")


def minutes_ago(minutes: int) -> str:
    return time.strftime("%H:%M", time.localtime(time.time() - minutes * 60))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default=None)
    ap.add_argument("--keep", action="store_true", help="验收后保留应用数据（默认清掉）")
    args = ap.parse_args()

    if not APK.exists():
        print("APK 不在位：先跑 ./gradlew assembleDebug", file=sys.stderr)
        return 2
    d = Device(args.serial)
    devices = d.run("devices").stdout
    if "\tdevice" not in devices:
        print("没有可用设备：\n" + devices, file=sys.stderr)
        return 2

    print("== 安装 ==")
    # 刻意**不加** -g：-g 会把运行时权限全给了，从而绕过 POST_NOTIFICATIONS 的真实
    # 授权流程——而「声明了却从不申请」正是这条路径上真出过的缺陷（常驻通知会静默
    # 消失）。下面按真实顺序走：先没有权限，再模拟用户同意。
    install = d.run("install", "-r", str(APK))
    check("APK 安装成功", "Success" in install.stdout + install.stderr,
          (install.stdout + install.stderr).strip()[-200:])
    d.sh("pm", "clear", PKG)

    print("== 播种数据（模拟已经用过一段时间）==")
    day = today_key()
    # 相对现在算：尾占位点 45 分钟前（在默认 240 分钟上限内，应当允许静默写入）
    start_ts = minutes_ago(90)
    tail_ts = minutes_ago(45)
    data = {"version": 1, "entries": [
        {"id": "seed1", "ts": f"{day}T{start_ts}", "what": "写代码", "tags": ["当前主线"]},
        {"id": "seed2", "ts": f"{day}T{tail_ts}", "what": "", "tags": []},
    ]}
    config = {"mainline": ["当前主线"], "chips": [
        {"name": "睡觉", "bucket": "maintain", "longOk": True},
        {"name": "刷手机", "bucket": "leak", "longOk": False},
    ]}
    # 先启动一次让应用建好私有目录
    d.sh("am", "start", "-n", f"{PKG}/org.eigentime.timelogger.MainActivity")
    time.sleep(6)
    d.write_store("timelog.v1", json.dumps(data, ensure_ascii=False))
    d.write_store("timelog.config", json.dumps(config, ensure_ascii=False))
    d.write_store("timelog.selectedDate", day)
    check("播种后能读回数据（run-as 通路可用）", d.read_store("timelog.v1") is not None)

    print("== 主界面：运行时能否在桥上启动 ==")
    d.sh("am", "force-stop", PKG)
    d.sh("am", "start", "-n", f"{PKG}/org.eigentime.timelogger.MainActivity")
    time.sleep(8)
    # 界面渲染的证据：应用会在启动后重算显示镜像（QuickWrite.refreshMirror）
    mirror_raw = d.read_store("timelog.widgetMirror.v1")
    check("启动后写出了显示镜像（说明桥页与真实模块都跑起来了）", mirror_raw is not None)
    if mirror_raw:
        mirror = json.loads(mirror_raw)
        check("镜像的下一起点＝尾占位点", mirror.get("nextStartTs") == f"{day}T{tail_ts}",
              json.dumps(mirror, ensure_ascii=False)[:200])
        check("镜像的上一条是播种的那条", mirror.get("lastWhat") == "写代码", str(mirror.get("lastWhat")))
        check("建议标签以当前主线开头", (mirror.get("suggestTags") or [None])[0] == "当前主线",
              json.dumps(mirror.get("suggestTags"), ensure_ascii=False))
    dump = d.sh("dumpsys", "window", "windows")
    check("主界面在前台", PKG in dump, "窗口里没看到应用")

    print("== 一键写入（小组件/磁贴/快捷方式都走这条）==")
    before = d.read_store("timelog.v1")
    d.sh("am", "start", "-a", "org.eigentime.timelogger.action.WRITE",
         "-n", f"{PKG}/org.eigentime.timelogger.QuickWriteActivity",
         "--es", "tag", "睡觉")
    time.sleep(9)   # 冷启动时桥要建 WebView（真机实测 ~660ms）+ 一次 eval（~150ms）
    after = d.read_store("timelog.v1")
    check("数据变了（一键确实写进了同一份存储）", after != before)
    if after:
        entries = json.loads(after)["entries"]
        filled = next((e for e in entries if e["ts"] == f"{day}T{tail_ts}"), None)
        check("追认的是尾占位点那一段", filled is not None and filled.get("what") == "睡觉",
              json.dumps(filled, ensure_ascii=False) if filled else "没找到")
        check("占位条被复用而不是新增（id 不变）", filled is not None and filled.get("id") == "seed2",
              filled.get("id") if filled else "")
        tail = entries[-1]
        check("now 处补出新占位", tail.get("what") == "", json.dumps(tail, ensure_ascii=False))
        stamps = [e["ts"] for e in entries]
        check("同刻唯一", len(set(stamps)) == len(stamps), ",".join(stamps))

    print("== 守卫：空白超过上限（默认 240 分钟）时不许静默写 ==")
    stale = {"version": 1, "entries": [
        {"id": "old1", "ts": f"{day}T{minutes_ago(360)}", "what": "写代码", "tags": ["当前主线"]},
        {"id": "old2", "ts": f"{day}T{minutes_ago(300)}", "what": "", "tags": []},
    ]}
    d.write_store("timelog.v1", json.dumps(stale, ensure_ascii=False))
    stale_before = d.read_store("timelog.v1")
    d.sh("am", "start", "-a", "org.eigentime.timelogger.action.WRITE",
         "-n", f"{PKG}/org.eigentime.timelogger.QuickWriteActivity",
         "--es", "tag", "睡觉")
    time.sleep(9)
    check("空白 5 小时时数据一个字节都没动", d.read_store("timelog.v1") == stale_before)

    print("== 守卫：今天还没有记录时不许静默写 ==")
    d.write_store("timelog.v1", json.dumps({"version": 1, "entries": [
        {"id": "old", "ts": "2026-01-01T09:00", "what": "很久以前", "tags": ["当前主线"]}]},
        ensure_ascii=False))
    guarded_before = d.read_store("timelog.v1")
    d.sh("am", "start", "-a", "org.eigentime.timelogger.action.WRITE",
         "-n", f"{PKG}/org.eigentime.timelogger.QuickWriteActivity",
         "--es", "tag", "睡觉")
    time.sleep(6)
    check("守卫拦下后数据一个字节都没动", d.read_store("timelog.v1") == guarded_before)
    win = d.sh("dumpsys", "window", "windows")
    check("守卫拦下后打开了应用让人确认起点", PKG in win)

    print("== 常驻通知（含 API 33+ 的真实授权流程）==")
    sdk = int((d.sh("getprop", "ro.build.version.sdk") or "0").strip() or 0)
    perms = d.sh("dumpsys", "package", PKG)
    check("清单声明了 POST_NOTIFICATIONS", "android.permission.POST_NOTIFICATIONS" in perms)
    if sdk >= 33:
        # **自己建立前提**，不假设安装时的状态：`install -r` 会保留既有授权，
        # 手工装过一次就足以让「未授权」这个前提不成立（第一版正是这样误报的）。
        d.sh("pm", "revoke", PKG, "android.permission.POST_NOTIFICATIONS")
        d.sh("am", "force-stop", PKG)
        d.sh("am", "start", "-n", f"{PKG}/org.eigentime.timelogger.MainActivity")
        time.sleep(7)
        check("未授权时不发通知（不假装入口存在）", d.posted_notifications() == 0,
              f"没授权却发出了 {d.posted_notifications()} 条")
        # 关掉可能弹出的权限对话框，免得挡住后面的窗口判定
        d.sh("input", "keyevent", "4")
    d.sh("pm", "grant", PKG, "android.permission.POST_NOTIFICATIONS")
    d.sh("am", "force-stop", PKG)
    d.sh("am", "start", "-n", f"{PKG}/org.eigentime.timelogger.MainActivity")
    time.sleep(8)
    check("授权后常驻通知立刻出现", d.posted_notifications() >= 1, "dumpsys 里没有已发布的通知记录")
    record = d.notification_record()
    check("发在 ongoing 频道上", "channel=ongoing" in record, record[:160])
    check("锁屏不展示记录内容（VISIBILITY_SECRET）", "vis=SECRET" in record, record[:160])
    check("带直接回复动作", "写一句" in record or "Type it" in record, record[-300:])
    check("带一键标签动作", "当前主线" in record or "Current focus" in record, record[-300:])

    print("== 磁贴的二级选择页 ==")
    d.sh("am", "start", "-n", f"{PKG}/org.eigentime.timelogger.QuickPickActivity")
    time.sleep(4)
    check("选择页能打开", "QuickPickActivity" in d.sh("dumpsys", "window", "windows"))

    print("== 网络能力：权限清单里不该有 INTERNET ==")
    check("没有 INTERNET 权限", "android.permission.INTERNET" not in perms)

    if not args.keep:
        d.sh("pm", "clear", PKG)

    print()
    if failures:
        print(f"FAILED {len(failures)}/{checks}：")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"OK {checks}/{checks} 断言通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
