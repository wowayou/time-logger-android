#!/usr/bin/env python3
# 时间尺 Android 壳 (time-logger-android)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""无头开机一台模拟器，开完就把 device_check.py 跑一遍。

    python3 scripts/emulator_up.py            # 开机 + 验收
    python3 scripts/emulator_up.py --no-check # 只开机，留着手动看
    python3 scripts/emulator_up.py --stop     # 关掉

前置：`/dev/kvm` 可读写。WSL 每次重启都会把它恢复成 660 root:kvm，永久解决办法是在
`/etc/wsl.conf` 里加：

    [boot]
    command = /bin/chmod 666 /dev/kvm

（一次性 sudo 编辑 + `wsl --shutdown`，之后每次开机自动生效。）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = Path.home() / "android-toolchain/sdk"
JDK = Path.home() / "android-toolchain/jdk17"
ADB = SDK / "platform-tools/adb"
AVD = "tl36"
IMAGE = "system-images;android-36;google_apis;x86_64"
SERIAL = "emulator-5554"
LOG = Path("/tmp/emulator.log")


def env() -> dict[str, str]:
    e = dict(os.environ)
    e["JAVA_HOME"] = str(JDK)
    e["ANDROID_HOME"] = str(SDK)
    e["ANDROID_SDK_ROOT"] = str(SDK)
    e["PATH"] = f"{JDK}/bin:{SDK}/platform-tools:" + e.get("PATH", "")
    return e


def kvm_ready() -> bool:
    return os.access("/dev/kvm", os.R_OK | os.W_OK)


def adb(*args: str, timeout: int = 60) -> str:
    out = subprocess.run([str(ADB), *args], capture_output=True, text=True,
                         timeout=timeout, check=False, env=env())
    return (out.stdout or "") + (out.stderr or "")


def ensure_avd() -> None:
    if (Path.home() / ".android/avd" / f"{AVD}.ini").exists():
        return
    print(f"创建 AVD {AVD}")
    subprocess.run(
        [str(SDK / "cmdline-tools/latest/bin/avdmanager"), "create", "avd",
         "-n", AVD, "-k", IMAGE, "-d", "pixel_6", "--force"],
        input="no\n", text=True, check=True, env=env(),
    )


def boot(wait_seconds: int) -> bool:
    if SERIAL in adb("devices"):
        print("模拟器已在运行")
        return True
    LOG.write_text("", encoding="utf-8")
    print("无头开机中……")
    with LOG.open("ab") as log:
        subprocess.Popen(
            [str(SDK / "emulator/emulator"), "-avd", AVD, "-no-window", "-no-audio",
             "-no-boot-anim", "-gpu", "swiftshader_indirect", "-no-snapshot-save",
             "-memory", "3072", "-port", "5554"],
            stdout=log, stderr=log, cwd=str(SDK / "emulator"), env=env(),
            start_new_session=True,
        )
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if adb("-s", SERIAL, "shell", "getprop", "sys.boot_completed", timeout=20).strip() == "1":
            print(f"开机完成（{int(wait_seconds - (deadline - time.time()))}s）")
            # 解锁并保持唤醒，否则 WebView 不绘制、通知也看不全
            adb("-s", SERIAL, "shell", "input", "keyevent", "82")
            adb("-s", SERIAL, "shell", "svc", "power", "stayon", "true")
            return True
        text = LOG.read_text(encoding="utf-8", errors="replace")
        for marker in ("PANIC", "Segmentation fault", "cannot add library", "KVM"):
            if marker in text and "added library" not in text:
                print(f"模拟器启动失败（日志里出现 {marker}）：\n" + text[-800:], file=sys.stderr)
                return False
        time.sleep(5)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--wait", type=int, default=900, help="开机等待上限（秒）")
    args = ap.parse_args()

    if args.stop:
        adb("-s", SERIAL, "emu", "kill")
        print("已关闭模拟器")
        return 0

    if not kvm_ready():
        print("/dev/kvm 不可读写——见本文件顶部的 wsl.conf 办法（WSL 重启会重置权限）",
              file=sys.stderr)
        return 2
    ensure_avd()
    if not boot(args.wait):
        return 1
    if args.no_check:
        print(f"模拟器就绪：{SERIAL}（adb -s {SERIAL} ...）")
        return 0
    return subprocess.run([sys.executable, str(ROOT / "scripts/device_check.py"),
                           "--serial", SERIAL], cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
