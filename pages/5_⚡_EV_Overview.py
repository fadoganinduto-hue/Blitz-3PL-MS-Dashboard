import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="EV Overview | Blitz", page_icon="⚡", layout="wide")
st.title("⚡ EV Overview — Leasing & Rental")
st.caption("Combined view of all EV-related business: EV Rental clients and EV Leasing revenue lines across all clients.")

df_full = require_data()

# ── Identify EV-relevant data ─────────────────────────────────────────────────
# EV Rental: clients with "EV Rental" in name
# EV Leasing: any client with non-zero EV Reduction or EV Manpower or EV Revenue columns
ev_rental_mask = df_full['Client Name'].str.contains('EV Rental', na=False)
def _col_nonzero(df, col):
    """Return boolean mask where column values are non-zero, or False if column missing."""
    if col in df.columns:
        return df[col].abs() > 0
    return pd.Series(False, index=df.index)

ev_leasing_mask = (
    _col_nonzero(df_full, 'EV Reduction (3PL & KSJ)') |
    _col_nonzero(df_full, 'EV Manpower') |
    _col_nonzero(df_full, 'EV Revenue + Battery (Rental Client)')
)
ev_all = df_full[ev_rental_mask | ev_leasing_mask].copy()

if ev_all.empty:
    st.warning("No EV-related data found.")
    st.stop()

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    years = sorted(ev_all['Year'].dropna().unique().tolist())
    sel_years = st.multiselect("Year", years, default=[max(years)], key="ev_year")

    all_clients = sorted(ev_all['Client Name'].dropna().unique().tolist())
    sel_clients = st.multiselect("Client", all_clients, default=all_clients, key="ev_client")

    st.divider()
    st.caption("Leave blank to include all.")

df = ev_all.copy()
if sel_years:
    df = df[df['Year'].isin(sel_years)]
if sel_clients:
    df = df[df['Client Name'].isin(sel_clients)]

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode ───────────────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="ev_view")
pop = pop_label(view_mode)

