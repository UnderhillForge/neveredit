#!/usr/bin/env python3
"""Regression check for Chapter1.nwm area name decoding.

Usage:
  ./util/check_chapter1_area_names.py
  ./util/check_chapter1_area_names.py --nwn-dir /path/to/NWN --module /path/to/Chapter1.nwm

Exit code is non-zero when required district prefixes are missing.
"""

import argparse
import os
import sys


def add_local_venv_sitepackages():
    """Add .venv site-packages to sys.path when launched with system Python."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    venv_lib = os.path.join(base_dir, ".venv", "lib")
    if not os.path.isdir(venv_lib):
        return
    for entry in os.listdir(venv_lib):
        if not entry.startswith("python"):
            continue
        site_packages = os.path.join(venv_lib, entry, "site-packages")
        if os.path.isdir(site_packages) and site_packages not in sys.path:
            sys.path.insert(0, site_packages)


def add_repo_parent_to_path():
    """Make imports of `neveredit.*` work from a source checkout."""
    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    parent = os.path.dirname(repo_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)


def normalize_text(value):
    if isinstance(value, bytes):
        return value.decode("latin1", "ignore")
    if value is None:
        return ""
    return str(value)


def main():
    parser = argparse.ArgumentParser(description="Check Chapter1 area names")
    parser.add_argument(
        "--nwn-dir",
        default="/home/js/.steam/steam/steamapps/common/Neverwinter Nights",
        help="Path to NWN installation directory",
    )
    parser.add_argument(
        "--module",
        default="/home/js/.steam/steam/steamapps/common/Neverwinter Nights/data/nwm/Chapter1.nwm",
        help="Path to Chapter1 module file",
    )
    args = parser.parse_args()

    add_local_venv_sitepackages()
    add_repo_parent_to_path()

    from neveredit.game.ResourceManager import ResourceManager
    from neveredit.game.Module import Module
    from neveredit.util import neverglobals

    if not os.path.exists(args.nwn_dir):
        print("ERROR: NWN directory not found:", args.nwn_dir)
        return 2
    if not os.path.exists(args.module):
        print("ERROR: Module file not found:", args.module)
        return 2

    expected_prefixes = [
        "City Core",
        "Peninsula",
        "Beggar's Nest",
        "Blacklake",
        "Docks",
    ]
    expected_contains = ["Sewers"]

    rm = ResourceManager()
    neverglobals.setResourceManager(rm)
    rm.scanGameDir(args.nwn_dir)

    mod = Module(args.module)
    rm.addModule(mod)

    areas = mod.getAreas()
    names = [normalize_text(area.getName()) for area in areas.values()]

    print("Area count:", len(names))

    missing = []
    for prefix in expected_prefixes:
        if not any(name.startswith(prefix) for name in names):
            missing.append(prefix)
    for text in expected_contains:
        if not any(text in name for name in names):
            missing.append(text)

    if missing:
        print("FAIL: Missing expected district prefixes:")
        for prefix in missing:
            print(" -", prefix)
        print("\nSample decoded names:")
        for sample in sorted(names)[:20]:
            print(" -", sample)
        return 1

    print("PASS: All expected district prefixes detected.")
    for prefix in expected_prefixes:
        matches = [n for n in names if n.startswith(prefix)]
        print(" - %s: %d" % (prefix, len(matches)))
    for text in expected_contains:
        matches = [n for n in names if text in n]
        print(" - contains '%s': %d" % (text, len(matches)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
