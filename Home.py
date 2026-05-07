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

from data_loader import (
    load_main_data,
    load_ev_data,
    load_action_items,
    load_mobile_data,
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

# ── Auto-load published data files from data/ folder ──────────────────────────
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"

LOADERS = [
    # Delivery file also yields ev_data + action_items from other sheets
    ("delivery_data", "delivery_latest.xlsx", load_main_data, [
        ("ev_data", load_ev_data),
        ("action_items", load_action_items),
    ]),
    ("mobile_data", "mobile_sellers_latest.xlsx", load_mobile_data, []),
]

for key, filename, loader, companions in LOADERS:
    fpath = DATA_DIR / filename
    if fpath.exists() and key not in st.session_state:
        try:
            with open(fpath, "rb") as f:
                file_bytes = f.read()
            st.session_state[key] = loader(file_bytes)
            for companion_key, companion_loader in companions:
                if companion_key not in st.session_state:
                    st.session_state[companion_key] = companion_loader(file_bytes)
        except Exception as exc:  # noqa: BLE001
            st.sidebar.error(f"Failed to load {filename}: {exc}")

# Backward-compat: legacy pages reference st.session_state['data']
if "delivery_data" in st.session_state and "data" not in st.session_state:
    st.session_state["data"] = st.session_state["delivery_data"]


# ── Build navigation ──────────────────────────────────────────────────────────
PAGES = {
    "Blitz Delivery": [
        st.Page("pages/1_📊_Overview.py",            title="Overview",           icon="📊", default=True),
        st.Page("pages/2_👥_By_Client.py",           title="By Client",          icon="👥"),
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
