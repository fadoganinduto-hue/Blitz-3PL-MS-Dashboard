import streamlit as st
import pandas as pd
import numpy as np
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   get_available_periods, MONTH_ORDER, dataframe_with_freeze)
from data_loader import REVENUE_COLS, COST_COLS

st.set_page_config(page_title="Delivery Detailed | Blitz", page_icon="📋", layout="wide")
st.title("📋 Delivery — Detailed Breakdown")
st.caption("Full column-level detail per client, broken down by week or month. Mirrors the 'Deets' pivot view.")

df_full = require_data()
df = sidebar_filters(df_full, page_key="del_detail")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────
c1, c2 = st.columns([1, 2])
with c1:
    view_mode = st.radio("Period", ["Weekly", "Monthly"], horizontal=True, key="dd_view")
with c2:
    clients = sorted(df['Client Name'].dropna().unique().tolist())
    sel_client = st.selectbox("Select Client", ["All Clients"] + clients, key="dd_client")

if sel_client != "All Clients":
    df = df[df['Client Name'] == sel_client]

if df.empty:
    st.warning("No data for the selected client.")
    st.stop()

# ── Define columns to display ─────────────────────────────────────────────────
# Revenue columns (present in data)
rev_cols = [c for c in REVENUE_COLS if c in df.columns and c != 'Total Revenue']
cost_cols = [c for c in COST_COLS if c in df.columns and c != 'Total Cost']
derived_cols = ['GP', 'GP Margin %', 'SRPO', 'RCPO', 'TCPO', 'TRPO']
derived_cols = [c for c in derived_cols if c in df.columns]

# ── Aggregate by period ───────────────────────────────────────────────────────
if view_mode == "Weekly":
    group_cols = ['Year', 'Week (by Year)']
else:
    group_cols = ['Year', 'Month']

numeric_cols = ['Delivery Volume'] + rev_cols + ['Total Revenue'] + cost_cols + ['Total Cost']
numeric_cols = [c for c in numeric_cols if c in df.columns]

# Aggregate: sum for financial, recalculate derived
agg_dict = {c: 'sum' for c in numeric_cols}
# Also get Date Range for weekly label
if 'Date Range' in df.columns:
    agg_dict['Date Range'] = 'first'

agg_df = df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()

# Recalculate derived metrics on aggregated data
agg_df['GP'] = agg_df['Total Revenue'] - agg_df['Total Cost']
agg_df['GP Margin %'] = np.where(
    agg_df['Total Revenue'] != 0,
    agg_df['GP'] / agg_df['Total Revenue'] * 100, 0
)
vol = agg_df['Delivery Volume'].replace(0, np.nan)
if 'Selling Price (Regular Rate)' in agg_df.columns:
    agg_df['SRPO'] = (agg_df['Selling Price (Regular Rate)'] / vol).fillna(0)
if 'Rider Cost' in agg_df.columns:
    agg_df['RCPO'] = (agg_df['Rider Cost'] / vol).fillna(0)
agg_df['TCPO'] = (agg_df['Total Cost'] / vol).fillna(0)
agg_df['TRPO'] = (agg_df['Total Revenue'] / vol).fillna(0)

# Add Rider Cost % of Revenue
if 'Rider Cost' in agg_df.columns:
    agg_df['Rider Cost % of Rev'] = np.where(
        agg_df['Total Revenue'] != 0,
        agg_df['Rider Cost'] / agg_df['Total Revenue'] * 100, 0
    )
    derived_cols = derived_cols + ['Rider Cost % of Rev']

# Sort
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
display_cols = ['Delivery Volume'] + rev_cols + ['Total Revenue'] + cost_cols + ['Total Cost'] + derived_cols
display_cols = [c for c in display_cols if c in agg_df.columns]

result = agg_df[['Period'] + display_cols].copy()

