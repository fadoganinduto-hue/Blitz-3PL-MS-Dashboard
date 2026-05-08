import streamlit as st
import pandas as pd
import numpy as np
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   get_available_periods, period_selector, MONTH_ORDER, dataframe_with_freeze)
from data_loader import MOBILE_REVENUE_COLS, MOBILE_COST_COLS, MOBILE_OPS_COLS, mobile_aggregate

st.set_page_config(page_title="Mobile Detailed | Blitz", page_icon="📋", layout="wide")
st.title("📋 Mobile Sellers — Detailed Breakdown")
st.caption("Full column-level detail per client, broken down by week or month.")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────
c1, c2 = st.columns([1, 2])
with c1:
    view_mode = period_selector(page_key="mobile_detail", label="Period")
with c2:
    clients = sorted(df_full['Client Name'].dropna().unique().tolist())
    sel_client = st.selectbox("Select Client", ["All Clients"] + clients, key="md_client")

df = df_full.copy()
if sel_client != "All Clients":
    df = df[df['Client Name'] == sel_client]

if df.empty:
    st.warning("No data for the selected client.")
    st.stop()

# ── Define columns ────────────────────────────────────────────────────────────
rev_cols = [c for c in MOBILE_REVENUE_COLS if c in df.columns]
cost_cols = [c for c in MOBILE_COST_COLS if c in df.columns]
ops_cols = [c for c in MOBILE_OPS_COLS if c in df.columns]
derived_cols = ['Delivery PV', 'Delivery PnL %', 'EV PV', 'EV PnL %', 'Total PV',
                'Mobile Profit',
                'Blitz Revenue', 'Gross Revenue', 'COGS', 'Total Cost (Mobile)',
                'Profit Calc', 'Profit Margin %', 'Blitz Margin %']
derived_cols = [c for c in derived_cols if c in df.columns]
# The two PnL % columns are the only ones in derived_cols that mustn't be
# treated as sum-able; their re-aggregation is handled below using the
# `_delivery_pv_base` / `_ev_pv_base` columns added by load_mobile_data.

# ── Aggregate by period ───────────────────────────────────────────────────────
if view_mode == "Weekly":
    group_cols = ['Year', 'Week (by Year)']
else:
    group_cols = ['Year', 'Month']

numeric_cols = ops_cols + rev_cols + cost_cols
# Spec 4 metrics need to roll up correctly through the groupby:
#   - Sum-able directly: Delivery PV, EV PV, Total PV, Mobile Profit
#   - Sum-able as denominators: _delivery_pv_base, _ev_pv_base
#   - PnL %s are recomputed from the summed base/PV pairs after groupby.
for c in ['Delivery PV', 'EV PV', 'Total PV', 'Mobile Profit',
          '_delivery_pv_base', '_ev_pv_base']:
    if c in df.columns and c not in numeric_cols:
        numeric_cols.append(c)
numeric_cols = [c for c in numeric_cols if c in df.columns]

# For aggregation: SUM riders across locations for a client in a given week
# (already de-duplicated for date splits in loader)
agg_dict = {c: 'sum' for c in numeric_cols}

if 'Date Range' in df.columns:
    agg_dict['Date Range'] = 'first'

agg_df = df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()

def _safe_col(df, col):
    """Return column series or zeros if column doesn't exist."""
    return df[col] if col in df.columns else pd.Series(0, index=df.index)

# Recalculate derived metrics
agg_df['Blitz Revenue'] = _safe_col(agg_df, 'Total Revenue Sharing % (Weekly)')
agg_df['Gross Revenue'] = _safe_col(agg_df, 'Total Revenue')
agg_df['COGS'] = _safe_col(agg_df, 'Total Income Sales (Weekly)')
agg_df['Total Cost (Mobile)'] = agg_df['COGS'] + _safe_col(agg_df, 'Total Operational Cost')
agg_df['Profit Calc'] = agg_df['Gross Revenue'] - agg_df['Total Cost (Mobile)']
agg_df['Profit Margin %'] = np.where(
    agg_df['Gross Revenue'] != 0,
    agg_df['Profit Calc'] / agg_df['Gross Revenue'] * 100, 0
)
agg_df['Blitz Margin %'] = np.where(
    agg_df['Blitz Revenue'] != 0,
    (agg_df['Blitz Revenue'] - agg_df['COGS']) / agg_df['Blitz Revenue'] * 100, 0
)

# Spec 4: Total PV is sum-able (already in agg_df via groupby). Recompute %s
# from the post-aggregation base sums.
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

# Per-driver metrics
riders = _safe_col(agg_df, 'Total Active Riders').replace(0, np.nan)
cups = _safe_col(agg_df, 'Total Cups Sold')
agg_df['Cups per Driver'] = (cups / riders).fillna(0)
agg_df['Revenue per Driver'] = (agg_df['Gross Revenue'] / riders).fillna(0)

