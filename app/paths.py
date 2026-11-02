"""Canonical project paths shared by runtime modules.

所有路径都从项目根目录推导，避免模块移动后 `__file__` 相对路径失效。
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
LOG_DIR = PROJECT_ROOT / "logs"
LIB_DIR = PROJECT_ROOT / "lib"
TOOLS_DIR = PROJECT_ROOT / "tools"
