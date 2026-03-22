from pathlib import Path

from neveredit.util import Preferences as pref_mod


def test_render_preferences_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    pref_mod.globalPrefs = None

    prefs = pref_mod.getPreferences()
    assert "RenderLiveTuning" in prefs.values
    assert "RenderDepthLOD" in prefs.values

    prefs["RenderLiveTuning"]["ToonBands"] = 9.0
    prefs["RenderDepthLOD"]["FogNearDistance"] = 150.0
    assert prefs.save() is True

    pref_mod.globalPrefs = None
    prefs2 = pref_mod.getPreferences()
    assert float(prefs2["RenderLiveTuning"]["ToonBands"]) == 9.0
    assert float(prefs2["RenderDepthLOD"]["FogNearDistance"]) == 150.0

    pref_file = Path(prefs2.prefPath)
    assert pref_file.exists()
