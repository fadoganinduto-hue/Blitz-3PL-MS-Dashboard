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


def _get_file_bytes(secrets_key: str, local_filename: str) -> tuple[bytes, datetime] | tuple[None, None]:
    """Resolve file bytes (and a refresh timestamp) from SharePoint if configured, else local data/."""
    if _using_sharepoint:
        try:
            files_secrets = st.secrets.get("files", {})
            url = files_secrets.get(secrets_key) if hasattr(files_secrets, "get") else files_secrets[secrets_key]
            if url:
                return fetch_from_sharepoint(url)
        except Exception as exc:  # noqa: BLE001
            st.sidebar.error(f"SharePoint fetch failed for {secrets_key}: {exc}")
    fpath = DATA_DIR / local_filename
    if fpath.exists():
        with open(fpath, "rb") as f:
            return f.read(), datetime.fromtimestamp(fpath.stat().st_mtime)
    return None, None


_refresh_times: list[datetime] = []
_bytes_fetched_now: int = 0  # Total bytes loaded *this run* — drives the post-refresh toast.
for key, secrets_key, filename, loader, companions in LOADERS:
    ts_key = f"_fetched_at_{key}"
    if key in st.session_state:
        if ts_key in st.session_state:
            _refresh_times.append(st.session_state[ts_key])
        continue
    file_bytes, fetched_at = _get_file_bytes(secrets_key, filename)
    if file_bytes is None:
        continue
    _bytes_fetched_now += len(file_bytes)
    if fetched_at is not None:
        st.session_state[ts_key] = fetched_at
        _refresh_times.append(fetched_at)
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


def _format_relative(ts: datetime) -> str:
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


with st.sidebar:
    if _using_sharepoint:
        st.markdown(
            "<div style='font-size:0.7rem; opacity:0.65; margin-top:0.5rem;'>"
            "🔗 Live from SharePoint · cache 5 min</div>",
            unsafe_allow_html=True,
        )
        if _refresh_times:
            latest = max(_refresh_times)
            st.markdown(
                f"<div style='font-size:0.7rem; opacity:0.65;' "
                f"title='{latest.strftime('%Y-%m-%d %H:%M:%S')}'>"
                f"⟳ Refreshed {_format_relative(latest)}</div>",
                unsafe_allow_html=True,
            )
        if st.button("↻ Refresh data", use_container_width=True, key="_refresh_data"):
            st.cache_data.clear()
            # Drop the parsed DataFrames + companions from session_state so the
            # loader loop actually re-runs on the next pass. Clearing only the
            # cache leaves the parsed data sitting in session_state, which would
            # short-circuit the fetch and leave the timestamp stale.
            for k, _, _, _, comps in LOADERS:
                st.session_state.pop(k, None)
                st.session_state.pop(f"_fetched_at_{k}", None)
                for ck, _ in comps:
                    st.session_state.pop(ck, None)
            st.session_state.pop("data", None)
            # Flag picked up by the post-load toast on the next run.
            st.session_state["_refresh_clicked"] = True
            st.rerun()
    else:
        st.markdown(
            "<div style='font-size:0.7rem; opacity:0.65; margin-top:0.5rem;'>"
            "📁 Loading from local data/ folder</div>",
            unsafe_allow_html=True,
        )
        if _refresh_times:
            latest = max(_refresh_times)
            st.markdown(
                f"<div style='font-size:0.7rem; opacity:0.65;' "
                f"title='{latest.strftime('%Y-%m-%d %H:%M:%S')}'>"
                f"⟳ File updated {_format_relative(latest)}</div>",
                unsafe_allow_html=True,
            )

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
        st.Page("pages/9_📋_Delivery_Detailed.py",   title="Delivery Detailed",  icon="📋"),
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
