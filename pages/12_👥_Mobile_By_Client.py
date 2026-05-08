import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   selected_period_df, selected_period_info, period_picker,
                   pop_pct, pop_label, period_selector, build_mobile_trend,
                   apply_chart_theme, idr_col, vol_col, pct_col,
                   dataframe_with_freeze)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile By Client | Blitz", page_icon="👥", layout="wide")
st.title("👥 Mobile Sellers — By Client")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

_pc1, _pc2 = st.columns([1, 2])
with _pc1:
    view_mode = period_selector(page_key="mobile_client")
with _pc2:
    period_picker(df_full, view_mode, page_key="mobile_client")
pop_lbl = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
curr_yr, curr_p, curr_lbl = selected_period_info(df_full, view_mode, page_key="mobile_client")
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = selected_period_df(df_full, view_mode, page_key="mobile_client")
prev_df = filter_period(df_full, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

st.caption(f"Latest period: {curr_lbl}")

# ── Ranked table ────────────────────────────────────────────────────────────────
st.subheader("Client Rankings")

agg_curr = mobile_aggregate(curr_df, ['Client Name'])
agg_prev = mobile_aggregate(prev_df, ['Client Name']) if not prev_df.empty else pd.DataFrame()

if not agg_prev.empty:
    merged = agg_curr.merge(agg_prev, on='Client Name', how='left', suffixes=('', '_prev')).fillna(0)
    merged['PoP%'] = merged.apply(
        lambda r: pop_pct(r['Profit Calc'], r.get('Profit Calc_prev', 0)) if r.get('Profit Calc_prev', 0) != 0 else None,
        axis=1
    )
else:
    merged = agg_curr.copy()
    merged['PoP%'] = None

# Calculate per-driver metrics
import numpy as np
merged['Cups per Driver'] = np.where(
    merged['Total Active Riders'] > 0,
    merged['Total Cups Sold'] / merged['Total Active Riders'], 0
)
merged['Rev per Driver'] = np.where(
    merged['Total Active Riders'] > 0,
    merged['Gross Revenue'] / merged['Total Active Riders'], 0
)

# ── Spec 4: weighted-correct Delivery PnL % / EV PnL % from base sums ──
# Row-level percentages can't be summed; reconstitute from sum(PV)/sum(base).
if '_delivery_pv_base' in merged.columns:
    merged['Delivery PnL %'] = np.where(
        merged['_delivery_pv_base'] > 0,
        merged['Delivery PV'] / merged['_delivery_pv_base'] * 100, 0
    )
else:
    merged['Delivery PnL %'] = 0
if '_ev_pv_base' in merged.columns:
    merged['EV PnL %'] = np.where(
        merged['_ev_pv_base'] > 0,
        merged['EV PV'] / merged['_ev_pv_base'] * 100, 0
    )
else:
    merged['EV PnL %'] = 0

display = merged[['Client Name', 'Total Cups Sold', 'Total Active Riders',
                  'Cups per Driver', 'Rev per Driver',
                  'Delivery PV', 'Delivery PnL %', 'EV PV', 'EV PnL %', 'Total PV',
                  'Gross Revenue', 'Blitz Revenue', 'Profit Calc', 'PoP%']].copy()
display.columns = ['Client', 'Cups', 'Riders', 'Cups/Driver', 'Rev/Driver',
                   'Delivery PV', 'Delivery PnL %', 'EV PV', 'EV PnL %', 'Total PV',
                   'Gross Revenue', 'Blitz Revenue', 'Profit', 'PoP%']

st.caption(
    "Sortable by any column. Default sort: **Total PV** (Spec 4 reconciled metric). "
    "**Profit / PoP%** are the legacy high-level rollup — kept rightmost for continuity "
    "but exclude rider/manpower/claim/storing costs."
)

dataframe_with_freeze(
    display.sort_values('Total PV', ascending=False),
    key="mobile_client_rankings",
    default_freeze=['Client'],
    column_config={
        'Cups':            vol_col('Cups'),
        'Riders':          vol_col('Riders'),
        'Cups/Driver':     st.column_config.NumberColumn('Cups/Driver', format="%.1f"),
        'Rev/Driver':      idr_col('Rev/Driver'),
        'Delivery PV':     idr_col('Delivery PV'),
        'Delivery PnL %':  pct_col('Delivery PnL %', signed=False),
        'EV PV':           idr_col('EV PV'),
        'EV PnL %':        pct_col('EV PnL %', signed=False),
        'Total PV':        idr_col('Total PV'),
        'Gross Revenue':   idr_col('Gross Revenue'),
        'Blitz Revenue':   idr_col('Blitz Revenue'),
        'Profit':          idr_col('Profit'),
        'PoP%':            pct_col('PoP%', signed=True),
    },
    width="stretch", hide_index=True,
)

st.divider()

# ── Top 10 Profit bar chart ─────────────────────────────────────────────────────
st.subheader("Top 10 Clients by Profit")
top_profit = merged.nlargest(10, 'Profit Calc')[['Client Name', 'Profit Calc']]
fig_profit = px.bar(top_profit, y='Client Name', x='Profit Calc', orientation='h',
                    color='Profit Calc', color_continuous_scale='greens',
                    height=380,
                    labels={'Profit Calc': 'Profit (IDR)'})
fig_profit.update_layout(yaxis={'categoryorder': 'total ascending'})
apply_chart_theme(fig_profit)
st.plotly_chart(fig_profit, width="stretch")

st.divider()

# ── Blitz Revenue pie chart ─────────────────────────────────────────────────────
st.subheader("Blitz Revenue Mix")
brev_dist = merged[['Client Name', 'Blitz Revenue']].copy()
brev_dist = brev_dist.sort_values('Blitz Revenue', ascending=False)
top15 = brev_dist.head(15)
others = brev_dist.iloc[15:]['Blitz Revenue'].sum()
if others > 0:
    top15 = pd.concat([top15, pd.DataFrame([{'Client Name': 'Others', 'Blitz Revenue': others}])], ignore_index=True)

fig_pie = px.pie(top15, values='Blitz Revenue', names='Client Name', hole=0.4,
                 height=420)
fig_pie.update_traces(textposition='inside', textinfo='percent+label')
apply_chart_theme(fig_pie)
st.plotly_chart(fig_pie, width="stretch")

st.divider()

# ── Drilldown: single client 12-period trend ────────────────────────────────────
st.subheader("Single Client — 12-Period Trend")
all_clients = sorted(df_full['Client Name'].dropna().unique())
sel_client = st.selectbox("Select Client", all_clients, key="mobile_client_drill")

cdf = df_full[df_full['Client Name'] == sel_client]
if not cdf.empty:
    trend_client = build_mobile_trend(cdf, [], view_mode)
    trend_12 = trend_client.tail(12)

    fig_drill = px.bar(trend_12, x='Label', y='Profit', color='Profit',
                       color_continuous_scale='blues', height=380,
                       labels={'Profit': 'Profit (IDR)', 'Label': 'Period'})
    fig_drill.update_layout(xaxis_tickangle=-45)
    apply_chart_theme(fig_drill)
    st.plotly_chart(fig_drill, width="stretch")
