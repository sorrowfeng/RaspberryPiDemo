#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import importlib.util
import os
import subprocess
import sys

try:
    import curses
except ImportError:
    curses = None


EXAMPLES_DIR = "aarch64/share/LHandProLib/examples"
DEMO_DIR = os.path.join(EXAMPLES_DIR, "RaspberryPiDemo")
CONFIG_DIR = os.path.join(DEMO_DIR, "configs")
ACTIVE_CONFIG_FILE = os.path.join(DEMO_DIR, "active_config.py")


def show_menu(stdscr, title, options, step=""):
    curses.curs_set(0)
    current_row = 0

    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        if step:
            stdscr.addstr(0, 0, step[: width - 1], curses.A_BOLD | curses.color_pair(1))

        title_line = 2 if step else 0
        separator = "=" * min(50, width - 1)
        stdscr.addstr(title_line, 0, separator, curses.color_pair(1))
        stdscr.addstr(title_line + 1, 0, title.center(min(50, width - 1)), curses.A_BOLD | curses.color_pair(1))
        stdscr.addstr(title_line + 2, 0, separator, curses.color_pair(1))

        start_line = title_line + 4
        for idx, option in enumerate(options):
            y = start_line + idx
            if y >= height - 2:
                break

            line = f"> {option}" if idx == current_row else f"  {option}"
            attrs = curses.A_REVERSE | curses.color_pair(2) if idx == current_row else curses.color_pair(2)
            stdscr.addstr(y, 2, line[: width - 3], attrs)

        hint = "使用方向键选择，Enter 确认，q 退出"
        hint_y = min(height - 1, start_line + len(options) + 2)
        stdscr.addstr(hint_y, 0, hint[: width - 1], curses.color_pair(3))
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(options) - 1:
            current_row += 1
        elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
            return current_row
        elif key in (ord("q"), ord("Q"), 27):
            return None


def show_message(stdscr, title, message):
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    separator = "=" * min(50, width - 1)
    stdscr.addstr(0, 0, separator, curses.color_pair(1))
    stdscr.addstr(1, 0, title.center(min(50, width - 1)), curses.A_BOLD | curses.color_pair(1))
    stdscr.addstr(2, 0, separator, curses.color_pair(1))
    stdscr.addstr(4, 0, message[: width - 1], curses.color_pair(2))
    stdscr.addstr(6, 0, "按任意键继续...", curses.color_pair(3))
    stdscr.refresh()
    stdscr.getch()


def input_number(stdscr, title, prompt, default="1"):
    curses.echo()
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    separator = "=" * min(50, width - 1)
    stdscr.addstr(0, 0, separator, curses.color_pair(1))
    stdscr.addstr(1, 0, title.center(min(50, width - 1)), curses.A_BOLD | curses.color_pair(1))
    stdscr.addstr(2, 0, separator, curses.color_pair(1))
    stdscr.addstr(4, 0, prompt[: width - 1], curses.color_pair(2))

    input_prompt = f"请输入（默认 {default}）: "
    stdscr.addstr(6, 0, input_prompt[: width - 1], curses.color_pair(3))
    stdscr.addstr(7, 0, f"直接按 Enter 使用默认值 {default}", curses.color_pair(3))
    stdscr.refresh()

    input_str = stdscr.getstr(6, len(input_prompt), 16).decode("utf-8").strip()
    curses.noecho()
    return input_str if input_str else default