# Add Grand Total row
total_row = {'Period': 'TOTAL'}
for c in display_cols:
    if c in ['GP Margin %', 'SRPO', 'RCPO', 'TCPO', 'TRPO', 'Rider Cost % of Rev']:
        # Recalculate ratios from totals
        pass
    else:
        total_row[c] = result[c].sum()
# Recalculate derived for total
if total_row.get('Total Revenue', 0) != 0:
    total_row['GP Margin %'] = total_row.get('GP', 0) / total_row['Total Revenue'] * 100
else:
    total_row['GP Margin %'] = 0
total_vol = total_row.get('Delivery Volume', 0)
if total_vol and total_vol != 0:
    if 'SRPO' in display_cols:
        total_row['SRPO'] = total_row.get('Selling Price (Regular Rate)', 0) / total_vol
    if 'RCPO' in display_cols:
        total_row['RCPO'] = total_row.get('Rider Cost', 0) / total_vol
    if 'TCPO' in display_cols:
        total_row['TCPO'] = total_row.get('Total Cost', 0) / total_vol
    if 'TRPO' in display_cols:
        total_row['TRPO'] = total_row.get('Total Revenue', 0) / total_vol
if 'Rider Cost % of Rev' in display_cols and total_row.get('Total Revenue', 0) != 0:
    total_row['Rider Cost % of Rev'] = total_row.get('Rider Cost', 0) / total_row['Total Revenue'] * 100

total_df = pd.DataFrame([total_row])
result = pd.concat([result, total_df], ignore_index=True)

# ── Display ───────────────────────────────────────────────────────────────────
st.subheader(f"{'Weekly' if view_mode == 'Weekly' else 'Monthly'} Breakdown — {sel_client}")

# Format financial columns for display
format_dict = {}
for c in display_cols:
    if c in ['GP Margin %', 'Rider Cost % of Rev']:
        format_dict[c] = '{:.1f}%'
    elif c in ['SRPO', 'RCPO', 'TCPO', 'TRPO']:
        format_dict[c] = 'Rp {:,.0f}'
    elif c == 'Delivery Volume':
        format_dict[c] = '{:,.0f}'
    else:
        format_dict[c] = 'Rp {:,.0f}'

dataframe_with_freeze(
    result.style.format(format_dict, na_rep='-'),
    key="del_detail_pivot",
    default_freeze=['Period'],
    use_container_width=True, hide_index=True, height=600,
)

# ── PoP % Change table ───────────────────────────────────────────────────────
st.divider()
st.subheader(f"Period-over-Period % Change")

# Calculate PoP% for key metrics
pop_metrics = ['Delivery Volume', 'Total Revenue', 'Total Cost', 'GP']
pop_metrics = [c for c in pop_metrics if c in agg_df.columns]

pop_df = agg_df[['Period'] + pop_metrics].copy()
for c in pop_metrics:
    pop_df[f'{c} PoP%'] = pop_df[c].pct_change() * 100

pop_display = pop_df[['Period'] + [f'{c} PoP%' for c in pop_metrics]].copy()
pop_display.columns = ['Period'] + [f'{c} %Δ' for c in pop_metrics]

def color_pop(val):
    if pd.isna(val):
        return ''
    if val > 0:
        return 'color: green'
    elif val < 0:
        return 'color: red'
    return ''

dataframe_with_freeze(
    pop_display.style.format({c: '{:+.1f}%' for c in pop_display.columns if '%Δ' in c}, na_rep='—')
                     .map(color_pop, subset=[c for c in pop_display.columns if '%Δ' in c]),
    key="del_detail_pop",
    default_freeze=['Period'],
    use_container_width=True, hide_index=True,
)

# ── Download button ───────────────────────────────────────────────────────────
st.divider()
csv_data = result.to_csv(index=False)
st.download_button(
    "📥 Download as CSV",
    data=csv_data,
    file_name=f"delivery_detailed_{sel_client.replace(' ', '_')}_{view_mode.lower()}.csv",
    mime="text/csv"
)
