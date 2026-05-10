"""Project Detailed — full column-level P&L breakdown for a single project,
broken down by week or month. Optional client filter within the chosen project.

Mirrors pages/9_📋_Delivery_Detailed.py but scopes by (Project, optional Client)
instead of (Client). Same revenue/cost component breakout, same TOTAL row,
same PoP table, same CSV download. Two intentional differences:

  - Uses idr_col / vol_col / pct_col column_config (so columns stay sortable
    on the underlying numeric values) instead of pre-formatted Styler strings.
  - Adds two stacked-bar charts at the bottom showing revenue and cost
    components composed over time.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   period_selector, MONTH_ORDER,
                   apply_chart_theme, idr_col, vol_col, pct_col,
                   dataframe_with_freeze)
from data_loader import REVENUE_COLS, COST_COLS

st.set_page_config(page_title="Project Detailed | Blitz", page_icon="📋", layout="wide")
st.title("📋 Project — Detailed Breakdown")
st.caption("Full column-level detail per project, broken down by week or month. "
           "Optional client filter within the selected project.")

df_full = require_data()

if 'Project' not in df_full.columns:
    st.error("'Project' column missing from delivery data.")
    st.stop()

# Keep only rows with a non-blank Project label (matches By Project page logic)
df_full = df_full[
    df_full['Project'].notna()
    & (df_full['Project'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No rows with a project label found.")
    st.stop()

# Standard delivery sidebar filters (Year / Blitz Team / Month / Client Level / SLA Type)
df = sidebar_filters(df_full, page_key="project_detailed")

if df.empty:
    st.warning("No data matches the current sidebar filters.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────
projects = sorted(df['Project'].dropna().unique().tolist())
if not projects:
    st.warning("No projects available under current filters.")
    st.stop()

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    sel_project = st.selectbox("Select Project", projects, key="pd_project")
# Clients within the selected project (computed after sel_project is set)
clients_in_proj = sorted(
    df[df['Project'] == sel_project]['Client Name'].dropna().unique().tolist()
)
with c2:
    sel_client = st.selectbox(
        "Client filter",
        ["(All clients)"] + clients_in_proj,
        key="pd_client",
    )
with c3:
    view_mode = period_selector(page_key="project_detailed", label="Period")

# Apply project (and optional client) filter
df = df[df['Project'] == sel_project]
if sel_client != "(All clients)":
    df = df[df['Client Name'] == sel_client]

if df.empty:
    st.warning("No data for the selected project / client combination.")
    st.stop()

# ── Define columns to display ─────────────────────────────────────────────────
rev_cols  = [c for c in REVENUE_COLS if c in df.columns and c != 'Total Revenue']
cost_cols = [c for c in COST_COLS    if c in df.columns and c != 'Total Cost']
# Derived metrics are recomputed from aggregated numerics post-groupby
derived_cols = ['GP', 'GP Margin %', 'TRPO']

# ── Aggregate by period ───────────────────────────────────────────────────────
group_cols = ['Year', 'Week (by Year)'] if view_mode == "Weekly" else ['Year', 'Month']

numeric_cols = ['Delivery Volume'] + rev_cols + ['Total Revenue'] + cost_cols + ['Total Cost']
numeric_cols = [c for c in numeric_cols if c in df.columns]

agg_dict = {c: 'sum' for c in numeric_cols}
if 'Date Range' in df.columns:
    agg_dict['Date Range'] = 'first'

agg_df = df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()

# Recompute derived metrics on aggregated rows — ratios must come from sums,
# not the average of per-row ratios
agg_df['GP'] = agg_df['Total Revenue'] - agg_df['Total Cost']
agg_df['GP Margin %'] = np.where(
    agg_df['Total Revenue'] != 0,
    agg_df['GP'] / agg_df['Total Revenue'] * 100, 0
)
vol = agg_df['Delivery Volume'].replace(0, np.nan)
agg_df['TRPO'] = (agg_df['Total Revenue'] / vol).fillna(0)

# Sort and label. Pandas 3.0+ uses pyarrow-backed strings by default which
# don't always concat cleanly with regular Python strings — explicit
# .astype(str) on every operand keeps the operation in plain object/str dtype.
if view_mode == "Weekly":
    agg_df = agg_df.sort_values(['Year', 'Week (by Year)'])
    agg_df['Period'] = (
        agg_df['Year'].astype(str)
        + ' W'
        + agg_df['Week (by Year)'].astype(int).astype(str)
    )
    if 'Date Range' in agg_df.columns:
        agg_df['Period'] = (
            agg_df['Period'].astype(str)
            + ' ('
            + agg_df['Date Range'].fillna('').astype(str)
            + ')'
        )
else:
    agg_df['Month'] = pd.Categorical(agg_df['Month'], categories=MONTH_ORDER, ordered=True)
    agg_df = agg_df.sort_values(['Year', 'Month'])
    agg_df['Period'] = agg_df['Year'].astype(str) + ' ' + agg_df['Month'].astype(str)

# ── Build display table ───────────────────────────────────────────────────────
display_cols = ['Delivery Volume'] + rev_cols + ['Total Revenue'] + cost_cols + ['Total Cost'] + derived_cols
display_cols = [c for c in display_cols if c in agg_df.columns]

result = agg_df[['Period'] + display_cols].copy()

# Grand TOTAL row — sum the financials, recompute the ratio columns from the
# summed totals (NOT sum-of-per-period-ratios, which would be meaningless).
total_row = {'Period': 'TOTAL'}
_ratio_cols = {'GP Margin %', 'TRPO'}
for c in display_cols:
    if c not in _ratio_cols:
        total_row[c] = result[c].sum()
if total_row.get('Total Revenue', 0) != 0:
    total_row['GP Margin %'] = total_row.get('GP', 0) / total_row['Total Revenue'] * 100
else:
    total_row['GP Margin %'] = 0
total_vol = total_row.get('Delivery Volume', 0) or 0
total_row['TRPO'] = (total_row.get('Total Revenue', 0) / total_vol) if total_vol else 0

result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

# ── Display ───────────────────────────────────────────────────────────────────
title_suffix = sel_project if sel_client == "(All clients)" else f"{sel_project} → {sel_client}"
st.subheader(f"{view_mode} Breakdown — {title_suffix}")

# column_config — keeps numeric sort working. idr_col auto-tags headers (Rp),
# vol_col gives localized integers, pct_col formats percentages.
col_cfg: dict = {}
for c in display_cols:
    if c == 'Delivery Volume':
        col_cfg[c] = vol_col('Delivery Volume')
    elif c == 'GP Margin %':
        col_cfg[c] = pct_col('GP Margin %', signed=False)
    else:
        # All revenue components, cost components, totals, GP, and TRPO are IDR
        col_cfg[c] = idr_col(c)

dataframe_with_freeze(
    result,
    key="project_detail_pivot",
    default_freeze=['Period'],
    column_config=col_cfg,
    width="stretch", hide_index=True, height=600,
)

# ── Period-over-Period % change ──────────────────────────────────────────────
st.divider()
st.subheader("Period-over-Period % Change")

pop_metrics = ['Delivery Volume', 'Total Revenue', 'Total Cost', 'GP', 'GP Margin %']
pop_metrics = [c for c in pop_metrics if c in agg_df.columns]

pop_df = agg_df[['Period'] + pop_metrics].copy()
pop_out_cols: list[str] = []
for c in pop_metrics:
    if c == 'GP Margin %':
        # pp delta, not pct change — % of % is confusing
        out = f'{c} Δ pp'
        pop_df[out] = pop_df[c].diff()
    else:
        out = f'{c} PoP%'
        pop_df[out] = pop_df[c].pct_change() * 100
    pop_out_cols.append(out)

pop_display = pop_df[['Period'] + pop_out_cols].copy()
pop_cfg = {c: pct_col(c, signed=True) for c in pop_out_cols}

dataframe_with_freeze(
    pop_display,
    key="project_detail_pop",
    default_freeze=['Period'],
    column_config=pop_cfg,
    width="stretch", hide_index=True,
)

# ── Composition charts: revenue + cost components stacked over time ──────────
st.divider()
st.subheader("Composition over time")

if rev_cols:
    trend_long_rev = agg_df[['Period'] + rev_cols].melt(
        id_vars='Period', var_name='Component', value_name='Amount'
    )
    trend_long_rev = trend_long_rev[trend_long_rev['Amount'] != 0]
    if not trend_long_rev.empty:
        fig_rev = px.bar(
            trend_long_rev, x='Period', y='Amount', color='Component',
            height=420, labels={'Amount': 'IDR', 'Period': ''},
            title=f"Revenue components — {title_suffix}",
        )
        fig_rev.update_layout(barmode='stack', xaxis_tickangle=-45)
        apply_chart_theme(fig_rev)
        st.plotly_chart(fig_rev, width="stretch")

if cost_cols:
    trend_long_cost = agg_df[['Period'] + cost_cols].melt(
        id_vars='Period', var_name='Component', value_name='Amount'
    )
    trend_long_cost = trend_long_cost[trend_long_cost['Amount'] != 0]
    if not trend_long_cost.empty:
        fig_cost = px.bar(
            trend_long_cost, x='Period', y='Amount', color='Component',
            height=420, labels={'Amount': 'IDR', 'Period': ''},
            title=f"Cost components — {title_suffix}",
        )
        fig_cost.update_layout(barmode='stack', xaxis_tickangle=-45)
        apply_chart_theme(fig_cost)
        st.plotly_chart(fig_cost, width="stretch")

# ── CSV download ──────────────────────────────────────────────────────────────
st.divider()
proj_slug   = sel_project.replace(' ', '_').replace('/', '-')
client_slug = (sel_client.replace(' ', '_').replace('/', '-')
               if sel_client != "(All clients)" else "all")
csv_data = result.to_csv(index=False)
st.download_button(
    "📥 Download as CSV",
    data=csv_data,
    file_name=f"project_detailed_{proj_slug}_{client_slug}_{view_mode.lower()}.csv",
    mime="text/csv",
)
