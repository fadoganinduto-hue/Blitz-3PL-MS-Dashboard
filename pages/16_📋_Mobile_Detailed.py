import streamlit as st
import pandas as pd
import numpy as np
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   get_available_periods, MONTH_ORDER)
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
    view_mode = st.radio("Period", ["Weekly", "Monthly"], horizontal=True, key="md_view")
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
derived_cols = ['Blitz Revenue', 'Gross Revenue', 'COGS', 'Total Cost (Mobile)',
                'Profit Calc', 'Profit Margin %', 'Blitz Margin %']
derived_cols = [c for c in derived_cols if c in df.columns]

# ── Aggregate by period ───────────────────────────────────────────────────────
if view_mode == "Weekly":
    group_cols = ['Year', 'Week (by Year)']
else:
    group_cols = ['Year', 'Month']

numeric_cols = ops_cols + rev_cols + cost_cols
numeric_cols = [c for c in numeric_cols if c in df.columns]

# For aggregation: SUM riders across locations for a client in a given week
# (already de-duplicated for date splits in loader)
agg_dict = {c: 'sum' for c in numeric_cols}

if 'Date Range' in df.columns:
    agg_dict['Date Range'] = 'first'

agg_df = df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()

# Recalculate derived metrics
agg_df['Blitz Revenue'] = agg_df.get('Total Revenue Sharing % (Weekly)', pd.Series(0, index=agg_df.index))
agg_df['Gross Revenue'] = agg_df.get('Total Revenue', pd.Series(0, index=agg_df.index))
agg_df['COGS'] = agg_df.get('Total Income Sales (Weekly)', pd.Series(0, index=agg_df.index))
agg_df['Total Cost (Mobile)'] = agg_df['COGS'] + agg_df.get('Total Operational Cost', pd.Series(0, index=agg_df.index))
agg_df['Profit Calc'] = agg_df['Gross Revenue'] - agg_df['Total Cost (Mobile)']
agg_df['Profit Margin %'] = np.where(
    agg_df['Gross Revenue'] != 0,
    agg_df['Profit Calc'] / agg_df['Gross Revenue'] * 100, 0
)
agg_df['Blitz Margin %'] = np.where(
    agg_df['Blitz Revenue'] != 0,
    (agg_df['Blitz Revenue'] - agg_df['COGS']) / agg_df['Blitz Revenue'] * 100, 0
)

# Per-driver metrics
riders = agg_df.get('Total Active Riders', pd.Series(0, index=agg_df.index)).replace(0, np.nan)
cups = agg_df.get('Total Cups Sold', pd.Series(0, index=agg_df.index))
agg_df['Cups per Driver'] = (cups / riders).fillna(0)
agg_df['Revenue per Driver'] = (agg_df['Gross Revenue'] / riders).fillna(0)

# Sort and label
if view_mode == "Weekly":
    agg_df = agg_df.sort_values(['Year', 'Week (by Year)'])
    agg_df['Period'] = agg_df['Year'].astype(str) + ' W' + agg_df['Week (by Year)'].astype(int).astype(str)
    if 'Date Range' in agg_df.columns:
        agg_df['Period'] = agg_df['Period'] + ' (' + agg_df['Date Range'].fillna('') + ')'
else:
    agg_df['Month'] = pd.Categorical(agg_df['Month'], categories=MONTH_ORDER, ordered=True)
    agg_df = agg_df.sort_values(['Year', 'Month'])
    agg_df['Period'] = agg_df['Year'].astype(str) + ' ' + agg_df['Month'].astype(str)

# ── Build display table ───────────────────────────────────────────────────────
display_cols = (ops_cols + ['Cups per Driver', 'Revenue per Driver'] +
                rev_cols + cost_cols + derived_cols)
display_cols = [c for c in display_cols if c in agg_df.columns]

result = agg_df[['Period'] + display_cols].copy()

# Grand total
total_row = {'Period': 'TOTAL'}
for c in display_cols:
    if c in ['Profit Margin %', 'Blitz Margin %', 'Cups per Driver', 'Revenue per Driver']:
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

result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

# ── Display ───────────────────────────────────────────────────────────────────
st.subheader(f"{'Weekly' if view_mode == 'Weekly' else 'Monthly'} Breakdown — {sel_client}")

format_dict = {}
for c in display_cols:
    if c in ['Profit Margin %', 'Blitz Margin %']:
        format_dict[c] = '{:.1f}%'
    elif c in ['Total Active Riders', 'Total Cups Sold']:
        format_dict[c] = '{:,.0f}'
    elif c in ['Cups per Driver']:
        format_dict[c] = '{:,.1f}'
    elif c in ['Revenue per Driver']:
        format_dict[c] = 'Rp {:,.0f}'
    else:
        format_dict[c] = 'Rp {:,.0f}'

st.dataframe(
    result.style.format(format_dict, na_rep='-'),
    use_container_width=True, hide_index=True, height=600
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

st.dataframe(
    pop_display.style.format({c: '{:+.1f}%' for c in pop_display.columns if '%Δ' in c}, na_rep='—')
                     .map(color_pop, subset=[c for c in pop_display.columns if '%Δ' in c]),
    use_container_width=True, hide_index=True
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
