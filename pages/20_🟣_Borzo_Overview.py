"""Borzo Overview — overall monthly KPIs & trends for Borzo (2022–present)."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils import (
    fmt_idr, fmt_pct, fmt_vol, MONTH_ORDER,
    C_REVENUE, C_COST, C_GP, C_VOLUME,
    require_borzo_monthly,
)

st.set_page_config(page_title="Borzo Overview | Blitz", page_icon="🟣", layout="wide")
st.title("🟣 Borzo — Overview")
st.caption("Monthly overall metrics. **Revenue = GMV**, **GP = Commission/Margin**.")

df = require_borzo_monthly()
df['PeriodLabel'] = df['Year'].astype(int).astype(str) + '-' + \
                    df['MonthNum'].astype(int).astype(str).str.zfill(2)
df = df.sort_values(['Year', 'MonthNum'])

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    years = sorted(df['Year'].dropna().astype(int).unique().tolist())
    sel_years = st.multiselect("Year", years, default=years, key="borzo_ov_year")

fdf = df[df['Year'].isin(sel_years)].copy() if sel_years else df.copy()
if fdf.empty:
    st.info("No data for selected years.")
    st.stop()

# Latest & prior month
latest = fdf.sort_values(['Year', 'MonthNum']).iloc[-1]
prev   = fdf.sort_values(['Year', 'MonthNum']).iloc[-2] if len(fdf) > 1 else None

def mom(c, p):
    if p is None or pd.isna(p) or p == 0:
        return None
    return (c - p) / abs(p) * 100

# ── KPI row ────────────────────────────────────────────────────────────────────
lm = f"{latest['Month']} {int(latest['Year'])}"
st.subheader(f"📊 Latest Month — {lm}")

k1, k2, k3, k4 = st.columns(4)
rev_p = mom(latest['GMV'], prev['GMV'] if prev is not None else None)
k1.metric("Revenue (GMV)", fmt_idr(latest['GMV']),
          f"{rev_p:+.1f}% MoM" if rev_p is not None else None)
cost_p = mom(latest['Cost'], prev['Cost'] if prev is not None else None)
k2.metric("Cost", fmt_idr(latest['Cost']),
          f"{cost_p:+.1f}% MoM" if cost_p is not None else None,
          delta_color="inverse")
gp_p = mom(latest['GP'], prev['GP'] if prev is not None else None)
k3.metric("GP (Commission)", fmt_idr(latest['GP']),
          f"{gp_p:+.1f}% MoM" if gp_p is not None else None)
margin_now = latest['GP Margin %']
margin_prev = prev['GP Margin %'] if prev is not None else None
margin_p = (margin_now - margin_prev) if margin_prev is not None else None
k4.metric("GP Margin %", fmt_pct(margin_now),
          f"{margin_p:+.1f}pp MoM" if margin_p is not None else None)

k5, k6, k7, k8 = st.columns(4)
ord_p = mom(latest['Orders'], prev['Orders'] if prev is not None else None)
k5.metric("Completed Orders", fmt_vol(latest['Orders']),
          f"{ord_p:+.1f}% MoM" if ord_p is not None else None)
del_p = mom(latest['Deliveries'], prev['Deliveries'] if prev is not None else None)
k6.metric("Completed Deliveries", fmt_vol(latest['Deliveries']),
          f"{del_p:+.1f}% MoM" if del_p is not None else None)
cli_p = mom(latest['Active Clients'], prev['Active Clients'] if prev is not None else None)
k7.metric("Active Clients", fmt_vol(latest['Active Clients']),
          f"{cli_p:+.1f}% MoM" if cli_p is not None else None)
cou_p = mom(latest['Active Couriers'], prev['Active Couriers'] if prev is not None else None)
k8.metric("Active Couriers", fmt_vol(latest['Active Couriers']),
          f"{cou_p:+.1f}% MoM" if cou_p is not None else None)

st.divider()

# ── Trend: Revenue / Cost / GP ─────────────────────────────────────────────────
st.subheader("📈 Revenue, Cost & GP — Monthly Trend")
fig = go.Figure()
fig.add_bar(x=fdf['PeriodLabel'], y=fdf['GMV'], name='Revenue (GMV)', marker_color=C_REVENUE)
fig.add_bar(x=fdf['PeriodLabel'], y=fdf['Cost'], name='Cost', marker_color=C_COST)
fig.add_bar(x=fdf['PeriodLabel'], y=fdf['GP'], name='GP (Commission)', marker_color=C_GP)
fig.update_layout(
    barmode='group', template='plotly_white', height=400,
    yaxis_title='IDR', hovermode='x unified',
    legend=dict(orientation='h', y=1.08)
)
st.plotly_chart(fig, use_container_width=True)

# ── Trend: GP Margin % ─────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    st.subheader("📈 GP Margin % — Monthly Trend")
    fig_m = go.Figure()
    fig_m.add_scatter(x=fdf['PeriodLabel'], y=fdf['GP Margin %'],
                      mode='lines+markers', name='GP Margin %',
                      line=dict(color=C_GP, width=2))
    fig_m.update_layout(template='plotly_white', height=340,
                        yaxis_title='%', hovermode='x unified')
    st.plotly_chart(fig_m, use_container_width=True)

with c2:
    st.subheader("🧮 Operations — Orders & Deliveries")
    fig_o = go.Figure()
    fig_o.add_scatter(x=fdf['PeriodLabel'], y=fdf['Orders'],
                      mode='lines+markers', name='Orders',
                      line=dict(color=C_VOLUME, width=2))
    fig_o.add_scatter(x=fdf['PeriodLabel'], y=fdf['Deliveries'],
                      mode='lines+markers', name='Deliveries',
                      line=dict(color='#009688', width=2, dash='dot'))
    fig_o.update_layout(template='plotly_white', height=340,
                        yaxis_title='Count', hovermode='x unified',
                        legend=dict(orientation='h', y=1.08))
    st.plotly_chart(fig_o, use_container_width=True)

# ── Client / Courier base ──────────────────────────────────────────────────────
c3, c4 = st.columns(2)
with c3:
    st.subheader("👥 Active Clients — Monthly")
    fig_c = go.Figure()
    fig_c.add_scatter(x=fdf['PeriodLabel'], y=fdf['Active Clients'],
                      mode='lines+markers', name='Active Clients',
                      line=dict(color='#1976D2', width=2))
    if 'new clients' in fdf.columns:
        fig_c.add_bar(x=fdf['PeriodLabel'], y=fdf['new clients'],
                      name='New Clients', marker_color='#90CAF9', opacity=0.5,
                      yaxis='y2')
        fig_c.update_layout(yaxis2=dict(overlaying='y', side='right',
                                        title='New Clients'))
    fig_c.update_layout(template='plotly_white', height=340,
                        yaxis_title='Clients', hovermode='x unified',
                        legend=dict(orientation='h', y=1.08))
    st.plotly_chart(fig_c, use_container_width=True)

with c4:
    st.subheader("🏍️ Active Couriers — Monthly")
    fig_k = go.Figure()
    fig_k.add_scatter(x=fdf['PeriodLabel'], y=fdf['Active Couriers'],
                      mode='lines+markers', name='Active Couriers',
                      line=dict(color='#D32F2F', width=2))
    fig_k.update_layout(template='plotly_white', height=340,
                        yaxis_title='Couriers', hovermode='x unified')
    st.plotly_chart(fig_k, use_container_width=True)

st.divider()

# ── Monthly table ──────────────────────────────────────────────────────────────
st.subheader("📋 Monthly Detail")
show_cols = ['Year', 'Month', 'GMV', 'Cost', 'GP', 'GP Margin %',
             'Orders', 'Deliveries', 'Active Clients', 'Active Couriers']
tbl = fdf[show_cols].copy()
tbl_disp = tbl.copy()
for c in ['GMV', 'Cost', 'GP']:
    tbl_disp[c] = tbl_disp[c].apply(fmt_idr)
tbl_disp['GP Margin %'] = tbl_disp['GP Margin %'].apply(fmt_pct)
for c in ['Orders', 'Deliveries', 'Active Clients', 'Active Couriers']:
    tbl_disp[c] = tbl_disp[c].apply(fmt_vol)
tbl_disp = tbl_disp.rename(columns={'GMV': 'Revenue (GMV)', 'GP': 'GP (Commission)'})
st.dataframe(tbl_disp.sort_values(['Year', 'Month'], ascending=[False, False]),
             use_container_width=True, hide_index=True)
