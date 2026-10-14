#!/usr/bin/env python3
"""Prepare the host for CANFD over gs_usb (userspace pyusb backend).

项目默认用 gsusb 后端（纯用户态 gs_usb，pyusb + vendored gsusb_canfd）访问
CANFD 适配器。这条路径要求：

1. 装了 pyusb，且能找到 libusb-1.0；
2. 内核 gs_usb 驱动**没有**绑定适配器（内核驱动和 pyusb 抢同一个 USB 接口，
   谁先绑定谁独占）；
3. 非 root 运行时，udev 规则给了适配器读写权限（lib/hcanbus.rules）。

本脚本只做检查与修复，不改动项目配置。
"""

import os
import subprocess
import sys

SUDO_PASSWORD = "leadshine"
GS_USB_MODULE = "gs_usb"
ADAPTER_USB_IDS = ("a8fa", "8598")
UDEV_RULES_DIR = "/etc/udev/rules.d"
UDEV_RULE_FILE = "hcanbus.rules"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def filter_sudo_stderr(stderr: str) -> str:
    return "\n".join(
        line
        for line in stderr.splitlines()
        if "[sudo]" not in line and "password" not in line.lower()
    ).strip()


def run_sudo_command(cmd, timeout=15):
    return subprocess.run(
        ["sudo", "-S"] + cmd,
        input=SUDO_PASSWORD + "\n",
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def check_pyusb() -> bool:
    print("[1/4] 检查 pyusb / libusb ...")
    try:
        import usb.core  # noqa: F401
        import usb.util  # noqa: F401
    except ImportError as exc:
        print(f"  FAIL: pyusb 未安装 ({exc})")
        print("  修复: pip install 'pyusb>=1.2.1'")
        print("        apt install libusb-1.0-0")
        return False

    version = getattr(sys.modules.get("usb"), "__version__", "unknown")
    print(f"  OK: pyusb {version}")

    try:
        import usb.backend.libusb1
        backend = usb.backend.libusb1.get_backend()
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: libusb 后端加载异常: {exc}")
        return False

    if backend is None:
        print("  FAIL: 找不到 libusb-1.0")
        print("  修复: apt install libusb-1.0-0")
        return False

    print("  OK: libusb-1.0 可用")
    return True


def gs_usb_driver_dir() -> str:
    return f"/sys/bus/usb/drivers/{GS_USB_MODULE}"


def bound_gs_usb_interfaces():
    """返回被内核 gs_usb 绑定的接口名，例如 ['1-1.2:1.0']。"""
    try:
        entries = os.listdir(gs_usb_driver_dir())
    except OSError:
        return []
    return sorted(name for name in entries if ":" in name)


def ensure_gs_usb_unbound() -> bool:
    print(f"[2/4] 检查内核 {GS_USB_MODULE} 驱动绑定 ...")
    bound = bound_gs_usb_interfaces()
    if not bound:
        print(f"  OK: 没有接口被 {GS_USB_MODULE} 绑定，适配器可被 pyusb 独占")
        return True

    print(f"  检测到已绑定接口: {', '.join(bound)}")
    print(f"  尝试卸载 {GS_USB_MODULE} ...")
    try:
        result = run_sudo_command(["modprobe", "-r", GS_USB_MODULE])
    except FileNotFoundError:
        print("  sudo / modprobe 不可用")
        result = None
    except subprocess.TimeoutExpired:
        print("  modprobe 超时")
        result = None

    if result is not None and result.returncode == 0:
        print(f"  OK: 已卸载 {GS_USB_MODULE}")
        return True

    if result is not None:
        filtered = filter_sudo_stderr(result.stderr)
        if filtered:
            print(f"  modprobe -r 失败: {filtered}")

    # 模块可能内建或正被占用，退回逐个接口解绑
    print("  退回 sysfs 逐接口解绑 ...")
    ok = True
    for name in bound_gs_usb_interfaces():
        try:
            with open(f"{gs_usb_driver_dir()}/unbind", "w", encoding="utf-8") as file_obj:
                file_obj.write(name)
            print(f"  OK: 已解绑 {name}")
        except OSError as exc:
            print(f"  FAIL: 解绑 {name} 失败: {exc}")
            ok = False

    if ok and not bound_gs_usb_interfaces():
        return True
    print(f"  仍被 {GS_USB_MODULE} 占用，请先手动处理（或确认 module 已禁用）")
    return False


def check_udev_rule() -> None:
    print("[3/4] 检查 udev 权限规则 ...")
    rule_path = os.path.join(UDEV_RULES_DIR, UDEV_RULE_FILE)
    if os.path.exists(rule_path):
        print(f"  OK: {rule_path} 已存在")
        return
    print(f"  提示: 未安装 {rule_path}，非 root 运行可能无法打开适配器")
    print(f"  修复: sudo cp lib/{UDEV_RULE_FILE} {UDEV_RULES_DIR}/ && sudo udevadm control --reload")


def scan_adapters():
    print("[4/4] 枚举 gs_usb 适配器 ...")
    try:
        import gsusb_canfd
    except ImportError as exc:
        print(f"  FAIL: 无法导入 gsusb_canfd ({exc})")
        print("  该包应随项目位于项目根目录 gsusb_canfd/")
        return None

    print(f"  gsusb_canfd 版本: {getattr(gsusb_canfd, '__version__', 'unknown')}")
    try:
        adapters = list(gsusb_canfd.scan_adapters())
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: 扫描异常: {exc}")
        return None

    if not adapters:
        print("  未发现 gs_usb 适配器")
        print(f"  确认设备已插上（USB ID {'/'.join(ADAPTER_USB_IDS)}），")
        print(f"  且第 2 步的 {GS_USB_MODULE} 未绑定")
        return adapters

    print(f"  OK: 发现 {len(adapters)} 个适配器")
    for index, adapter in enumerate(adapters):
        try:
            name = adapter.display_name()
        except Exception:  # noqa: BLE001
            name = str(adapter)
        print(f"    [{index}] {name}  serial={adapter.serial or '-'} "
              f"bus={adapter.bus} addr={adapter.address}")
    print("  device_index 即上面的序号（USB 枚举顺序，插拔后可能变化）")

    # 多实例启动前必须确认序列号唯一：gsusb_canfd 的 open(adapter) 优先按序列号
    # 定位并取第一个匹配项，序列号重复会让多个进程打开同一个适配器且不报错。
    serials = [adapter.serial for adapter in adapters if adapter.serial]
    duplicated = sorted({s for s in serials if serials.count(s) > 1})
    if len(serials) < len(adapters):
        print(f"  注意: {len(adapters) - len(serials)} 个适配器无序列号，"
              f"将按 USB bus/address 定位（同样可靠）")
    if duplicated:
        print(f"  警告: 检测到重复序列号: {', '.join(duplicated)}")
        print("        open(adapter) 按序列号定位时只取第一个匹配，"
              "多个 main.py 进程会打开同一个适配器且不会报错！")
        print("        多实例（CANFD preset 的 default_launch_count=4）前必须先解决：")
        print("        换成序列号唯一的适配器，或改用按 bus/address 固定。")
        return adapters

    if len(adapters) > 1:
        print(f"  OK: {len(adapters)} 个适配器序列号唯一/缺失但 bus+address 可区分，支持多实例")
    return adapters


def main() -> int:
    print("CANFD gs_usb 模式准备\n")
    pyusb_ok = check_pyusb()
    unbound_ok = ensure_gs_usb_unbound()
    check_udev_rule()
    adapters = scan_adapters()

    print("\n结果:")
    print(f"  pyusb/libusb : {'OK' if pyusb_ok else 'FAIL'}")
    print(f"  gs_usb 解绑  : {'OK' if unbound_ok else 'FAIL'}")
    print(f"  适配器数量   : {'-' if adapters is None else len(adapters)}")

    if pyusb_ok and unbound_ok and adapters:
        print("\n可以启动 CANFD 模式：sudo python3 main.py -m CANFD")
        return 0

    print("\n尚不可用，请按上面提示修复后重试。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
