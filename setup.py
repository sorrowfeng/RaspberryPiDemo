#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import glob
import subprocess
import curses

def show_menu(stdscr, title, options, step=""):
    curses.curs_set(0)
    stdscr.clear()
    current_row = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # 显示标题
        if step:
            stdscr.addstr(0, 0, step, curses.A_BOLD | curses.color_pair(1))

        title_line = 2 if step else 0
        stdscr.addstr(title_line, 0, "=" * min(50, w-1), curses.color_pair(1))
        stdscr.addstr(title_line + 1, 0, title.center(min(50, w-1)), curses.A_BOLD | curses.color_pair(1))
        stdscr.addstr(title_line + 2, 0, "=" * min(50, w-1), curses.color_pair(1))

        # 显示选项
        start_line = title_line + 4
        for idx, option in enumerate(options):
            x = 2
            y = start_line + idx
            if y >= h - 2:
                break

            if idx == current_row:
                stdscr.addstr(y, x, f"► {option}", curses.A_REVERSE | curses.color_pair(2))
            else:
                stdscr.addstr(y, x, f"  {option}")

        # 显示提示
        hint_y = min(h - 1, start_line + len(options) + 2)
        stdscr.addstr(hint_y, 0, "使用 ↑↓ 方向键选择, Enter 确认, q 退出", curses.color_pair(3))

        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(options) - 1:
            current_row += 1
        elif key == ord('\n'):
            return current_row
        elif key == ord('q') or key == ord('Q') or key == 27:  # q or ESC
            return None

def show_message(stdscr, title, message):
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    stdscr.addstr(0, 0, "=" * min(50, w-1), curses.color_pair(1))
    stdscr.addstr(1, 0, title.center(min(50, w-1)), curses.A_BOLD | curses.color_pair(1))
    stdscr.addstr(2, 0, "=" * min(50, w-1), curses.color_pair(1))
    stdscr.addstr(4, 0, message, curses.color_pair(2))
    stdscr.addstr(6, 0, "按任意键继续...", curses.color_pair(3))
    stdscr.refresh()
    stdscr.getch()

def input_number(stdscr, title, prompt, default="1"):
    curses.echo()
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    stdscr.addstr(0, 0, "=" * min(50, w-1), curses.color_pair(1))
    stdscr.addstr(1, 0, title.center(min(50, w-1)), curses.A_BOLD | curses.color_pair(1))
    stdscr.addstr(2, 0, "=" * min(50, w-1), curses.color_pair(1))
    stdscr.addstr(4, 0, prompt, curses.color_pair(2))

    input_prompt = f"请输入(默认{default}): "
    stdscr.addstr(6, 0, input_prompt, curses.color_pair(3))
    stdscr.addstr(7, 0, f"(直接按 Enter 使用默认值 {default})", curses.color_pair(3))
    stdscr.refresh()

    # 计算中文字符的显示宽度
    display_width = sum(2 if ord(c) > 127 else 1 for c in input_prompt)
    input_str = stdscr.getstr(6, display_width, 10).decode('utf-8').strip()
    curses.noecho()
    return input_str if input_str else default

def step1_select_sdk(stdscr):
    sdk_files = glob.glob("LHandProLib-API-Linux-*.tar.gz")
    if not sdk_files:
        show_message(stdscr, "错误", "未找到 LHandProLib-API-Linux-*.tar.gz 文件")
        sys.exit(1)

    options = ["跳过 (不解压SDK)"] + sdk_files
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
    stdscr.addstr(2, 0, f"正在解压 {sdk_file}...")
    stdscr.refresh()
    subprocess.run(["tar", "-zxf", sdk_file], check=True)

    cmd = "echo 'leadshine' | sudo -S rm -rf i386/ x86_64/"
    subprocess.run(cmd, shell=True, check=True, stderr=subprocess.DEVNULL)

def step3_clean_examples(stdscr):
    examples_dir = "aarch64/share/LHandProLib/examples"
    if not os.path.isdir(examples_dir):
        show_message(stdscr, "错误", f"目录 {examples_dir} 不存在")
        sys.exit(1)

    stdscr.clear()
    stdscr.addstr(0, 0, "清理示例目录", curses.A_BOLD)
    stdscr.addstr(2, 0, f"正在清理 {examples_dir}...")
    stdscr.refresh()

    cmd = f"echo 'leadshine' | sudo -S rm -rf {examples_dir}/*"
    subprocess.run(cmd, shell=True, check=True, stderr=subprocess.DEVNULL)


def step4_extract_demo(stdscr):
    demo_file = "RaspberryPiDemo.7z"
    target_dir = "aarch64/share/LHandProLib/examples"

    if not os.path.isfile(demo_file):
        show_message(stdscr, "错误", f"文件 {demo_file} 不存在")
        sys.exit(1)

    stdscr.clear()
    stdscr.addstr(0, 0, "解压 Demo", curses.A_BOLD)
    stdscr.addstr(2, 0, f"正在解压 {demo_file}...")
    stdscr.refresh()

    if subprocess.run(["which", "7z"], capture_output=True).returncode == 0:
        subprocess.run(["7z", "x", demo_file, f"-o{target_dir}", "-y"],
                      stdout=subprocess.DEVNULL, check=True)
    elif subprocess.run(["which", "7za"], capture_output=True).returncode == 0:
        subprocess.run(["7za", "x", demo_file, f"-o{target_dir}", "-y"],
                      stdout=subprocess.DEVNULL, check=True)
    else:
        show_message(stdscr, "错误", "未找到 7z 命令，请安装: sudo apt-get install p7zip-full")
        sys.exit(1)

