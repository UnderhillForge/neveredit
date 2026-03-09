#!/usr/bin/env python3
"""Smoke-check ambient sound round-trip behavior used by the editor.

This validates that key ambient fields survive wrapper updates and reload:
- radius (MaxDistance)
- SoundSetEvent
- AttenuationModel
"""

import os
import sys


def add_repo_parent_to_path():
    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    parent = os.path.dirname(repo_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)


def build_sound_struct(include_max_distance=True):
    from neveredit.file.GFFFile import GFFStruct

    gff = GFFStruct()
    gff.add("ObjectId", 1001, "INT")
    gff.add("XPosition", 12.0, "FLOAT")
    gff.add("YPosition", 34.0, "FLOAT")
    gff.add("ZPosition", 2.5, "FLOAT")
    if include_max_distance:
        gff.add("MaxDistance", 6.0, "FLOAT")
    gff.add("SoundSetEvent", 3, "INT")
    gff.add("AttenuationModel", 0, "INT")
    gff.add("SoundSet", "as_owl", "CExoString")
    return gff


def run_case(include_max_distance):
    from neveredit.game.Sound import SoundInstance

    raw = build_sound_struct(include_max_distance=include_max_distance)
    sound = SoundInstance(raw)

    sound.setRadius(11.25)
    sound["SoundSetEvent"] = 9
    sound["AttenuationModel"] = 1

    root = sound.getMainGFFStruct()
    assert root.hasEntry("MaxDistance"), "MaxDistance missing after setRadius"
    assert abs(float(root["MaxDistance"]) - 11.25) < 1e-6, "Radius did not persist"
    assert int(root["SoundSetEvent"]) == 9, "SoundSetEvent did not persist"
    assert int(root["AttenuationModel"]) == 1, "AttenuationModel did not persist"

    reloaded = SoundInstance(root)
    assert abs(float(reloaded.getRadius()) - 11.25) < 1e-6, "Reloaded radius mismatch"
    assert int(reloaded["SoundSetEvent"]) == 9, "Reloaded SoundSetEvent mismatch"
    assert int(reloaded["AttenuationModel"]) == 1, "Reloaded AttenuationModel mismatch"


def main():
    add_repo_parent_to_path()

    run_case(include_max_distance=True)
    run_case(include_max_distance=False)

    print("PASS: ambient sound round-trip checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
