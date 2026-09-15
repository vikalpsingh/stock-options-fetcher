import unittest
from unittest.mock import patch

import app


class KiteProfileTabConfigurationTest(unittest.TestCase):
    def test_blank_profile_defaults_to_core_tabs_only(self):
        visible_tabs = app.kite_profile_visible_tabs(
            "Shanti",
            {"Shanti": app.blank_kite_profile("Shanti")},
        )

        for tab_id in ("home", "kite-setup", "positions", "research", "place", "order-management"):
            self.assertIn(tab_id, visible_tabs)
        self.assertNotIn("dhan-it", visible_tabs)

    def test_saved_profile_strategy_tab_is_rendered_for_that_profile(self):
        profiles = {name: app.blank_kite_profile(name) for name in app.KITE_PROFILE_NAMES}
        profiles["Shanti"]["VISIBLE_TABS"] = app.normalize_profile_visible_tabs(
            ["home", "kite-setup", "positions", "dhan-it"]
        )

        with patch.object(app, "load_kite_profiles", return_value=profiles):
            rendered = app.render_page(app.PageState(active_tab="kite-setup", kite_profile="Shanti")).decode()

        self.assertIn("Profile Tab Configuration", rendered)
        self.assertIn('data-tab="dhan-it">DHAN-IT</button>', rendered)
        self.assertNotIn('data-tab="kite-spreads">DHAN</button>', rendered)

    def test_hidden_active_tab_falls_back_to_kite_setup(self):
        profiles = {name: app.blank_kite_profile(name) for name in app.KITE_PROFILE_NAMES}
        profiles["Shanti"]["VISIBLE_TABS"] = app.normalize_profile_visible_tabs(["home", "kite-setup"])

        with patch.object(app, "load_kite_profiles", return_value=profiles):
            rendered = app.render_page(app.PageState(active_tab="dhan-it", kite_profile="Shanti")).decode()

        self.assertIn('body class="tab-kite-setup"', rendered)
        self.assertIn("This tab is hidden for the selected Kite profile", rendered)
        self.assertNotIn('data-tab="dhan-it">DHAN-IT</button>', rendered)


if __name__ == "__main__":
    unittest.main()