def step5_select_config(stdscr):
    config_dir = "aarch64/share/LHandProLib/examples/RaspberryPiDemo/configs"

    if not os.path.isdir(config_dir):
        show_message(stdscr, "错误", f"目录 {config_dir} 不存在")
        sys.exit(1)

    config_files = [f for f in glob.glob(f"{config_dir}/*") if os.path.isfile(f)]
    if not config_files:
        show_message(stdscr, "错误", f"{config_dir} 目录为空")
        sys.exit(1)

    # 中文显示映射
    config_display = {
        "config_DH116_CANFD_exhibit.py": "DH116 - CANFD - 展览",
        "config_DH116_ECAT_exhibit.py": "DH116 - ECAT - 展览",
        "config_DH116_RS485_exhibit.py": "DH116 - RS485 - 展览",
        "config_DH116_CANFD_aging.py": "DH116 - CANFD - 老化测试",
        "config_DH116_CANFD_finger_aging.py": "DH116 - CANFD - 单指老化测试",
        "config_DH116_ECAT_aging.py": "DH116 - ECAT - 老化测试",
        "config_DH116_RS485_aging.py": "DH116 - RS485 - 老化测试",
        "config_DH116S_CANFD_exhibit.py": "DH116S - CANFD - 展览",
        "config_DH116S_CANFD_aging.py": "DH116S - CANFD - 老化测试",
        "config_DH116S_CANFD_finger_aging.py": "DH116S - CANFD - 单指老化测试",
        "config_DH116S_CANFD_grasp.py": "DH116S - CANFD - 抓握测试",
        "config_Module_CANFD_aging.py": "模组 - CANFD - 老化测试",
        "config_Module_ECAT_aging.py": "模组 - ECAT - 老化测试"
    }

    # 排序规则：DH116 -> DH116S -> 模组
    def sort_key(filepath):
        basename = os.path.basename(filepath)
        if basename.startswith("config_DH116S"):
            return (1, basename)
        elif basename.startswith("config_DH116"):
            return (0, basename)
        elif basename.startswith("config_Module"):
            return (2, basename)
        else:
            return (3, basename)

    config_files.sort(key=sort_key)

    config_names = []
    for f in config_files:
        basename = os.path.basename(f)
        display_name = config_display.get(basename, basename)
        config_names.append(display_name)

    # 添加跳过选项
    config_names.append("跳过 (保留现有配置)")

    choice = show_menu(stdscr, "选择配置文件", config_names)

    if choice is None:
        return None
    if choice == len(config_names) - 1:  # 选择了跳过
        return "SKIP"
    return config_files[choice]

def step6_copy_config(stdscr, config_file):
    if config_file == "SKIP":
        stdscr.clear()
        stdscr.addstr(0, 0, "复制配置文件", curses.A_BOLD)
        stdscr.addstr(2, 0, "已跳过配置文件复制，保留现有配置")
        stdscr.refresh()
        stdscr.getch()
        return

    target_file = "aarch64/share/LHandProLib/examples/RaspberryPiDemo/config.py"
    stdscr.clear()
    stdscr.addstr(0, 0, "复制配置文件", curses.A_BOLD)
    stdscr.addstr(2, 0, "正在复制配置文件...")
    stdscr.refresh()
    subprocess.run(["cp", config_file, target_file], check=True)

    # 检查是否是CANFD版本
    basename = os.path.basename(config_file)
    if "CANFD" in basename:
        node_id = input_number(stdscr, "设置 CANFD 节点 ID", "请输入 CANFD 节点 ID (数字):")

        if node_id.isdigit():
            # 读取文件内容
            with open(target_file, 'r') as f:
                content = f.read()

            # 替换 CANFD_NODE_ID
            import re
            content = re.sub(r'CANFD_NODE_ID\s*=\s*\d+', f'CANFD_NODE_ID = {node_id}', content)

            # 写回文件
            with open(target_file, 'w') as f:
                f.write(content)

def step7_complete(stdscr):
    options = ["是，立即关机", "否，不关机"]
    choice = show_menu(stdscr, "部署完成！是否立即关机？", options)

    if choice == 0 or choice is None:
        stdscr.clear()
        stdscr.addstr(0, 0, "正在关机...", curses.A_BOLD)
        stdscr.refresh()
        cmd = "echo 'leadshine' | sudo -S shutdown -h 0"
        subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)

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

        config_file = step5_select_config(stdscr)
        if config_file is None:
            return

        step6_copy_config(stdscr, config_file)
        step7_complete(stdscr)
    except Exception as e:
        stdscr.clear()
        stdscr.addstr(0, 0, f"错误: {e}", curses.color_pair(3))
        stdscr.addstr(2, 0, "按任意键退出...")
        stdscr.refresh()
        stdscr.getch()

def main():
    try:
        curses.wrapper(main_wrapper)
    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(0)

if __name__ == "__main__":
    main()
