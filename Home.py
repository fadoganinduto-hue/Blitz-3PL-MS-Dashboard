"""Blitz Operations Dashboard — main entry point.

Lane 1 of the redesign: navigation & information architecture.

Replaces the flat 19-page sidebar with a sectioned `st.navigation()` layout.
Pages themselves are unchanged — only how they're registered and grouped.

Sections (current live state):
    Blitz Delivery · Blitz Mobile · EV · Analysis · Admin

Note on the future 5-stream model:
    Group Overview, Borzo Overview/By-Client, and EV Leasing pages don't
    exist in the live repo yet. They'll be added in a later lane once the
    raw data carries the workstream identifier column. When those pages
    land, we just append new entries to PAGES below — Lane 1 holds.
"""
import streamlit as st
from pathlib import Path
from datetime import datetime

from data_loader import (
    load_main_data,
    load_ev_data,
    load_action_items,
    load_mobile_data,
    fetch_from_sharepoint,
    is_sharepoint_configured,
)
from utils import apply_global_styles, render_theme_toggle

# ── Page config (defaults; pages may override their own title/icon) ───────────
st.set_page_config(
    page_title="Blitz Ops",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Lane 2A.1: render Light/Dark toggle in sidebar, then inject theme CSS ─────
theme_mode = render_theme_toggle()
apply_global_styles(theme_mode)

# ── Data loading: SharePoint (if configured) → falls back to local data/ ──────
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"

# Each entry: (session_key, secrets_key, local_filename, loader, companion_loaders)
#   - secrets_key       — key under [files] in st.secrets pointing at the SharePoint URL
#   - local_filename    — fallback file in data/ if SharePoint not configured
#   - companion_loaders — extra parsers run on the same file bytes (e.g. EV sheet)
LOADERS = [
    ("delivery_data", "DELIVERY", "delivery_latest.xlsx", load_main_data, [
        ("ev_data", load_ev_data),
        ("action_items", load_action_items),
    ]),
    ("mobile_data", "MOBILE", "mobile_sellers_latest.xlsx", load_mobile_data, []),
]

# Show data source in sidebar so it's obvious which mode is active
_using_sharepoint = is_sharepoint_configured()


def _get_file_bytes(secrets_key: str, local_filename: str) -> bytes | None:
    """Resolve file bytes from SharePoint if configured, else local data/.

    SharePoint successes/failures are logged into session_state by
    fetch_from_sharepoint itself (see _sp_last_ok / _sp_last_error); this
    function just swallows the exception so the loader loop can fall through
    to the local-file path or skip cleanly.
    """
    if _using_sharepoint:
        try:
            files_secrets = st.secrets.get("files", {})
            url = files_secrets.get(secrets_key) if hasattr(files_secrets, "get") else files_secrets[secrets_key]
            if url:
                return fetch_from_sharepoint(url)
        except Exception:  # noqa: BLE001
            # Error already recorded in session_state['_sp_last_error'] by
            # fetch_from_sharepoint. Sidebar status indicator surfaces it.
            pass
    fpath = DATA_DIR / local_filename
    if fpath.exists():
        with open(fpath, "rb") as f:
            return f.read()
    return None


_bytes_fetched_now: int = 0  # Total bytes loaded *this run* — drives the post-refresh toast.
for key, secrets_key, filename, loader, companions in LOADERS:
    if key in st.session_state:
        continue
    file_bytes = _get_file_bytes(secrets_key, filename)
    if file_bytes is None:
        continue
    _bytes_fetched_now += len(file_bytes)
    try:
        st.session_state[key] = loader(file_bytes)
        for companion_key, companion_loader in companions:
            if companion_key not in st.session_state:
                st.session_state[companion_key] = companion_loader(file_bytes)
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"Failed to load {filename}: {exc}")

# Post-refresh toast: fires once if the user just clicked Refresh AND the rerun
# actually re-fetched bytes. Both conditions matter — if the click happened but
# nothing was fetched (e.g. SharePoint failed), we don't want to falsely confirm.
if st.session_state.pop("_refresh_clicked", False) and _bytes_fetched_now > 0:
    _now = datetime.now().strftime("%H:%M:%S")
    _mb = _bytes_fetched_now / (1024 * 1024)
    st.toast(f"✓ Refreshed at {_now} · fetched {_mb:.1f} MB", icon="✅")


