#!/usr/bin/env python3
"""Run ambient regression checks in one command.

Runs:
1) in-memory ambient round-trip check
2) real-module ambient area I/O check
"""

import argparse
import os
import subprocess
import sys


def run_step(label, cmd):
    print("==>", label)
    print("    $", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("FAIL:", label)
        return result.returncode
    print("PASS:", label)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run ambient regression suite")
    parser.add_argument(
        "--nwn-dir",
        default="/home/js/.steam/steam/steamapps/common/Neverwinter Nights",
        help="Path to NWN installation directory",
    )
    parser.add_argument(
        "--module",
        default="/home/js/.steam/steam/steamapps/common/Neverwinter Nights/data/nwm/Chapter1.nwm",
        help="Path to module file",
    )
    parser.add_argument(
        "--area",
        default="",
        help="Optional area resref to target for real-area I/O check",
    )
    parser.add_argument(
        "--skip-real-area",
        action="store_true",
        help="Skip real module/area I/O check and run only in-memory checks",
    )
    args = parser.parse_args()

    util_dir = os.path.abspath(os.path.dirname(__file__))
    py = sys.executable or "python3"

    rc = run_step(
        "in-memory round-trip",
        [py, os.path.join(util_dir, "check_ambient_sound_roundtrip.py")],
    )
    if rc != 0:
        return rc

    if args.skip_real_area:
        print("PASS: ambient regression suite (in-memory only)")
        return 0

    cmd = [
        py,
        os.path.join(util_dir, "check_ambient_area_io.py"),
        "--nwn-dir",
        args.nwn_dir,
        "--module",
        args.module,
    ]
    if args.area:
        cmd.extend(["--area", args.area])

    rc = run_step("real area I/O", cmd)
    if rc != 0:
        return rc

    print("PASS: ambient regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
