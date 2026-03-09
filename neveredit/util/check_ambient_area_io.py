#!/usr/bin/env python3
"""Regression check for ambient sound I/O on a real module area.

Loads a module from disk, finds an area with ambient sounds, mutates key
ambient fields in memory, and verifies values persist through a re-wrap.
"""

import argparse
import os
import sys


def add_local_venv_sitepackages():
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
    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    parent = os.path.dirname(repo_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)


def pick_area_with_sounds(mod, preferred_area=None):
    if preferred_area:
        area = mod.getArea(preferred_area)
        if area is None:
            return None, "area %r not found" % preferred_area
        sounds = area.getSounds() or []
        if not sounds:
            return None, "area %r has no ambient sounds" % preferred_area
        return area, None

    for area_name, area in mod.getAreas().items():
        sounds = area.getSounds() or []
        if sounds:
            return area, None
    return None, "no areas with ambient sounds found"


def main():
    parser = argparse.ArgumentParser(description="Check ambient area I/O")
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
        help="Optional area resref to test",
    )
    args = parser.parse_args()

    add_local_venv_sitepackages()
    add_repo_parent_to_path()

    from neveredit.game.ResourceManager import ResourceManager
    from neveredit.game.Module import Module
    from neveredit.game.Sound import SoundInstance
    from neveredit.util import neverglobals

    if not os.path.exists(args.nwn_dir):
        print("ERROR: NWN directory not found:", args.nwn_dir)
        return 2
    if not os.path.exists(args.module):
        print("ERROR: Module file not found:", args.module)
        return 2

    rm = ResourceManager()
    neverglobals.setResourceManager(rm)
    rm.scanGameDir(args.nwn_dir)

    mod = Module(args.module)
    rm.addModule(mod)

    area, error = pick_area_with_sounds(mod, args.area.strip() or None)
    if area is None:
        print("FAIL:", error)
        return 1

    sounds = area.getSounds() or []
    sound = sounds[0]
    root = sound.getMainGFFStruct()

    before_radius = float(sound.getRadius())
    before_event = int(sound.getSoundSetEvent() if hasattr(sound, 'getSoundSetEvent') else (sound['SoundSetEvent'] or 1))
    before_attn = int(sound.getAttenuationModel() if hasattr(sound, 'getAttenuationModel') else (sound['AttenuationModel'] or 0))

    new_radius = before_radius + 1.0
    new_event = max(1, min(256, before_event + 1))
    new_attn = 0 if before_attn == 1 else 1

    sound.setRadius(new_radius)
    if hasattr(sound, 'setSoundSetEvent'):
        sound.setSoundSetEvent(new_event)
    else:
        sound['SoundSetEvent'] = new_event
    if hasattr(sound, 'setAttenuationModel'):
        sound.setAttenuationModel(new_attn)
    else:
        sound['AttenuationModel'] = new_attn

    reloaded = SoundInstance(root)

    assert abs(float(reloaded.getRadius()) - new_radius) < 1e-6, "radius mismatch"
    assert int(reloaded.getSoundSetEvent() if hasattr(reloaded, 'getSoundSetEvent') else reloaded['SoundSetEvent']) == new_event, "SoundSetEvent mismatch"
    assert int(reloaded.getAttenuationModel() if hasattr(reloaded, 'getAttenuationModel') else reloaded['AttenuationModel']) == new_attn, "AttenuationModel mismatch"

    # Restore original in-memory values to avoid surprising callers.
    sound.setRadius(before_radius)
    if hasattr(sound, 'setSoundSetEvent'):
        sound.setSoundSetEvent(before_event)
    else:
        sound['SoundSetEvent'] = before_event
    if hasattr(sound, 'setAttenuationModel'):
        sound.setAttenuationModel(before_attn)
    else:
        sound['AttenuationModel'] = before_attn

    print("PASS: area=%s sounds=%d radius=%.2f->%.2f event=%d->%d attn=%d->%d" % (
        area.name,
        len(sounds),
        before_radius,
        new_radius,
        before_event,
        new_event,
        before_attn,
        new_attn,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