def format_relative(ts: datetime) -> str:
    """Compact "N ago" string for a naive local-time datetime.

    Pairs with `_sp_last_ok` / `_sp_last_error['time']`, which are also naive
    `datetime.now()` values written by fetch_from_sharepoint. Same timezone
    on both sides → no aware/naive mix-ups.
    """
    delta = datetime.now() - ts
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def render_data_source_status() -> None:
    """One-stop sidebar widget describing the data source's current health.

    Distinguishes five states:
      📁 Local data folder       — SharePoint not configured.
      🟢 Live from SharePoint    — Last fetch succeeded; serving fresh data.
      ⚠️  SharePoint unreachable — Last attempt failed but a previous fetch
                                  succeeded; serving cached bytes from then.
      🔴 Cannot reach SharePoint — Never succeeded this session; no data.
      ⏳ Loading...              — Cold start, no fetch attempted yet.

    Note: the app fetches two SharePoint files (delivery + mobile) per run.
    If only one of them fails, _sp_last_error['time'] > _sp_last_ok and we
    flip to ⚠️ even though one stream is healthy. That's the literal
    spec semantics — the indicator tracks the most recent event.
    """
    if not is_sharepoint_configured():
        st.sidebar.markdown("📁 **Local data folder**")
        return

    last_ok    = st.session_state.get('_sp_last_ok')
    last_error = st.session_state.get('_sp_last_error')

    rel = format_relative(last_ok) if last_ok else "never"

    if last_error and last_ok and (last_error['time'] > last_ok):
        st.sidebar.error(
            f"⚠️ **SharePoint unreachable**\n\n"
            f"Last good fetch: {rel}\n\n"
            f"Showing cached data. Click ↻ to retry."
        )
        with st.sidebar.expander("Error details"):
            st.code(last_error['message'])
    elif last_error and not last_ok:
        st.sidebar.error(
            "🔴 **Cannot reach SharePoint**\n\n"
            "No data loaded. Check credentials and file URLs."
        )
        with st.sidebar.expander("Error details"):
            st.code(last_error['message'])
    elif last_ok:
        st.sidebar.markdown(
            f"🟢 **Live from SharePoint**\n\n"
            f"Refreshed {rel}"
        )
    else:
        st.sidebar.info("⏳ Loading from SharePoint...")


def render_data_freshness_card() -> None:
    """Show per-dataset max period + row count in sidebar."""
    delivery = st.session_state.get("delivery_data")
    mobile   = st.session_state.get("mobile_data")
    borzo    = st.session_state.get("borzo_monthly_data")

    rows = []
    if delivery is not None and not delivery.empty and "Year" in delivery.columns:
        try:
            max_y = int(delivery["Year"].max())
            max_w = int(delivery[delivery["Year"] == max_y]["Week (by Year)"].max())
            rows.append(("Delivery", f"{max_y} W{max_w}", len(delivery)))
        except Exception:
            pass
    if mobile is not None and not mobile.empty and "Year" in mobile.columns:
        try:
            max_y = int(mobile["Year"].max())
            max_w = int(mobile[mobile["Year"] == max_y]["Week (by Year)"].max())
            rows.append(("Mobile", f"{max_y} W{max_w}", len(mobile)))
        except Exception:
            pass
    if borzo is not None and not borzo.empty and "Year" in borzo.columns:
        try:
            max_y = int(borzo["Year"].max())
            max_m = borzo[borzo["Year"] == max_y]["Month"].iloc[-1]
            rows.append(("Borzo", f"{max_y} {max_m}", len(borzo)))
        except Exception:
            pass

    if not rows:
        return

    with st.sidebar.expander("📅 Data freshness", expanded=False):
        for name, period, n in rows:
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; "
                f"font-size:0.85rem; opacity:0.85;'>"
                f"<span>{name}</span>"
                f"<span>{period} · {n:,} rows</span></div>",
                unsafe_allow_html=True,
            )