def load_preset_metadata(file_path):
    spec = importlib.util.spec_from_file_location(os.path.basename(file_path).replace(".py", ""), file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    display_name = getattr(module, "DISPLAY_NAME", "")
    if not display_name or "?" in display_name:
        basename = os.path.splitext(os.path.basename(file_path))[0].removeprefix("config_")
        display_name = basename.replace("_", " / ")
    return display_name, module.PRESET


def step1_select_sdk(stdscr):
    sdk_files = sorted(glob.glob("LHandProLib-API-Linux-*.tar.gz"))
    if not sdk_files:
        show_message(stdscr, "错误", "未找到 LHandProLib-API-Linux-*.tar.gz 文件")
        sys.exit(1)

    options = ["跳过（不解压 SDK）"] + sdk_files
    choice = show_menu(stdscr, "选择 SDK 版本", options)
    if choice is None:
        return None
    if choice == 0:
        return "SKIP"
    return sdk_files[choice - 1]


def step2_extract_sdk(stdscr, sdk_file):
    if sdk_file == "SKIP":
        return

    stdscr.clear()
    stdscr.addstr(0, 0, "解压 SDK", curses.A_BOLD)
    stdscr.addstr(2, 0, f"正在解压 {sdk_file} ...")
    stdscr.refresh()
    subprocess.run(["tar", "-zxf", sdk_file], check=True)
    subprocess.run(
        "echo 'leadshine' | sudo -S rm -rf i386/ x86_64/",
        shell=True,
        check=True,
        stderr=subprocess.DEVNULL,
    )


def step3_clean_examples(stdscr):
    if not os.path.isdir(EXAMPLES_DIR):
        show_message(stdscr, "错误", f"目录不存在: {EXAMPLES_DIR}")
        sys.exit(1)

    stdscr.clear()
    stdscr.addstr(0, 0, "清理示例目录", curses.A_BOLD)
    stdscr.addstr(2, 0, f"正在清理 {EXAMPLES_DIR} ...")
    stdscr.refresh()
    subprocess.run(
        f"echo 'leadshine' | sudo -S rm -rf {EXAMPLES_DIR}/*",
        shell=True,
        check=True,
        stderr=subprocess.DEVNULL,
    )


def step4_extract_demo(stdscr):
    demo_file = "RaspberryPiDemo.7z"
    if not os.path.isfile(demo_file):
        show_message(stdscr, "错误", f"文件不存在: {demo_file}")
        sys.exit(1)

    stdscr.clear()
    stdscr.addstr(0, 0, "解压 Demo", curses.A_BOLD)
    stdscr.addstr(2, 0, f"正在解压 {demo_file} ...")
    stdscr.refresh()

    if subprocess.run(["which", "7z"], capture_output=True).returncode == 0:
        subprocess.run(["7z", "x", demo_file, f"-o{EXAMPLES_DIR}", "-y"], stdout=subprocess.DEVNULL, check=True)
        return
    if subprocess.run(["which", "7za"], capture_output=True).returncode == 0:
        subprocess.run(["7za", "x", demo_file, f"-o{EXAMPLES_DIR}", "-y"], stdout=subprocess.DEVNULL, check=True)
        return

    show_message(stdscr, "错误", "未找到 7z 命令，请先安装 p7zip-full")
    sys.exit(1)


def step5_select_preset(stdscr):
    if not os.path.isdir(CONFIG_DIR):
        show_message(stdscr, "错误", f"目录不存在: {CONFIG_DIR}")
        sys.exit(1)

    preset_files = [
        file_path
        for file_path in sorted(glob.glob(os.path.join(CONFIG_DIR, "config_*.py")))
        if os.path.isfile(file_path) and not file_path.endswith("__init__.py")
    ]
    if not preset_files:
        show_message(stdscr, "错误", f"{CONFIG_DIR} 下未找到预设文件")
        sys.exit(1)

    display_items = []
    for file_path in preset_files:
        display_name, _preset = load_preset_metadata(file_path)
        display_items.append((file_path, display_name))

    options = [item[1] for item in display_items] + ["跳过（保留当前 active_config.py）"]
    choice = show_menu(stdscr, "选择预设配置", options)
    if choice is None:
        return None
    if choice == len(options) - 1:
        return "SKIP"
    return display_items[choice][0]


def write_active_config(preset_module, device_overrides):
    file_content = (
        '"""Selects which preset is active at runtime."""\n\n'
        f'ACTIVE_PRESET = "{preset_module}"\n\n'
        "RUNTIME_OVERRIDES = {\n"
        f"    \"device\": {device_overrides},\n"
        "}\n"
    )
    with open(ACTIVE_CONFIG_FILE, "w", encoding="utf-8") as file_obj:
        file_obj.write(file_content)


def step6_activate_preset(stdscr, preset_file):
    if preset_file == "SKIP":
        show_message(stdscr, "保留配置", "已跳过预设切换，保留当前 active_config.py")
        return

    display_name, preset = load_preset_metadata(preset_file)
    preset_module = f"configs.{os.path.splitext(os.path.basename(preset_file))[0]}"
    device_overrides = {}

    if preset["communication"]["default_mode"] == "CANFD":
        default_node_id = str(preset["device"]["canfd_node_id"])
        node_id = input_number(stdscr, "设置 CANFD Node ID", "请输入 CANFD Node ID:", default=default_node_id)
        if node_id.isdigit():
            device_overrides["canfd_node_id"] = int(node_id)

    write_active_config(preset_module, device_overrides)
    show_message(stdscr, "预设已激活", f"当前预设: {display_name}")


def step7_complete(stdscr):
    options = ["是，立即关机", "否，返回系统"]
    choice = show_menu(stdscr, "部署完成，是否立即关机？", options)
    if choice == 0 or choice is None:
        stdscr.clear()
        stdscr.addstr(0, 0, "正在关机...", curses.A_BOLD)
        stdscr.refresh()
        subprocess.run(
            "echo 'leadshine' | sudo -S shutdown -h 0",
            shell=True,
            stderr=subprocess.DEVNULL,
        )


def main_wrapper(stdscr):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    try:
        sdk_file = step1_select_sdk(stdscr)
        if sdk_file is None:
            return

        step2_extract_sdk(stdscr, sdk_file)
        step3_clean_examples(stdscr)
        step4_extract_demo(stdscr)

        preset_file = step5_select_preset(stdscr)
        if preset_file is None:
            return

        step6_activate_preset(stdscr, preset_file)
        step7_complete(stdscr)
    except Exception as exc:
        show_message(stdscr, "错误", str(exc))


def main():
    if curses is None:
        print("setup.py requires curses support and should be run on the target Linux device.")
        sys.exit(1)

    try:
        curses.wrapper(main_wrapper)
    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(0)


if __name__ == "__main__":
    main()
