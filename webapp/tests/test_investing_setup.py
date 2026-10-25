from investing.config import enabled,settings_update,render_setup


def test_saved_toggle_overrides_legacy_environment_in_both_directions():
    assert enabled({'INVESTING_V2_ENABLED':'false'},{'investing_v2_enabled':True})
    assert not enabled({'INVESTING_V2_ENABLED':'true'},{'investing_v2_enabled':False})
    assert enabled({'INVESTING_V2_ENABLED':'true'},{})
    assert not enabled({}, {})


def test_checkbox_save_and_absent_form_preserve_settings():
    assert settings_update({})=={}
    assert settings_update({'investing_v2_settings_present':['1']})=={'investing_v2_enabled':False}
    assert settings_update({'investing_v2_settings_present':['1'],'investing_v2_enabled':['1']})=={'investing_v2_enabled':True}
    assert ' checked' in render_setup({'investing_v2_enabled':True})
    assert ' checked' not in render_setup({'investing_v2_enabled':False})