render_data_source_status()
render_data_freshness_card()

if _using_sharepoint:
    with st.sidebar:
        if st.button("↻ Refresh data", use_container_width=True, key="_refresh_data"):
            st.cache_data.clear()
            # Drop the parsed DataFrames + companions from session_state so the
            # loader loop actually re-runs on the next pass. Clearing only the
            # cache leaves the parsed data sitting in session_state, which would
            # short-circuit the fetch and leave the indicator stuck.
            for k, _, _, _, comps in LOADERS:
                st.session_state.pop(k, None)
                for ck, _ in comps:
                    st.session_state.pop(ck, None)
            st.session_state.pop("data", None)
            # Flag picked up by the post-load toast on the next run.
            st.session_state["_refresh_clicked"] = True
            st.rerun()

# Backward-compat: legacy pages reference st.session_state['data']
if "delivery_data" in st.session_state and "data" not in st.session_state:
    st.session_state["data"] = st.session_state["delivery_data"]


# ── Build navigation ──────────────────────────────────────────────────────────
PAGES = {
    "Blitz Delivery": [
        st.Page("pages/1_📊_Overview.py",            title="Overview",           icon="📊", default=True),
        st.Page("pages/2_👥_By_Client.py",           title="By Client",          icon="👥"),
        st.Page("pages/2_🏗️_By_Project.py",          title="By Project",         icon="🏗️"),
        st.Page("pages/2_🎯_By_SLA_Type.py",         title="By SLA Type",        icon="🎯"),
        st.Page("pages/2_📅_Weekly_Performance.py",  title="Weekly Performance", icon="📅"),
        st.Page("pages/3_🗺️_By_Location.py",         title="By Location",        icon="🗺️"),
        st.Page("pages/4_🏙️_By_Team.py",             title="By Team",            icon="🏙️"),
        st.Page("pages/7_📈_Finance_Check.py",       title="Finance Check",      icon="📈"),
        st.Page("pages/7_🎯_SLA_Check.py",           title="SLA Check",          icon="🎯"),
        st.Page("pages/8_🔬_Deep_Dive.py",           title="Deep Dive",          icon="🔬"),
        st.Page("pages/9_📋_Delivery_Detailed.py",      title="Delivery Detailed",        icon="📋"),
        st.Page("pages/2_📋_Project_Detailed.py",       title="Project Detailed",         icon="📋"),
        st.Page("pages/2_📋_Client_Project_Detail.py",  title="Client → Project Detail",  icon="📋"),
    ],
    "Blitz Mobile": [
        st.Page("pages/10_📱_Mobile_Overview.py",            title="Overview",           icon="📱"),
        st.Page("pages/11_📅_Mobile_Period_Performance.py",  title="Period Performance", icon="📅"),
        st.Page("pages/12_👥_Mobile_By_Client.py",           title="By Client",          icon="👥"),
        st.Page("pages/13_🏗️_Mobile_By_Project.py",          title="By Project",         icon="🏗️"),
        st.Page("pages/13_🗺️_Mobile_By_Location.py",         title="By Location",        icon="🗺️"),
        st.Page("pages/14_🏙️_Mobile_By_Team.py",             title="By Team",            icon="🏙️"),
        st.Page("pages/15_🔬_Mobile_Deep_Dive.py",           title="Deep Dive",          icon="🔬"),
        st.Page("pages/16_📋_Mobile_Detailed.py",            title="Mobile Detailed",    icon="📋"),
        st.Page("pages/16_📋_Mobile_Project_Detailed.py",    title="Mobile Project Detailed", icon="📋"),
    ],
    "EV": [
        st.Page("pages/5_⚡_EV_Overview.py", title="EV Overview", icon="⚡"),
    ],
    "Analysis": [
        st.Page("pages/20_🔍_Strategy_Analysis.py", title="Strategy Analysis", icon="🔍"),
    ],
    "Admin": [
        st.Page("pages/99_🔐_Updater.py", title="Updater", icon="🔐"),
    ],
}

# Dispatch to selected page
nav = st.navigation(PAGES)
nav.run()
