import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_mobile_trend)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile Overview | Blitz", page_icon="📱", layout="wide")
st.title("📱 Mobile Sellers Overview")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mobile_overview_view")
pop = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df_full, view_mode, curr_yr, curr_p)
prev_df = filter_period(df_full, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()
prev_lbl = prev_info[2] if prev_info else "—"

if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")

def period_kpi(curr, prev, col):
    if col == 'Total Active Riders':
        cv = curr[col].max() if not curr.empty else 0
        pv = prev[col].max() if not prev.empty else 0
    else:
        cv = curr[col].sum() if not curr.empty else 0
        pv = prev[col].sum() if not prev.empty else 0
    return cv, pop_pct(cv, pv)

c1, c2, c3, c4, c5, c6 = st.columns(6)
cups_v, cups_p = period_kpi(curr_df, prev_df, 'Total Cups Sold')
grev_v, grev_p = period_kpi(curr_df, prev_df, 'Gross Revenue')
brev_v, brev_p = period_kpi(curr_df, prev_df, 'Blitz Revenue')
cost_v, cost_p = period_kpi(curr_df, prev_df, 'Total Cost (Mobile)')
profit_v = (curr_df['Gross Revenue'] - curr_df['Total Income Sales (Weekly)'] - curr_df['Total Operational Cost']).sum()
profit_pv = (prev_df['Gross Revenue'] - prev_df['Total Income Sales (Weekly)'] - prev_df['Total Operational Cost']).sum() if not prev_df.empty else 0
profit_p = pop_pct(profit_v, profit_pv)
riders_v, riders_p = period_kpi(curr_df, prev_df, 'Total Active Riders')
margin_v = profit_v / grev_v * 100 if grev_v > 0 else 0
margin_pv = profit_pv / (prev_df['Gross Revenue'].sum() if not prev_df.empty else 1) * 100 if not prev_df.empty else 0
margin_p = margin_v - margin_pv if not prev_df.empty else None

c1.metric("Cups Sold", fmt_vol(cups_v), f"{cups_p:+.1f}% {pop}" if cups_p is not None else None)
c2.metric("Gross Revenue", fmt_idr(grev_v), f"{grev_p:+.1f}% {pop}" if grev_p is not None else None)
c3.metric("Blitz Revenue", fmt_idr(brev_v), f"{brev_p:+.1f}% {pop}" if brev_p is not None else None)
c4.metric("Total Cost", fmt_idr(cost_v), f"{cost_p:+.1f}% {pop}" if cost_p is not None else None, delta_color="inverse")
c5.metric("Profit", fmt_idr(profit_v), f"{profit_p:+.1f}% {pop}" if profit_p is not None else None)
c6.metric("Profit Margin %", fmt_pct(margin_v), f"{margin_p:+.1f}pp {pop}" if margin_p is not None else None)

st.divider()

# ── Trend ───────────────────────────────────────────────────────────────────────
st.subheader("Trend (Last 13 Periods)")
trend = build_mobile_trend(df_full, [], view_mode)
trend_recent = trend.tail(13)

tab_pl, tab_vol = st.tabs(["Profit + Volume", "Revenue & Cost"])

with tab_pl:
    fig = go.Figure()
    fig.add_bar(x=trend_recent['Label'], y=trend_recent['Profit'], name='Profit',
                marker_color=C_GP, opacity=0.8, yaxis='y')
    fig.add_scatter(x=trend_recent['Label'], y=trend_recent['Cups'], mode='lines+markers', name='Cups',
                    line=dict(color=C_VOLUME, width=2), yaxis='y2')
    fig.update_layout(
        barmode='overlay', hovermode='x unified', template='plotly_white',
        height=400, legend=dict(orientation='h', y=1.05),
        yaxis_title='Profit (IDR)', yaxis2=dict(title='Cups Sold', overlaying='y', side='right'),
        xaxis_tickangle=-45
    )
    st.plotly_chart(fig, use_container_width=True)

with tab_vol:
    fig = go.Figure()
    fig.add_bar(x=trend_recent['Label'], y=trend_recent['GrossRevenue'], name='Gross Revenue',
                marker_color=C_REVENUE, opacity=0.8)
    fig.add_bar(x=trend_recent['Label'], y=trend_recent['Profit'], name='Profit',
                marker_color=C_GP, opacity=0.8)
    fig.update_layout(
        barmode='group', hovermode='x unified', template='plotly_white',
        height=400, legend=dict(orientation='h', y=1.05),
        yaxis_title='IDR', xaxis_tickangle=-45
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Top 10 clients by Blitz Revenue ─────────────────────────────────────────────
st.subheader("Top 10 Clients by Blitz Revenue")
client_rev = (
    df_full.groupby('Client Name', observed=True)['Blitz Revenue']
    .sum().reset_index().sort_values('Blitz Revenue', ascending=False).head(10)
)
fig_top = px.bar(client_rev, y='Client Name', x='Blitz Revenue', orientation='h',
                 color='Blitz Revenue', color_continuous_scale='blues',
                 template='plotly_white', height=400,
                 labels={'Blitz Revenue': 'Blitz Revenue (IDR)'})
fig_top.update_layout(yaxis={'categoryorder': 'total ascending'})
st.plotly_chart(fig_top, use_container_width=True)
