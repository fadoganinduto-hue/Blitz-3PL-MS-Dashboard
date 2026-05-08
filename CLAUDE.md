# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run / develop

```bash
pip install -r requirements.txt
streamlit run Home.py            # http://localhost:8501
```

There are no tests, no linter config, and no build step — this is a Streamlit app run directly. The `.devcontainer/` config auto-launches `streamlit run Home.py` on attach.

## Big picture

This is a Streamlit multi-page dashboard for two business streams (Blitz Delivery + Blitz Mobile Sellers) plus an EV sub-section. There are three architectural seams worth understanding before editing:

### 1. Data source resolution (Home.py → data_loader.py)

`Home.py` decides per-load whether to fetch from SharePoint or fall back to the local `data/` folder, controlled by `is_sharepoint_configured()` (true iff `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` are all in `st.secrets`). Same parsers run on the bytes either way — never branch parsers on source.

The `LOADERS` list in `Home.py` is the single registry of "what data exists":

```python
("delivery_data", "DELIVERY", "delivery_latest.xlsx", load_main_data, [companions...])
("mobile_data",   "MOBILE",   "mobile_sellers_latest.xlsx", load_mobile_data, [])
```

`secrets_key` (`DELIVERY` / `MOBILE`) maps into `st.secrets["files"]` for SharePoint URLs (see `.streamlit/secrets.toml.example`). Adding a new dataset = append one tuple; everything else is downstream.

SharePoint fetch (`fetch_from_sharepoint`) uses Microsoft Graph's `/shares` endpoint with a base64url-encoded sharing token, app-only auth via MSAL, and a 5-minute `@st.cache_data` TTL. The "↻ Refresh data" sidebar button calls `st.cache_data.clear()` to force a fresh fetch.

### 2. Session-state convention

Pages don't load data themselves. They call:
- `require_data()` → `st.session_state["delivery_data"]` (also exposed as legacy `["data"]`)
- `require_mobile_data()` → `st.session_state["mobile_data"]`

Both helpers live in `utils.py` and call `_auto_load_from_data_folder()` as a safety net so a page works even if you navigate to it directly without going through `Home.py` first. Other session keys: `ev_data`, `action_items`. The legacy `data` alias is kept in `Home.py` (line ~109) for older pages — don't remove it without grepping.

### 3. Page registration (Home.py PAGES dict)

The `pages/` folder uses filename-prefix ordering only as a hint — the canonical navigation is the `PAGES` dict in `Home.py`, grouped into sections (`Blitz Delivery`, `Blitz Mobile`, `EV`, `Analysis`, `Admin`). Multiple pages share the same numeric prefix (`2_👥_By_Client.py`, `2_🏗️_By_Project.py`, `2_🎯_By_SLA_Type.py`, `2_📅_Weekly_Performance.py`) — the dict order is what users see. **To add a page: drop a file in `pages/`, then register it in `PAGES`.** A file in `pages/` not listed in `PAGES` won't appear in nav.

## Data shape (delivery)

`load_main_data` produces a long-format DataFrame keyed by `(Year, Week (by Year), Client Name, Client Location, Project, …)`. Derived columns added by the loader and relied on by every page:

- `GP`, `GP Margin %` — gross profit + margin
- `SRPO`, `RCPO`, `TCPO`, `TRPO` — selling/rider/total cost/total revenue **per order** (Delivery Volume basis)
- `OTP Rate %` — combined dedicated + backup courier on-time percentage, capped at 100% (data entry can produce >100 raw)
- `_total_deliveries`, `_total_ontime`, `_total_late` — internal SLA aggregates (note the underscore prefix; not for display)

`_fix_week()` repairs week numbers like `12026` → `1` (Excel sometimes appends the year). `_clean_columns()` strips Excel helper/lookup columns (`Year.1`, `Project Name`, `Unnamed:`, etc.) — extend `_IGNORE_COLS` in `data_loader.py` if new junk appears.

## Data shape (mobile)

`load_mobile_data` reads from sheet `'NEW COLUMN TEMPLATE'` and **de-duplicates date-split rows**: a single week sometimes spans two months (e.g. W14 = Mar 29–31 + Apr 1–4) and produces two rows for the same `(Year, Week, Client, Location, Project)` with riders counted twice. The loader collapses with `MAX` for `Total Active Riders` and `SUM` for everything else. After this, downstream `SUM` aggregations are correct across locations, so `mobile_aggregate()` and `build_mobile_trend()` plain-sum riders. **Do not bypass `load_mobile_data` and read the sheet directly** — you'll double-count.

Derived columns added:
- `Blitz Revenue` (alias for `Total Revenue Sharing % (Weekly)`), `Gross Revenue`, `COGS`, `Total Cost (Mobile)`
- `Profit Calc` = Total Revenue − Total Income Sales − Total Operational Cost
- `Profit Margin %`, `Blitz Margin %`

For monthly views, `build_mobile_trend()` averages weekly rider totals (not sum) — riders is a stock, not a flow.

