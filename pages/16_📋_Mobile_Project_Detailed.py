"""Mobile Project Detailed — full column-level mobile P&L for a single project,
broken down by week or month. Optional client filter within the chosen project.

Surfaces the Spec 4 reconciled metrics (Delivery PV, Delivery PnL %, EV PV,
EV PnL %, Total PV, Mobile Profit) as primary columns. The legacy high-level
rollup (Profit Calc, Profit Margin %, Blitz Revenue/Margin) is kept rightmost
for continuity but it excludes rider/manpower/claim/storing costs and so
disagrees with the PV-based metrics — caption above the table reminds readers.

The two PnL % columns are NEVER summed — they're recomputed from the
post-groupby `_delivery_pv_base` / `_ev_pv_base` columns added by
load_mobile_data, both for per-period rows and the TOTAL row.

Mirrors pages/16_📋_Mobile_Detailed.py but scopes by (Project, optional Client)
and uses idr_col / vol_col / pct_col column_config instead of Styler.format
so financial columns stay sortable on numeric values.
"""
import streamlit as st
import pandas as pd
import numpy as np
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   period_selector, MONTH_ORDER,
                   apply_chart_theme, idr_col, vol_col, pct_col,
                   dataframe_with_freeze)
from data_loader import (MOBILE_REVENUE_COLS, MOBILE_COST_COLS,
                         MOBILE_OPS_COLS)

st.set_page_config(page_title="Mobile Project Detailed | Blitz", page_icon="📋", layout="wide")
st.title("📋 Mobile Project — Detailed Breakdown")
st.caption("Full column-level mobile P&L per project. Surfaces the reconciled "
           "metrics (Delivery PV, EV PV, Total PV).")

df_full = require_mobile_data()

if 'Project' not in df_full.columns:
    st.error("'Project' column missing from mobile data.")
    st.stop()