# Sort and label.
# Note: pandas 3.0+ uses pyarrow-backed string arrays by default which don't
# always concat cleanly with regular Python strings — explicit .astype(str)
# on every operand keeps the operation in plain object/str dtype.
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
    agg_df['Period'] = (
        agg_df['Year'].astype(str)
        + ' '
        + agg_df['Month'].astype(str)
    )

# ── Build display table ───────────────────────────────────────────────────────
display_cols = (ops_cols + ['Cups per Driver', 'Revenue per Driver'] +
                rev_cols + cost_cols + derived_cols)
display_cols = [c for c in display_cols if c in agg_df.columns]

result = agg_df[['Period'] + display_cols].copy()

# Grand total
total_row = {'Period': 'TOTAL'}
_pct_cols = {'Profit Margin %', 'Blitz Margin %', 'Cups per Driver', 'Revenue per Driver',
             'Delivery PnL %', 'EV PnL %'}
for c in display_cols:
    if c in _pct_cols:
        pass
    else:
        total_row[c] = result[c].sum()
# Recalculate derived for total
gr = total_row.get('Gross Revenue', total_row.get('Total Revenue', 0))
if gr and gr != 0:
    total_row['Profit Margin %'] = total_row.get('Profit Calc', 0) / gr * 100
else:
    total_row['Profit Margin %'] = 0
br = total_row.get('Blitz Revenue', 0)
cogs = total_row.get('COGS', 0)
total_row['Blitz Margin %'] = ((br - cogs) / br * 100) if br else 0
total_riders = total_row.get('Total Active Riders', 0)
total_cups = total_row.get('Total Cups Sold', 0)
total_row['Cups per Driver'] = total_cups / total_riders if total_riders else 0
total_row['Revenue per Driver'] = gr / total_riders if total_riders else 0

# Spec 4: weighted-correct PnL % for the TOTAL row. Bases live on agg_df
# (they're underscore-prefixed and not in display_cols), so read them there.
_dbase = agg_df['_delivery_pv_base'].sum() if '_delivery_pv_base' in agg_df.columns else 0
_ebase = agg_df['_ev_pv_base'].sum() if '_ev_pv_base' in agg_df.columns else 0
if 'Delivery PnL %' in display_cols:
    total_row['Delivery PnL %'] = (total_row.get('Delivery PV', 0) / _dbase * 100) if _dbase else 0
if 'EV PnL %' in display_cols:
    total_row['EV PnL %'] = (total_row.get('EV PV', 0) / _ebase * 100) if _ebase else 0

result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

# ── Display ───────────────────────────────────────────────────────────────────
st.subheader(f"{'Weekly' if view_mode == 'Weekly' else 'Monthly'} Breakdown — {sel_client}")

format_dict = {}
for c in display_cols:
    if c in ['Profit Margin %', 'Blitz Margin %', 'Delivery PnL %', 'EV PnL %']:
        format_dict[c] = '{:.1f}%'
    elif c in ['Total Active Riders', 'Total Cups Sold']:
        format_dict[c] = '{:,.0f}'
    elif c in ['Cups per Driver']:
        format_dict[c] = '{:,.1f}'
    elif c in ['Revenue per Driver']:
        format_dict[c] = 'Rp {:,.0f}'
    else:
        format_dict[c] = 'Rp {:,.0f}'

dataframe_with_freeze(
    result.style.format(format_dict, na_rep='-'),
    key="mobile_detail_pivot",
    default_freeze=['Period'],
    width="stretch", hide_index=True, height=600,
)

# ── PoP % Change ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("Period-over-Period % Change")

pop_metrics = ['Total Cups Sold', 'Total Active Riders', 'Gross Revenue', 'Profit Calc']
pop_metrics = [c for c in pop_metrics if c in agg_df.columns]

pop_df = agg_df[['Period'] + pop_metrics].copy()
for c in pop_metrics:
    pop_df[f'{c} PoP%'] = pop_df[c].pct_change() * 100

pop_display = pop_df[['Period'] + [f'{c} PoP%' for c in pop_metrics]].copy()
pop_display.columns = ['Period'] + [f'{c} %Δ' for c in pop_metrics]

def color_pop(val):
    if pd.isna(val):
        return ''
    return 'color: green' if val > 0 else 'color: red' if val < 0 else ''

dataframe_with_freeze(
    pop_display.style.format({c: '{:+.1f}%' for c in pop_display.columns if '%Δ' in c}, na_rep='—')
                     .map(color_pop, subset=[c for c in pop_display.columns if '%Δ' in c]),
    key="mobile_detail_pop",
    default_freeze=['Period'],
    width="stretch", hide_index=True,
)

# ── Download ──────────────────────────────────────────────────────────────────
st.divider()
csv_data = result.to_csv(index=False)
st.download_button(
    "📥 Download as CSV",
    data=csv_data,
    file_name=f"mobile_detailed_{sel_client.replace(' ', '_')}_{view_mode.lower()}.csv",
    mime="text/csv"
)