**Mobile aggregation gotcha:** the source sheet has a raw `Profit` column AND the loader adds `Profit Calc` (the canonical computed value). `mobile_aggregate()` sums *both*. If you then rename `Profit Calc → Profit` for display on the whole frame, you get two `Profit` columns, which pyarrow rejects with `Duplicate column names found`. Always **select-then-rename**: pick the explicit list of source columns first (excluding `Profit`), then rename. `build_mobile_trend()` doesn't have this problem because it constructs `Profit` from `Profit Calc` via a fresh `agg(...)`.

## Shared page utilities (utils.py)

- `sidebar_filters(df, page_key=...)` — **delivery-only** filter set (Year / Blitz Team / Month / Client Level / SLA Type). Mobile pages have no equivalent because mobile data doesn't carry the `Blitz Team` / `Client Level` / `SLA Type` columns. Always pass a unique `page_key` to avoid widget-state collisions across pages.
- `get_available_periods` / `filter_period` / `prev_period_info` / `pop_pct` / `pop_label` — period (Weekly/Monthly) navigation primitives, used by **both** streams. Pages typically render a `st.radio("View by", ["Weekly", "Monthly"])` and feed the choice into these. `pop_label(mode)` returns the abbreviation (`"WoW"` or `"MoM"`) for KPI delta strings.
- `build_trend` (delivery) / `build_mobile_trend` (mobile) — canonical trend aggregations; downstream charts and tables read from their output.
- `apply_chart_theme(fig)` — wrap every Plotly figure with this for consistent typography, transparent background (so dark/light theme works), top-right horizontal legend, soft y-grid only.
- `idr_col` / `vol_col` / `pct_col` — `st.column_config.NumberColumn` factories. **Always pass numeric values to `st.dataframe` and use these for display formatting** — pre-formatting strings breaks Streamlit's column sort (e.g. `"5,827"` < `"641"` lexicographically).
- `fmt_idr` / `fmt_pct` / `fmt_vol` — text formatters for KPI cards and inline display only.
- `dataframe_with_freeze(df, *, key, column_config=None, default_freeze=None, **dataframe_kwargs)` — drop-in replacement for `st.dataframe` on **wide tables** (≥6 display columns). Renders a collapsed "🔒 Freeze columns" expander above the table; selected columns get `pinned=True` applied to their existing `column_config` (mutates the cloned dict — Streamlit column configs are dicts internally, so NumberColumn format/alignment is preserved). Accepts both DataFrames and Stylers (Stylers are unwrapped via `.data`). `key` must be unique per page; `default_freeze` should be the natural identifier (`Client Name`, `SLA Type`, `Project`, `Label`, etc.). Skip on narrow tables (≤4 cols) — the expander adds visual clutter that isn't worth it.

`COST_COMPONENTS` (exported from `data_loader.py`) is the canonical raw-column → display-bucket mapping used by cost-waterfall charts (`Rider Cost` → "Rider", `Mid-Mile/ Linehaul Cost` → "Mid-Mile", etc.). When adding a new cost waterfall, import this rather than re-hardcoding bucket names.

## Canonical delivery page skeleton

Every delivery page follows the same shape. New pages should match it so filter state, period selection, and PoP comparisons stay consistent:

```python
df_full = require_data()
df      = sidebar_filters(df_full, page_key="<unique>")
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="<unique>_view")
pop = pop_label(view_mode)

periods   = get_available_periods(df, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)
curr_df   = filter_period(df, view_mode, curr_yr, curr_p)
prev_df   = filter_period(df, view_mode, *prev_info[:2]) if prev_info else pd.DataFrame()

# KPIs (st.metric), then trend via build_trend(df, [...], view_mode), then drill-down tables
```

Mobile pages use `require_mobile_data()` + `build_mobile_trend()` and skip `sidebar_filters` (no equivalent helper exists; mobile pages either filter inline or expose nothing).

## Theme

`render_theme_toggle()` adds a Light/Dark radio in the sidebar; `apply_global_styles(mode)` injects the matching CSS. Both are called once from `Home.py` after `st.set_page_config()`. Streamlit removed the in-app theme picker in 1.40+, which is why this exists. CSS targets stable `data-testid="..."` selectors; new-page styling is automatic and shouldn't need page-level overrides.

## Admin / Updater (pages/99_🔐_Updater.py)

Password-gated (via `st.secrets["admin_password"]`) page that commits uploaded `.xlsx` files to `data/delivery_latest.xlsx` or `data/mobile_sellers_latest.xlsx` on the configured GitHub repo via the Contents API. Streamlit Cloud auto-redeploys on push (~30s). When SharePoint is configured this workflow is largely superseded but kept as a fallback.

## Secrets reference

Stored in `.streamlit/secrets.toml` (gitignored; `.example` is committed):

- `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` — Azure AD app registration with `Files.Read.All` Application permission. All-or-nothing: missing any one disables SharePoint mode.
- `[files] DELIVERY = "..."`, `[files] MOBILE = "..."` — full SharePoint URLs (browser link or share link both work).
- `admin_password`, `github_token`, `github_repo`, `github_branch` — required only for the Updater page.
