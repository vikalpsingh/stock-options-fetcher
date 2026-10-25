"""Configuration for the additive engine; never changes trading settings."""
import os

MODEL_VERSION = 'investing-v2.0-data-1'


def enabled(environ=None, settings=None):
    if settings is not None and "investing_v2_enabled" in settings:
        return settings["investing_v2_enabled"] is True
    return (os.environ if environ is None else environ).get('INVESTING_V2_ENABLED', '').lower() == 'true'


def render_setup(settings):
    checked = ' checked' if enabled(settings=settings) else ''
    return '<section class="panel"><div class="panel-title">Investing Decision Engine</div><input type="hidden" name="investing_v2_settings_present" value="1"><label><input type="checkbox" name="investing_v2_enabled" value="1"'+checked+'> Enable Investing v2 scoring and research</label><p class="status">Shared application setting. Adds evidence-based scores and optional GPT review to Investing. Does not enable orders or automatic GPT calls. Save Kite Setup to apply; no restart required.</p></section>'


def settings_update(form):
    if (form.get('investing_v2_settings_present') or [''])[0] != '1':
        return {}
    return {'investing_v2_enabled': (form.get('investing_v2_enabled') or [''])[0] == '1'}
