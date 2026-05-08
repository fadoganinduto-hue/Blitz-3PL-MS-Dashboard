import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   selected_period_df, selected_period_info, period_picker,
                   pop_pct, pop_label, period_selector, build_mobile_trend)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile Overview | Blitz", page_icon="📱", layout="wide")
st.title("📱 Mobile Sellers Overview")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

_pc1, _pc2 = st.columns([1, 2])
with _pc1:
    view_mode = period_selector(page_key="mobile_overview")
with _pc2:
    period_picker(df_full, view_mode, page_key="mobile_overview")
pop = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
curr_yr, curr_p, curr_lbl = selected_period_info(df_full, view_mode, page_key="mobile_overview")
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = selected_period_df(df_full, view_mode, page_key="mobile_overview")
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


def _weighted_pct(curr, prev, num_col: str, base_col: str):
    """Aggregate % the right way: sum(numerator) / sum(base) × 100.
    Avoids the trap of averaging row-level percentages, which mobile_aggregate
    cannot do correctly because it sums all numeric columns blindly.
    """
    cv = (curr[num_col].sum() / curr[base_col].sum() * 100) if curr[base_col].sum() else 0
    if prev.empty or prev[base_col].sum() == 0:
        return cv, None
    pv = prev[num_col].sum() / prev[base_col].sum() * 100
    return cv, cv - pv  # delta in percentage points


# ── Primary KPI strip (Spec 4): operational + reconciled PV/PnL metrics ──
cups_v,  cups_p   = period_kpi(curr_df, prev_df, 'Total Cups Sold')
riders_v, riders_p = period_kpi(curr_df, prev_df, 'Total Active Riders')
dpv_v,  dpv_p     = period_kpi(curr_df, prev_df, 'Delivery PV')
evpv_v, evpv_p    = period_kpi(curr_df, prev_df, 'EV PV')
totpv_v, totpv_p  = period_kpi(curr_df, prev_df, 'Total PV')
dpnl_v,  dpnl_dlt = _weighted_pct(curr_df, prev_df, 'Delivery PV', '_delivery_pv_base')
evpnl_v, evpnl_dlt = _weighted_pct(curr_df, prev_df, 'EV PV',       '_ev_pv_base')

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("Total Cups",      fmt_vol(cups_v),    f"{cups_p:+.1f}% {pop}"   if cups_p   is not None else None)
c2.metric("Active Riders",   fmt_vol(riders_v),  f"{riders_p:+.1f}% {pop}" if riders_p is not None else None)
c3.metric("Delivery PV",     fmt_idr(dpv_v),     f"{dpv_p:+.1f}% {pop}"    if dpv_p    is not None else None)
c4.metric("Delivery PnL %",  fmt_pct(dpnl_v),    f"{dpnl_dlt:+.1f}pp {pop}" if dpnl_dlt is not None else None)
c5.metric("EV PV",           fmt_idr(evpv_v),    f"{evpv_p:+.1f}% {pop}"   if evpv_p   is not None else None)
c6.metric("EV PnL %",        fmt_pct(evpnl_v),   f"{evpnl_dlt:+.1f}pp {pop}" if evpnl_dlt is not None else None)
c7.metric("Total PV",        fmt_idr(totpv_v),   f"{totpv_p:+.1f}% {pop}"  if totpv_p  is not None else None)

# ── Demoted high-level rollup: Profit Calc / Margin from Total Revenue ──
# These don't include rider/manpower/claim/storing costs and so disagree with
# the PV-based numbers above; kept for continuity with prior reporting.
st.caption(
    "**High-level rollup** (Gross Revenue − Total Income Sales − Total Operational Cost). "
    "Excludes rider, manpower, claim, and storing costs — does not match the PV-based "
    "metrics above. Retained for continuity."
)
grev_v,  grev_p  = period_kpi(curr_df, prev_df, 'Gross Revenue')
brev_v,  brev_p  = period_kpi(curr_df, prev_df, 'Blitz Revenue')
cost_v,  cost_p  = period_kpi(curr_df, prev_df, 'Total Cost (Mobile)')
profit_v  = (curr_df['Gross Revenue'] - curr_df['Total Income Sales (Weekly)'] - curr_df['Total Operational Cost']).sum()
profit_pv = (prev_df['Gross Revenue'] - prev_df['Total Income Sales (Weekly)'] - prev_df['Total Operational Cost']).sum() if not prev_df.empty else 0
profit_p  = pop_pct(profit_v, profit_pv)
margin_v  = profit_v / grev_v * 100 if grev_v > 0 else 0
margin_pv = profit_pv / (prev_df['Gross Revenue'].sum() if not prev_df.empty else 1) * 100 if not prev_df.empty else 0
margin_p  = margin_v - margin_pv if not prev_df.empty else None

r1, r2, r3, r4, r5 = st.columns(5)
r1.metric("Gross Revenue",   fmt_idr(grev_v),   f"{grev_p:+.1f}% {pop}"   if grev_p   is not None else None)
r2.metric("Blitz Revenue",   fmt_idr(brev_v),   f"{brev_p:+.1f}% {pop}"   if brev_p   is not None else None)
r3.metric("Total Cost",      fmt_idr(cost_v),   f"{cost_p:+.1f}% {pop}"   if cost_p   is not None else None, delta_color="inverse")
r4.metric("Profit Calc",     fmt_idr(profit_v), f"{profit_p:+.1f}% {pop}" if profit_p is not None else None)
r5.metric("Profit Margin %", fmt_pct(margin_v), f"{margin_p:+.1f}pp {pop}" if margin_p is not None else None)

# ── Per-driver metrics row ────────────────────────────────────────────────────
d1, d2, d3 = st.columns(3)
cups_per_driver = cups_v / riders_v if riders_v else 0
prev_riders = prev_df['Total Active Riders'].sum() if not prev_df.empty else 0
prev_cups = prev_df['Total Cups Sold'].sum() if not prev_df.empty else 0
prev_cpd = prev_cups / prev_riders if prev_riders else 0
cpd_pop = pop_pct(cups_per_driver, prev_cpd) if prev_cpd else None
d1.metric("Cups / Driver", f"{cups_per_driver:,.1f}", f"{cpd_pop:+.1f}% {pop}" if cpd_pop is not None else None)
rev_per_driver = grev_v / riders_v if riders_v else 0
prev_rpd = (prev_df['Gross Revenue'].sum() / prev_riders) if prev_riders else 0
rpd_pop = pop_pct(rev_per_driver, prev_rpd) if prev_rpd else None
d2.metric("Revenue / Driver", fmt_idr(rev_per_driver), f"{rpd_pop:+.1f}% {pop}" if rpd_pop is not None else None)
pv_per_driver = totpv_v / riders_v if riders_v else 0
prev_tpv = prev_df['Total PV'].sum() if not prev_df.empty else 0
prev_pvpd = (prev_tpv / prev_riders) if prev_riders else 0
pvpd_pop = pop_pct(pv_per_driver, prev_pvpd) if prev_pvpd else None
d3.metric("Total PV / Driver", fmt_idr(pv_per_driver), f"{pvpd_pop:+.1f}% {pop}" if pvpd_pop is not None else None)

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
