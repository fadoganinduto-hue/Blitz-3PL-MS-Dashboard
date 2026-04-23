import streamlit as st
import pandas as pd
from utils import require_data

st.set_page_config(page_title="Action Items | Blitz", page_icon="📋", layout="wide")
st.title("📋 Action Items")
st.caption("Client management tracker — status, issues, and action items.")

require_data()  # Ensure main data is loaded

ai_available = (
    'action_items' in st.session_state
    and st.session_state['action_items'] is not None
    and not st.session_state['action_items'].empty
)

if not ai_available:
    st.info(
        "**This page requires the full Excel file.**\n\n"
        "The Action Items tab is a separate qualitative sheet that isn't part of Raw Data Source. "
        "To see client action items here, upload the complete workbook (with the 'Action Items' sheet included) instead of just the Raw Data Source export.\n\n"
        "All other pages (Overview, By Client, By Location, By Team, EV Rental, Finance Check) "
        "work fully from Raw Data Source alone."
    )
    st.stop()

ai_df = st.session_state['action_items'].copy()

# ── Clean up ──────────────────────────────────────────────────────────────────
first_col = ai_df.columns[0]
ai_df[first_col] = ai_df[first_col].ffill()
ai_df = ai_df.dropna(how='all').reset_index(drop=True)

col_names = ai_df.columns.tolist()
rename_map = {}
for i, col in enumerate(col_names):
    c = str(col).strip()
    if i == 0:                              rename_map[col] = 'Client'
    elif 'status' in c.lower() or i == 1:  rename_map[col] = 'Status'
    elif 'problem' in c.lower() or i == 2: rename_map[col] = 'Problems'
    elif 'action' in c.lower() or i == 3:  rename_map[col] = 'Action Items'
    elif 'add' in c.lower() or i == 4:     rename_map[col] = 'Notes'
    else:                                   rename_map[col] = col
ai_df = ai_df.rename(columns=rename_map)

# ── Sidebar filter ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    clients = sorted(ai_df['Client'].dropna().unique().tolist())
    sel_clients = st.multiselect("Client", clients, default=clients)

if sel_clients:
    ai_df = ai_df[ai_df['Client'].isin(sel_clients)]

# ── Status overview ───────────────────────────────────────────────────────────
st.subheader("Client Status Overview")
if 'Status' in ai_df.columns:
    stat_counts = ai_df.groupby('Client')['Status'].first().value_counts().reset_index()
    stat_counts.columns = ['Status', 'Count']
    st.dataframe(stat_counts, use_container_width=False, hide_index=True)

st.divider()

# ── Per-client detail ─────────────────────────────────────────────────────────
st.subheader("Client Detail")
for client, group in ai_df.groupby('Client', sort=False):
    with st.expander(f"**{client}**", expanded=False):
        display_cols = [c for c in ['Status', 'Problems', 'Action Items', 'Notes']
                        if c in group.columns]
        g_disp = group[display_cols].dropna(how='all').reset_index(drop=True)
        if not g_disp.empty:
            st.dataframe(g_disp, use_container_width=True, hide_index=True)
        else:
            st.caption("No detailed action items recorded.")

st.divider()
with st.expander("View raw table"):
    st.dataframe(ai_df, use_container_width=True, hide_index=True)
