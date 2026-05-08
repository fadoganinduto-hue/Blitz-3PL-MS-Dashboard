import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   selected_period_df,
                   pop_pct, pop_label, period_selector, build_trend,
                   apply_chart_theme, idr_col, vol_col, pct_col,
                   dataframe_with_freeze)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="By Client | Blitz", page_icon="👥", layout="wide")
st.title("👥 By Client")
st.caption("Per-client P&L rankings, unit economics, and drilldown.")

df_full = require_data()
df = sidebar_filters(df_full, page_key="client")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode selector ───────────────────────────────────────────────────────
view_mode = period_selector(page_key="client")
pop = pop_label(view_mode)

periods   = get_available_periods(df, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = selected_period_df(df, view_mode, page_key="client")
prev_df = filter_period(df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()
prev_lbl = prev_info[2] if prev_info else "—"

# ── Latest period snapshot ────────────────────────────────────────────────────
if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week Snapshot — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month Snapshot — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")

lw_agg = (
    curr_df.groupby('Client Name', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
    .reset_index()
)
if not prev_df.empty:
    pw_agg = (
        prev_df.groupby('Client Name', observed=True)
        .agg(GP_prev=('GP', 'sum'), Revenue_prev=('Total Revenue', 'sum'))
        .reset_index()
    )
else:
    pw_agg = pd.DataFrame(columns=['Client Name', 'GP_prev', 'Revenue_prev'])

lw = lw_agg.merge(pw_agg, on='Client Name', how='left').fillna(0)
lw['GP Margin %'] = np.where(lw['Revenue'] != 0, lw['GP'] / lw['Revenue'] * 100, 0)
lw[f'GP {pop} %'] = lw.apply(lambda r: pop_pct(r['GP'], r['GP_prev']), axis=1)
lw = lw.sort_values('GP', ascending=False).reset_index(drop=True)

dataframe_with_freeze(
    lw[['Client Name', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %', f'GP {pop} %']],
    key="client_snapshot",
    default_freeze=['Client Name'],
    column_config={
        'Volume':         vol_col('Volume'),
        'Revenue':        idr_col('Revenue'),
        'Cost':           idr_col('Cost'),
        'GP':             idr_col('GP'),
        'GP Margin %':    pct_col('Margin', signed=False),
        f'GP {pop} %':    pct_col(f'GP {pop} %', signed=True),
    },
    width="stretch", hide_index=True, height=400,
)

st.divider()

# ── Period rankings ───────────────────────────────────────────────────────────
st.subheader("Period Rankings (all filtered data)")
sort_col = st.selectbox("Sort by", ['GP', 'Revenue', 'Volume', 'GP Margin %'], index=0)

client_agg = (
    df.groupby('Client Name', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
    .reset_index()
)
client_agg['GP Margin %'] = np.where(
    client_agg['Revenue'] != 0, client_agg['GP'] / client_agg['Revenue'] * 100, 0
)
client_agg = client_agg.sort_values(sort_col, ascending=False).reset_index(drop=True)

dataframe_with_freeze(
    client_agg[['Client Name', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %']],
    key="client_rankings",
    default_freeze=['Client Name'],
    column_config={
        'Volume':      vol_col('Volume'),
        'Revenue':     idr_col('Revenue'),
        'Cost':        idr_col('Cost'),
        'GP':          idr_col('GP'),
        'GP Margin %': pct_col('GP Margin %', signed=False),
    },
    width="stretch", hide_index=True,
)

st.divider()

# ── Client drilldown ──────────────────────────────────────────────────────────
st.subheader("Client Drilldown")
sel_client = st.selectbox("Select a client", sorted(df['Client Name'].dropna().unique()))
cdf = df[df['Client Name'] == sel_client].copy()

if cdf.empty:
    st.stop()

ck1, ck2, ck3, ck4 = st.columns(4)
ck1.metric("Revenue",  fmt_idr(cdf['Total Revenue'].sum()))
ck2.metric("Cost",     fmt_idr(cdf['Total Cost'].sum()))
ck3.metric("GP",       fmt_idr(cdf['GP'].sum()))
gpm = cdf['GP'].sum() / cdf['Total Revenue'].sum() * 100 if cdf['Total Revenue'].sum() else 0
ck4.metric("Margin",   fmt_pct(gpm))

# Trend + drilldown table (follows the same view_mode chosen at top)
trend_c = build_trend(cdf, [], view_mode)
trend_c['GP Margin %'] = np.where(
    trend_c['Revenue'] != 0, trend_c['GP'] / trend_c['Revenue'] * 100, 0
)
for m in ['Revenue', 'GP', 'Volume']:
    trend_c[f'{m} PoP%'] = trend_c[m].pct_change() * 100

fig = go.Figure()
fig.add_bar(x=trend_c['Label'], y=trend_c['Revenue'], name='Revenue',
            marker_color=C_REVENUE, opacity=0.8)
fig.add_bar(x=trend_c['Label'], y=trend_c['Cost'],    name='Cost',
            marker_color=C_COST, opacity=0.8)
fig.add_scatter(x=trend_c['Label'], y=trend_c['GP'], mode='lines+markers',
                name='GP', line=dict(color=C_GP, width=2))
fig.update_layout(barmode='group', height=400, yaxis_title='IDR',
                  xaxis_tickangle=-45, title=f"{sel_client} — {view_mode} P&L")
apply_chart_theme(fig)
st.plotly_chart(fig, width="stretch")

dataframe_with_freeze(
    trend_c[['Label', 'Volume', 'Volume PoP%', 'Revenue', 'Revenue PoP%',
             'Cost', 'GP', 'GP PoP%', 'GP Margin %']],
    key="client_drilldown_trend",
    default_freeze=['Label'],
    column_config={
        'Label':        st.column_config.TextColumn('Period'),
        'Volume':       vol_col('Volume'),
        'Volume PoP%':  pct_col('Vol PoP%', signed=True),
        'Revenue':      idr_col('Revenue'),
        'Revenue PoP%': pct_col('Rev PoP%', signed=True),
        'Cost':         idr_col('Cost'),
        'GP':           idr_col('GP'),
        'GP PoP%':      pct_col('GP PoP%', signed=True),
        'GP Margin %':  pct_col('Margin', signed=False),
    },
    width="stretch", hide_index=True,
)

# Cost structure pie
cost_data = {label: cdf[col].sum() for col, label in COST_COMPONENTS.items()
             if col in cdf.columns and cdf[col].sum() > 0}
if cost_data:
    cost_df = pd.DataFrame({'Component': list(cost_data.keys()), 'Amount': list(cost_data.values())})
    fig_cost = px.pie(cost_df, values='Amount', names='Component', hole=0.35,
                      height=360,
                      title=f"{sel_client} — Cost Structure")
    apply_chart_theme(fig_cost)
    st.plotly_chart(fig_cost, width="stretch")