# Keep only rows with a non-blank Project label
df_full = df_full[
    df_full['Project'].notna()
    & (df_full['Project'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No rows with a project label found.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────
projects = sorted(df_full['Project'].dropna().unique().tolist())
if not projects:
    st.warning("No projects available.")
    st.stop()

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    sel_project = st.selectbox("Select Project", projects, key="mpd_project")
clients_in_proj = sorted(
    df_full[df_full['Project'] == sel_project]['Client Name'].dropna().unique().tolist()
)
with c2:
    sel_client = st.selectbox(
        "Client filter",
        ["(All clients in project)"] + clients_in_proj,
        key="mpd_client",
    )
with c3:
    view_mode = period_selector(page_key="mobile_project_detailed", label="Period")

# Apply project (and optional client) filter
df = df_full[df_full['Project'] == sel_project].copy()
if sel_client != "(All clients in project)":
    df = df[df['Client Name'] == sel_client]

if df.empty:
    st.warning("No data for the selected project / client combination.")
    st.stop()

# ── Column groups ─────────────────────────────────────────────────────────────
rev_cols  = [c for c in MOBILE_REVENUE_COLS if c in df.columns]
cost_cols = [c for c in MOBILE_COST_COLS    if c in df.columns]
ops_cols  = [c for c in MOBILE_OPS_COLS     if c in df.columns]

# Spec 4 reconciled (primary)
spec4_pv_cols  = [c for c in ['Mobile Profit', 'Delivery PV', 'EV PV', 'Total PV']
                  if c in df.columns]
spec4_pct_cols = [c for c in ['Delivery PnL %', 'EV PnL %'] if c in df.columns]

# Legacy (demoted, rightmost)
legacy_cols = [c for c in ['Blitz Revenue', 'Gross Revenue', 'COGS',
                           'Total Cost (Mobile)', 'Profit Calc',
                           'Profit Margin %', 'Blitz Margin %']
               if c in df.columns]

# ── Aggregate by period ──────────────────────────────────────────────────────
group_cols = ['Year', 'Week (by Year)'] if view_mode == "Weekly" else ['Year', 'Month']

# Numeric cols summed through groupby. Includes the underscore-prefixed
# `_delivery_pv_base` / `_ev_pv_base` denominators so weighted PnL %
# recomputation works on the aggregated frame.
numeric_cols = ops_cols + rev_cols + cost_cols + spec4_pv_cols
for c in ('_delivery_pv_base', '_ev_pv_base'):
    if c in df.columns:
        numeric_cols.append(c)
numeric_cols = [c for c in numeric_cols if c in df.columns]

agg_dict = {c: 'sum' for c in numeric_cols}
if 'Date Range' in df.columns:
    agg_dict['Date Range'] = 'first'

agg_df = df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()


def _col(d: pd.DataFrame, name: str) -> pd.Series:
    """Return column if present, else a zero-filled Series of matching index."""
    return d[name] if name in d.columns else pd.Series(0, index=d.index)


# ── Recompute legacy derived metrics from aggregated numerics ────────────────
agg_df['Blitz Revenue']      = _col(agg_df, 'Total Revenue Sharing % (Weekly)')
agg_df['Gross Revenue']      = _col(agg_df, 'Total Revenue')
agg_df['COGS']               = _col(agg_df, 'Total Income Sales (Weekly)')
agg_df['Total Cost (Mobile)'] = agg_df['COGS'] + _col(agg_df, 'Total Operational Cost')
agg_df['Profit Calc']        = agg_df['Gross Revenue'] - agg_df['Total Cost (Mobile)']
agg_df['Profit Margin %']    = np.where(
    agg_df['Gross Revenue'] != 0,
    agg_df['Profit Calc'] / agg_df['Gross Revenue'] * 100, 0
)
agg_df['Blitz Margin %']     = np.where(
    agg_df['Blitz Revenue'] != 0,
    (agg_df['Blitz Revenue'] - agg_df['COGS']) / agg_df['Blitz Revenue'] * 100, 0
)

# ── Spec 4 weighted PnL % from base sums (NOT row-level avg) ─────────────────
if '_delivery_pv_base' in agg_df.columns and 'Delivery PV' in agg_df.columns:
    agg_df['Delivery PnL %'] = np.where(
        agg_df['_delivery_pv_base'] > 0,
        agg_df['Delivery PV'] / agg_df['_delivery_pv_base'] * 100, 0
    )
if '_ev_pv_base' in agg_df.columns and 'EV PV' in agg_df.columns:
    agg_df['EV PnL %'] = np.where(
        agg_df['_ev_pv_base'] > 0,
        agg_df['EV PV'] / agg_df['_ev_pv_base'] * 100, 0
    )
if 'Delivery PV' in agg_df.columns and 'EV PV' in agg_df.columns:
    agg_df['Total PV'] = agg_df['Delivery PV'].fillna(0) + agg_df['EV PV'].fillna(0)

# ── Per-driver derived metrics ───────────────────────────────────────────────
riders = _col(agg_df, 'Total Active Riders').replace(0, np.nan)
cups   = _col(agg_df, 'Total Cups Sold')
agg_df['Cups per Driver']    = (cups / riders).fillna(0)
agg_df['Revenue per Driver'] = (agg_df['Gross Revenue'] / riders).fillna(0)

# ── Sort and label periods ───────────────────────────────────────────────────
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

# ── Build display table ──────────────────────────────────────────────────────
# Order: ops → per-driver → revenue components → cost components → Spec 4
# (interleaved PV/PnL%) → legacy demoted (rightmost).
display_cols: list[str] = []
display_cols += ops_cols
display_cols += ['Cups per Driver', 'Revenue per Driver']
display_cols += rev_cols
display_cols += cost_cols
spec4_order = ['Mobile Profit', 'Delivery PV', 'Delivery PnL %',
               'EV PV', 'EV PnL %', 'Total PV']
display_cols += [c for c in spec4_order if c in agg_df.columns]
display_cols += legacy_cols

# Filter to columns that actually exist + dedupe preserving order
seen: set = set()
display_cols = [c for c in display_cols if c in agg_df.columns
                and not (c in seen or seen.add(c))]

result = agg_df[['Period'] + display_cols].copy()

# ── Grand TOTAL row — sum financials, recompute ratio columns from sums ─────
total_row: dict = {'Period': 'TOTAL'}
_ratio_cols = {'Profit Margin %', 'Blitz Margin %', 'Delivery PnL %', 'EV PnL %',
               'Cups per Driver', 'Revenue per Driver'}
for c in display_cols:
    if c not in _ratio_cols:
        total_row[c] = result[c].sum()

# Legacy ratios from totals
gr = total_row.get('Gross Revenue', 0)
total_row['Profit Margin %'] = (
    total_row.get('Profit Calc', 0) / gr * 100 if gr else 0
)
br = total_row.get('Blitz Revenue', 0)
total_row['Blitz Margin %'] = (
    (br - total_row.get('COGS', 0)) / br * 100 if br else 0
)
total_riders = total_row.get('Total Active Riders', 0) or 0
total_cups   = total_row.get('Total Cups Sold', 0) or 0
total_row['Cups per Driver']    = total_cups / total_riders if total_riders else 0
total_row['Revenue per Driver'] = gr / total_riders if total_riders else 0

# Spec 4: weighted PnL % for TOTAL row from base sums on agg_df
# (the base columns are underscore-prefixed and not in display_cols).
_dbase = agg_df['_delivery_pv_base'].sum() if '_delivery_pv_base' in agg_df.columns else 0
_ebase = agg_df['_ev_pv_base'].sum()       if '_ev_pv_base'       in agg_df.columns else 0
if 'Delivery PnL %' in display_cols:
    total_row['Delivery PnL %'] = (
        total_row.get('Delivery PV', 0) / _dbase * 100 if _dbase else 0
    )
if 'EV PnL %' in display_cols:
    total_row['EV PnL %'] = (
        total_row.get('EV PV', 0) / _ebase * 100 if _ebase else 0
    )

result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

# ── Display ──────────────────────────────────────────────────────────────────
title_suffix = sel_project if sel_client == "(All clients in project)" \
                            else f"{sel_project} → {sel_client}"
st.subheader(f"{view_mode} Breakdown — {title_suffix}")

st.caption(
    "**Reading order:** operational metrics · revenue components · cost "
    "components · **Spec 4 reconciled metrics** (Delivery PV, EV PV, Total PV, "
    "Mobile Profit) · *legacy high-level rollup (Profit Calc / Profit Margin % "
    "/ Blitz Revenue & Margin) — excludes rider, manpower, claim, and storing "
    "costs; retained for continuity*."
)

# column_config — keeps numeric sort working
col_cfg: dict = {}
for c in display_cols:
    if c in ('Total Cups Sold', 'Total Active Riders'):
        col_cfg[c] = vol_col(c)
    elif c == 'Cups per Driver':
        col_cfg[c] = st.column_config.NumberColumn(c, format="%.1f")
    elif c in ('Profit Margin %', 'Blitz Margin %', 'Delivery PnL %', 'EV PnL %'):
        col_cfg[c] = pct_col(c, signed=False)
    else:
        # All revenue/cost components, Spec 4 PV cols, Mobile Profit,
        # Revenue per Driver, COGS, Total Cost (Mobile), Profit Calc — all IDR
        col_cfg[c] = idr_col(c)

dataframe_with_freeze(
    result,
    key="mobile_project_detail_pivot",
    default_freeze=['Period'],
    column_config=col_cfg,
    width="stretch", hide_index=True, height=600,
)

# ── PoP % Change ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("Period-over-Period % Change")

pop_metrics = [c for c in ('Total Cups Sold', 'Total Active Riders',
                           'Total PV', 'Mobile Profit')
               if c in agg_df.columns]

pop_df = agg_df[['Period'] + pop_metrics].copy()
pop_out_cols: list[str] = []
for c in pop_metrics:
    out = f'{c} PoP%'
    pop_df[out] = pop_df[c].pct_change() * 100
    pop_out_cols.append(out)

pop_display = pop_df[['Period'] + pop_out_cols].copy()
pop_cfg = {c: pct_col(c, signed=True) for c in pop_out_cols}

dataframe_with_freeze(
    pop_display,
    key="mobile_project_detail_pop",
    default_freeze=['Period'],
    column_config=pop_cfg,
    width="stretch", hide_index=True,
)

# ── CSV download ─────────────────────────────────────────────────────────────
st.divider()
proj_slug   = sel_project.replace(' ', '_').replace('/', '-')
client_slug = (sel_client.replace(' ', '_').replace('/', '-')
               if sel_client != "(All clients in project)" else "all")
csv_data = result.to_csv(index=False)
st.download_button(
    "📥 Download as CSV",
    data=csv_data,
    file_name=f"project_detailed_mobile_{proj_slug}_{client_slug}_{view_mode.lower()}.csv",
    mime="text/csv",
)