periods = get_available_periods(df, view_mode)
if not periods:
    st.warning("No periods available.")
    st.stop()
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df, view_mode, curr_yr, curr_p)
prev_df_period = filter_period(df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

# ── Top-level KPIs ────────────────────────────────────────────────────────────
st.subheader(f"EV Summary — {curr_lbl}")

ev_rev_col = 'EV Revenue + Battery (Rental Client)'
ev_red_col = 'EV Reduction (3PL & KSJ)'
ev_man_col = 'EV Manpower'

# Current period totals
curr_ev_rev = curr_df[ev_rev_col].sum() if ev_rev_col in curr_df.columns else 0
curr_ev_red = curr_df[ev_red_col].sum() if ev_red_col in curr_df.columns else 0
curr_ev_man = curr_df[ev_man_col].sum() if ev_man_col in curr_df.columns else 0
curr_total_rev = curr_df['Total Revenue'].sum()
curr_total_cost = curr_df['Total Cost'].sum()
curr_gp = curr_total_rev - curr_total_cost
curr_margin = curr_gp / curr_total_rev * 100 if curr_total_rev else 0

# Previous period for PoP
if not prev_df_period.empty:
    prev_gp = prev_df_period['Total Revenue'].sum() - prev_df_period['Total Cost'].sum()
    gp_pop = pop_pct(curr_gp, prev_gp)
else:
    gp_pop = None

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("EV Revenue", fmt_idr(curr_ev_rev))
k2.metric("EV Reduction", fmt_idr(curr_ev_red))
k3.metric("EV Manpower", fmt_idr(curr_ev_man))
k4.metric("Total Revenue", fmt_idr(curr_total_rev))
k5.metric("Gross Profit", fmt_idr(curr_gp),
          f"{gp_pop:+.1f}% {pop}" if gp_pop is not None else None)
k6.metric("GP Margin", fmt_pct(curr_margin))

st.divider()

# ── Per-Client breakdown ──────────────────────────────────────────────────────
st.subheader("Per-Client EV Metrics")

ev_metrics = [ev_rev_col, ev_red_col, ev_man_col]
ev_metrics = [c for c in ev_metrics if c in df.columns]

client_agg = (
    curr_df.groupby('Client Name', observed=True)
    .agg(
        **{c: (c, 'sum') for c in ev_metrics},
        Total_Revenue=('Total Revenue', 'sum'),
        Total_Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Volume=('Delivery Volume', 'sum')
    )
    .reset_index()
    .sort_values('GP', ascending=False)
)
client_agg['GP Margin %'] = np.where(
    client_agg['Total_Revenue'] != 0,
    client_agg['GP'] / client_agg['Total_Revenue'] * 100, 0
)

# Tag client type
client_agg['Type'] = client_agg['Client Name'].apply(
    lambda x: 'EV Rental' if 'EV Rental' in str(x) else 'EV Leasing'
)

# Display table
disp = client_agg.copy()
for c in ev_metrics:
    disp[c] = disp[c].apply(fmt_idr)
disp['Revenue'] = disp['Total_Revenue'].apply(fmt_idr)
disp['Cost'] = disp['Total_Cost'].apply(fmt_idr)
disp['GP_fmt'] = disp['GP'].apply(fmt_idr)
disp['Volume'] = disp['Volume'].apply(fmt_vol)
disp['Margin'] = disp['GP Margin %'].apply(fmt_pct)

show_cols = ['Client Name', 'Type'] + ev_metrics + ['Revenue', 'Cost', 'GP_fmt', 'Volume', 'Margin']
show_cols = [c for c in show_cols if c in disp.columns]
st.dataframe(disp[show_cols], use_container_width=True, hide_index=True)

# Chart: Revenue & GP by client
fig_cl = px.bar(
    client_agg, x='Client Name', y=['Total_Revenue', 'GP'],
    barmode='group',
    color_discrete_map={'Total_Revenue': C_REVENUE, 'GP': C_GP},
    template='plotly_white', height=400,
    title="Revenue & GP by Client",
    labels={'value': 'IDR', 'variable': 'Metric'}
)
fig_cl.update_layout(hovermode='x unified', xaxis_tickangle=-20,
                     legend=dict(orientation='h', y=1.05))
st.plotly_chart(fig_cl, use_container_width=True)

st.divider()

# ── Cost structure ────────────────────────────────────────────────────────────
st.subheader("Cost Structure by Client")
cost_cols = [c for c in COST_COMPONENTS.keys() if c in df.columns]
cost_agg = curr_df.groupby('Client Name', observed=True)[cost_cols].sum().reset_index()
cost_long = cost_agg.melt(id_vars='Client Name', var_name='Component', value_name='Amount')
cost_long['Label'] = cost_long['Component'].map(COST_COMPONENTS).fillna(cost_long['Component'])
cost_long = cost_long[cost_long['Amount'] > 0]

if not cost_long.empty:
    fig_cost = px.bar(
        cost_long, x='Client Name', y='Amount', color='Label',
        barmode='stack', template='plotly_white', height=380,
        title="Cost Breakdown", labels={'Amount': 'IDR', 'Label': 'Component'}
    )
    fig_cost.update_layout(hovermode='x unified', xaxis_tickangle=-20,
                           legend=dict(orientation='h', y=1.05))
    st.plotly_chart(fig_cost, use_container_width=True)

st.divider()

# ── Trend over time ───────────────────────────────────────────────────────────
st.subheader(f"{view_mode} Trend")

if view_mode == "Weekly":
    trend = (
        df.groupby(['Year', 'Week (by Year)', 'Client Name'], observed=True)
        .agg(Revenue=('Total Revenue', 'sum'), GP=('GP', 'sum'),
             EV_Rev=(ev_rev_col, 'sum') if ev_rev_col in df.columns else ('Total Revenue', lambda x: 0))
        .reset_index()
        .sort_values(['Year', 'Week (by Year)'])
    )
    trend['Label'] = trend['Year'].astype(str) + ' W' + trend['Week (by Year)'].astype(str)
else:
    trend = (
        df.groupby(['Year', 'Month', 'Client Name'], observed=True)
        .agg(Revenue=('Total Revenue', 'sum'), GP=('GP', 'sum'),
             EV_Rev=(ev_rev_col, 'sum') if ev_rev_col in df.columns else ('Total Revenue', lambda x: 0))
        .reset_index()
    )
    trend['Month'] = pd.Categorical(trend['Month'], categories=MONTH_ORDER, ordered=True)
    trend = trend.sort_values(['Year', 'Month'])
    trend['Label'] = trend['Year'].astype(str) + ' ' + trend['Month'].astype(str)

tab1, tab2 = st.tabs(["Revenue", "Gross Profit"])

with tab1:
    fig_rev = px.bar(trend, x='Label', y='Revenue', color='Client Name',
                     barmode='stack', template='plotly_white', height=380,
                     title=f"{view_mode} EV Revenue by Client")
    fig_rev.update_layout(hovermode='x unified', xaxis_tickangle=-45,
                          legend=dict(orientation='h', y=1.05))
    st.plotly_chart(fig_rev, use_container_width=True)

with tab2:
    fig_gp = px.bar(trend, x='Label', y='GP', color='Client Name',
                    barmode='stack', template='plotly_white', height=380,
                    title=f"{view_mode} EV Gross Profit by Client")
    fig_gp.update_layout(hovermode='x unified', xaxis_tickangle=-45,
                         legend=dict(orientation='h', y=1.05))
    fig_gp.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.5)
    st.plotly_chart(fig_gp, use_container_width=True)

st.divider()

# ── Monthly YoY ───────────────────────────────────────────────────────────────
st.subheader("Monthly YoY Comparison")

monthly_ev = (
    df.groupby(['Year', 'Month'], observed=True)
    .agg(Revenue=('Total Revenue', 'sum'), Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
    .reset_index()
)
monthly_ev['Month'] = pd.Categorical(monthly_ev['Month'], categories=MONTH_ORDER, ordered=True)
monthly_ev = monthly_ev.sort_values(['Year', 'Month'])

fig_m = px.bar(monthly_ev, x='Month', y='GP', color='Year',
               barmode='group', template='plotly_white', height=360,
               title="Monthly EV GP by Year")
fig_m.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.05))
fig_m.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.4)
st.plotly_chart(fig_m, use_container_width=True)
