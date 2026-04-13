#!/usr/bin/env python3
"""Package the project into a 7z archive one directory above the repo."""

import os
import subprocess
import sys


def main() -> int:
    current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    parent_dir = os.path.dirname(current_dir)
    folder_name = os.path.basename(current_dir)
    output_path = os.path.join(parent_dir, f"{folder_name}.7z")

    print(f"Packing directory: {current_dir}")
    print(f"Output archive: {output_path}")

    cmd = [
        "7z",
        "a",
        output_path,
        folder_name,
        "-xr!.git",
        "-xr!logs",
        "-xr!__pycache__",
        f"-x!{folder_name}/lib/LHandProLib.dll",
    ]

    try:
        result = subprocess.run(cmd, cwd=parent_dir)
    except FileNotFoundError:
        print("7z command not found. Please install 7-Zip first.")
        return 1

    if result.returncode == 0:
        print(f"Pack completed: {output_path}")
        return 0

    print(f"Pack failed with code: {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
