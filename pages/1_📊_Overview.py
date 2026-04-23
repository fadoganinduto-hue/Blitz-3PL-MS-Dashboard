import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_trend)

st.set_page_config(page_title="Overview | Blitz", page_icon="📊", layout="wide")
st.title("📊 Overview")

df_full = require_data()
df = sidebar_filters(df_full, page_key="overview")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode selector (drives ALL sections on this page) ────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="overview_view")
pop = pop_label(view_mode)

# Derive current and previous period
periods   = get_available_periods(df, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df, view_mode, curr_yr, curr_p)
prev_df = filter_period(df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

prev_lbl = prev_info[2] if prev_info else "—"

# ── Latest period banner ───────────────────────────────────────────────────────
if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")

def period_kpi(curr, prev, col):
    cv = curr[col].sum()
    pv = prev[col].sum() if not prev.empty else 0.0
    return cv, pop_pct(cv, pv)

c1, c2, c3, c4 = st.columns(4)
rev_v,  rev_p  = period_kpi(curr_df, prev_df, 'Total Revenue')
cost_v, cost_p = period_kpi(curr_df, prev_df, 'Total Cost')
vol_v,  vol_p  = period_kpi(curr_df, prev_df, 'Delivery Volume')
gp_v   = (curr_df['Total Revenue'] - curr_df['Total Cost']).sum()
gp_pv  = (prev_df['Total Revenue'] - prev_df['Total Cost']).sum() if not prev_df.empty else 0.0
gp_p   = pop_pct(gp_v, gp_pv)

c1.metric("Revenue",      fmt_idr(rev_v),  f"{rev_p:+.1f}% {pop}"  if rev_p  is not None else None)
c2.metric("Cost",         fmt_idr(cost_v), f"{cost_p:+.1f}% {pop}" if cost_p is not None else None,
          delta_color="inverse")
c3.metric("Gross Profit", fmt_idr(gp_v),   f"{gp_p:+.1f}% {pop}"   if gp_p   is not None else None)
c4.metric("Volume",       fmt_vol(vol_v),  f"{vol_p:+.1f}% {pop}"  if vol_p  is not None else None)

st.divider()

# ── Period Summary KPIs ────────────────────────────────────────────────────────
st.subheader("Period Summary (filtered)")
total_rev  = df['Total Revenue'].sum()
total_cost = df['Total Cost'].sum()
total_gp   = df['GP'].sum()
total_vol  = df['Delivery Volume'].sum()
gp_margin  = total_gp / total_rev * 100 if total_rev else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Revenue",  fmt_idr(total_rev))
k2.metric("Total Cost",     fmt_idr(total_cost))
k3.metric("Gross Profit",   fmt_idr(total_gp))
k4.metric("GP Margin",      fmt_pct(gp_margin))
k5.metric("Total Volume",   fmt_vol(total_vol))

st.divider()

# ── Trend charts ───────────────────────────────────────────────────────────────
st.subheader("Trend")
trend = build_trend(df, [], view_mode)

tab_pnl, tab_vol = st.tabs(["P&L", "Volume"])

with tab_pnl:
    fig = go.Figure()
    fig.add_bar(x=trend['Label'], y=trend['Revenue'], name='Revenue',
                marker_color=C_REVENUE, opacity=0.8)
    fig.add_bar(x=trend['Label'], y=trend['Cost'], name='Cost',
                marker_color=C_COST, opacity=0.8)
    fig.add_scatter(x=trend['Label'], y=trend['GP'], mode='lines+markers', name='GP',
                    line=dict(color=C_GP, width=2))
    fig.update_layout(barmode='group', hovermode='x unified', template='plotly_white',
                      height=400, legend=dict(orientation='h', y=1.05), yaxis_title='IDR',
                      xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

with tab_vol:
    fig_vol = px.bar(trend, x='Label', y='Volume', color_discrete_sequence=[C_VOLUME],
                     template='plotly_white', height=360, labels={'Volume': 'Deliveries'})
    fig_vol.update_layout(hovermode='x unified', xaxis_tickangle=-45)
    st.plotly_chart(fig_vol, use_container_width=True)

st.divider()

# ── Summary table with PoP % ───────────────────────────────────────────────────
st.subheader(f"{'Weekly' if view_mode == 'Weekly' else 'Monthly'} Summary Table")
disp = trend.copy()

# Calculate period-over-period % for the table
for col in ['Revenue', 'Cost', 'GP', 'Volume']:
    disp[f'{col} PoP%'] = disp[col].pct_change() * 100

def fmt_pop(v):
    if pd.isna(v):
        return "—"
    arrow = "▲" if v > 0 else "▼"
    return f"{arrow} {abs(v):.1f}%"

disp['Margin']   = (trend['GP'] / trend['Revenue'].replace(0, np.nan) * 100).apply(fmt_pct)
disp['GP PoP%']  = disp['GP PoP%'].apply(fmt_pop)
disp['Rev PoP%'] = disp['Revenue PoP%'].apply(fmt_pop)
disp['Vol PoP%'] = disp['Volume PoP%'].apply(fmt_pop)
disp['Revenue']  = disp['Revenue'].apply(fmt_idr)
disp['Cost']     = disp['Cost'].apply(fmt_idr)
disp['GP']       = disp['GP'].apply(fmt_idr)
disp['Volume']   = disp['Volume'].apply(fmt_vol)

st.dataframe(
    disp[['Label', 'Revenue', 'Rev PoP%', 'Cost', 'GP', 'GP PoP%', 'Margin', 'Volume', 'Vol PoP%']]
    .rename(columns={'Label': 'Period'}),
    use_container_width=True, hide_index=True
)

st.divider()

# ── Client revenue mix ────────────────────────────────────────────────────────
st.subheader("Client Revenue Mix")
client_rev = (
    df.groupby('Client Name', observed=True)['Total Revenue']
    .sum().reset_index().sort_values('Total Revenue', ascending=False)
)
top15 = client_rev.head(15)
others = client_rev.iloc[15:]['Total Revenue'].sum()
if others > 0:
    top15 = pd.concat([top15,
                       pd.DataFrame([{'Client Name': 'Others', 'Total Revenue': others}])],
                      ignore_index=True)
fig_pie = px.pie(top15, values='Total Revenue', names='Client Name', hole=0.4,
                 template='plotly_white', height=420)
fig_pie.update_traces(textposition='inside', textinfo='percent+label')
st.plotly_chart(fig_pie, use_container_width=True)
