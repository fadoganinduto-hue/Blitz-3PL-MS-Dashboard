import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="EV Rental | Blitz", page_icon="⚡", layout="wide")
st.title("⚡ EV Rental")
st.caption("Electric vehicle rental business line — revenue, cost, and GP from Raw Data Source.")

df_full = require_data()

# ── Filter to EV Rental clients only ─────────────────────────────────────────
ev_mask = df_full['Client Name'].str.contains('EV Rental', na=False)
ev_full = df_full[ev_mask].copy()

if ev_full.empty:
    st.warning("No EV Rental clients found in the data. Ensure client names contain 'EV Rental'.")
    st.stop()

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    years = sorted(ev_full['Year'].dropna().unique().tolist())
    sel_years = st.multiselect("Year", years, default=[max(years)], key="ev_year")

    clients = sorted(ev_full['Client Name'].dropna().unique().tolist())
    sel_clients = st.multiselect("EV Client", clients, default=clients, key="ev_client")
    st.divider()
    st.caption("Leave blank to include all.")

df = ev_full.copy()
if sel_years:
    df = df[df['Year'].isin(sel_years)]
if sel_clients:
    df = df[df['Client Name'].isin(sel_clients)]

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Top KPIs ──────────────────────────────────────────────────────────────────
total_rev  = df['Total Revenue'].sum()
total_cost = df['Total Cost'].sum()
total_gp   = df['GP'].sum()
gp_margin  = total_gp / total_rev * 100 if total_rev else 0
ev_rev     = df['EV Revenue + Battery (Rental Client)'].sum()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("EV Revenue",         fmt_idr(ev_rev))
k2.metric("Total Revenue",      fmt_idr(total_rev))
k3.metric("Total Cost",         fmt_idr(total_cost))
k4.metric("Gross Profit",       fmt_idr(total_gp))
k5.metric("GP Margin",          fmt_pct(gp_margin))

st.divider()

# ── Revenue & GP by client ────────────────────────────────────────────────────
st.subheader("Revenue & GP by EV Client")

client_agg = (
    df.groupby('Client Name', observed=True)
    .agg(Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'),
         GP=('GP', 'sum'),
         EV_Rev=('EV Revenue + Battery (Rental Client)', 'sum'),
         EV_Red=('EV Reduction (3PL & KSJ)', 'sum'))
    .reset_index()
    .sort_values('GP', ascending=False)
)
client_agg['GP Margin %'] = client_agg.apply(
    lambda r: r['GP'] / r['Revenue'] * 100 if r['Revenue'] else 0, axis=1
)

fig_cl = px.bar(
    client_agg, x='Client Name', y=['Revenue', 'Cost', 'GP'],
    barmode='group',
    color_discrete_map={'Revenue': C_REVENUE, 'Cost': C_COST, 'GP': C_GP},
    template='plotly_white', height=400,
    title="Revenue, Cost & GP by EV Rental Client"
)
fig_cl.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.05),
                     xaxis_tickangle=-20)
st.plotly_chart(fig_cl, use_container_width=True)

# Summary table
disp = client_agg.copy()
disp['EV Revenue']  = disp['EV_Rev'].apply(fmt_idr)
disp['EV Reduction']= disp['EV_Red'].apply(fmt_idr)
disp['Total Rev']   = disp['Revenue'].apply(fmt_idr)
disp['Cost']        = disp['Cost'].apply(fmt_idr)
disp['GP']          = disp['GP'].apply(fmt_idr)
disp['Margin']      = disp['GP Margin %'].apply(fmt_pct)
st.dataframe(
    disp[['Client Name', 'EV Revenue', 'EV Reduction', 'Total Rev', 'Cost', 'GP', 'Margin']],
    use_container_width=True, hide_index=True
)

st.divider()

# ── Cost structure breakdown ──────────────────────────────────────────────────
st.subheader("Cost Structure by EV Client")

cost_cols = [c for c in COST_COMPONENTS.keys() if c in df.columns]
cost_agg  = df.groupby('Client Name', observed=True)[cost_cols].sum().reset_index()
cost_long = cost_agg.melt(id_vars='Client Name', var_name='Component', value_name='Amount')
cost_long['Label'] = cost_long['Component'].map(COST_COMPONENTS).fillna(cost_long['Component'])
cost_long = cost_long[cost_long['Amount'] > 0]

if not cost_long.empty:
    fig_cost = px.bar(
        cost_long, x='Client Name', y='Amount', color='Label',
        barmode='stack', template='plotly_white', height=380,
        title="Cost Breakdown by EV Client",
        labels={'Amount': 'IDR', 'Label': 'Cost Component'}
    )
    fig_cost.update_layout(hovermode='x unified', xaxis_tickangle=-20,
                           legend=dict(orientation='h', y=1.05))
    st.plotly_chart(fig_cost, use_container_width=True)

st.divider()

# ── Weekly revenue trend ──────────────────────────────────────────────────────
st.subheader("Weekly Revenue Trend")

weekly_ev = (
    df.groupby(['Year', 'Week (by Year)', 'Client Name'], observed=True)
    .agg(Revenue=('Total Revenue', 'sum'), GP=('GP', 'sum'))
    .reset_index()
    .sort_values(['Year', 'Week (by Year)'])
)
weekly_ev['Label'] = (weekly_ev['Year'].astype(str) + ' W' +
                      weekly_ev['Week (by Year)'].astype(str))

tab1, tab2 = st.tabs(["Revenue", "Gross Profit"])

with tab1:
    fig_rev = px.bar(weekly_ev, x='Label', y='Revenue', color='Client Name',
                     barmode='stack', template='plotly_white', height=380,
                     title="Weekly EV Revenue by Client",
                     labels={'Revenue': 'IDR'})
    fig_rev.update_layout(hovermode='x unified', xaxis_tickangle=-45,
                          legend=dict(orientation='h', y=1.05))
    st.plotly_chart(fig_rev, use_container_width=True)

with tab2:
    fig_gp = px.bar(weekly_ev, x='Label', y='GP', color='Client Name',
                    barmode='stack', template='plotly_white', height=380,
                    title="Weekly EV Gross Profit by Client",
                    labels={'GP': 'IDR'})
    fig_gp.update_layout(hovermode='x unified', xaxis_tickangle=-45,
                         legend=dict(orientation='h', y=1.05))
    fig_gp.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.5)
    st.plotly_chart(fig_gp, use_container_width=True)

st.divider()

# ── Monthly YoY ───────────────────────────────────────────────────────────────
st.subheader("Monthly Performance")

monthly_ev = (
    df.groupby(['Year', 'Month'], observed=True)
    .agg(Revenue=('Total Revenue', 'sum'), Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
    .reset_index()
)
monthly_ev['Month'] = pd.Categorical(monthly_ev['Month'], categories=MONTH_ORDER, ordered=True)
monthly_ev = monthly_ev.sort_values(['Year', 'Month'])

fig_m = px.bar(monthly_ev, x='Month', y='GP', color='Year',
               barmode='group', template='plotly_white', height=360,
               title="Monthly EV GP by Year",
               labels={'GP': 'Gross Profit (IDR)'})
fig_m.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.05))
fig_m.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.4)
st.plotly_chart(fig_m, use_container_width=True)
