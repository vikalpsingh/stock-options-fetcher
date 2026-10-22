from pathlib import Path

SOURCE = Path("app.py").read_text(encoding="utf-8-sig")
start = SOURCE.index("PROFILE_TAB_OPTIONS:")
end = SOURCE.index("\ndef blank_kite_profile(", start)
scope = {"Any": object, "selected_kite_profile_name": lambda name: name,
         "blank_kite_profile": lambda name: {}}
exec(compile(SOURCE[start:end], "profile_tabs", "exec"), scope)
normalize = scope["normalize_profile_visible_tabs"]
visible = scope["kite_profile_visible_tabs"]


def test_explicit_selection_overrides_feature_flags_and_is_profile_specific():
    profiles = {
        "A": {"VISIBLE_TABS": ["trade"], "NIFTY_INCOME_ENABLED": True,
              "NIFTY_GROW_ENABLED": True},
        "B": {"VISIBLE_TABS": ["nifty-2", "nifty-grow"]},
    }
    assert visible("A", profiles) == {"home", "kite-setup", "trade"}
    assert visible("B", profiles) == {"home", "kite-setup", "nifty-2", "nifty-grow"}


def test_empty_selection_does_not_restore_optional_defaults():
    assert normalize([]) == ["home", "kite-setup"]
    assert normalize(["invalid"]) == ["home", "kite-setup"]
    assert normalize(None) == list(scope["DEFAULT_PROFILE_VISIBLE_TABS"])
    assert normalize("trade,trade,unknown") == ["home", "kite-setup", "trade"]


def test_all_selectable_tabs_round_trip_and_client_does_not_force_nifty():
    for tab_id in scope["PROFILE_TAB_IDS"]:
        assert set(normalize([tab_id])) == {"home", "kite-setup", tab_id}
    assert "visibleTabs.add('nifty-income')" not in SOURCE
    assert "visibleTabs.add('nifty-2')" not in SOURCE
    assert "visibleTabs.add('nifty-grow')" not in SOURCE
