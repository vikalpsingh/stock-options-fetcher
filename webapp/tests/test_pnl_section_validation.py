import app


def test_pnl_actions_are_isolated_from_other_section_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "pnl-section.sqlite3")
    state = app.PageState(active_tab="pnl")

    page = app.render_pnl_panel(state)

    assert 'formaction="/pnl/sync-today" formnovalidate' in page
    assert 'formaction="/pnl/load" formnovalidate' in page
    assert 'formaction="/pnl/export-csv" formnovalidate' in page
    assert 'formaction="/pnl/save-risk-config" formnovalidate' in page
    assert 'formaction="/pnl/import-kite" formnovalidate' in page
    # Workbook ownership and file checks remain explicit on the server route.
    assert 'name="pnl_kite_file"' in page
    assert 'name="pnl_import_confirm"' in page


def test_monthly_loss_amount_uses_whole_rupees_not_one_plus_thousand_steps(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "APP_DB_PATH", tmp_path / "pnl-amount.sqlite3")
    page = app.render_pnl_panel(app.PageState(active_tab="pnl"))

    assert 'min="1" step="1" name="monthly_max_loss_inr"' in page
    assert 'step="1000" name="monthly_max_loss_inr"' not in page
