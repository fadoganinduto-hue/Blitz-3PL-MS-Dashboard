"""By SLA Type — per-SLA-type P&L for delivery clients.

SLA Type is a column in the delivery `Raw Data Source` sheet. Rows without an
SLA Type label are excluded from this view.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_trend, apply_chart_theme,
                   idr_col, vol_col, pct_col)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="By SLA Type | Blitz", page_icon="🎯", layout="wide")
st.title("🎯 By SLA Type")
st.caption("Per-SLA-type P&L. Drill into each SLA tier to see clients and trend.")

df_full = require_data()

if 'SLA Type' not in df_full.columns:
    st.error(
        "The 'SLA Type' column is missing from the loaded delivery data. "
        "Confirm the source workbook still has the SLA Type column in Raw Data Source."
    )
    st.stop()

# Keep only rows with a non-blank SLA Type
df_full = df_full[
    df_full['SLA Type'].notna()
    & (df_full['SLA Type'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No rows with an SLA Type label found.")
    st.stop()

df = sidebar_filters(df_full, page_key="sla")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode ──────────────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="sla_view")
pop = pop_label(view_mode)

periods = get_available_periods(df, view_mode)
if not periods:
    st.warning("No periods available.")
    st.stop()

curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)
curr_df = filter_period(df, view_mode, curr_yr, curr_p)
prev_df = filter_period(df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()
prev_lbl = prev_info[2] if prev_info else "—"

# ── Latest period snapshot ───────────────────────────────────────────────────
if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week Snapshot — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month Snapshot — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")

lw_agg = (
    curr_df.groupby('SLA Type', observed=True)
    .agg(
        Volume=('Delivery Volume', 'sum'),
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Clients=('Client Name', 'nunique'),
    )
    .reset_index()
)
if not prev_df.empty:
    pw_agg = (
        prev_df.groupby('SLA Type', observed=True)
        .agg(GP_prev=('GP', 'sum'), Revenue_prev=('Total Revenue', 'sum'))
        .reset_index()
    )
else:
    pw_agg = pd.DataFrame(columns=['SLA Type', 'GP_prev', 'Revenue_prev'])

lw = lw_agg.merge(pw_agg, on='SLA Type', how='left').fillna(0)
lw['GP Margin %'] = np.where(lw['Revenue'] != 0, lw['GP'] / lw['Revenue'] * 100, 0)
lw[f'GP {pop} %'] = lw.apply(lambda r: pop_pct(r['GP'], r['GP_prev']), axis=1)
lw = lw.sort_values('GP', ascending=False).reset_index(drop=True)

st.dataframe(
    lw[['SLA Type', 'Clients', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %', f'GP {pop} %']],
    column_config={
        'Clients':     vol_col('Clients'),
        'Volume':      vol_col('Volume'),
        'Revenue':     idr_col('Revenue'),
        'Cost':        idr_col('Cost'),
        'GP':          idr_col('GP'),
        'GP Margin %': pct_col('Margin', signed=False),
        f'GP {pop} %': pct_col(f'GP {pop} %', signed=True),
    },
    width="stretch", hide_index=True, height=380,
)

st.divider()

# ── Period Rankings ──────────────────────────────────────────────────────────
st.subheader("Period Rankings (all filtered data)")
sort_col = st.selectbox("Sort by", ['GP', 'Revenue', 'Volume', 'GP Margin %'], index=0)

sla_agg = (
    df.groupby('SLA Type', observed=True)
    .agg(
        Volume=('Delivery Volume', 'sum'),
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Clients=('Client Name', 'nunique'),
    )
    .reset_index()
)
sla_agg['GP Margin %'] = np.where(
    sla_agg['Revenue'] != 0, sla_agg['GP'] / sla_agg['Revenue'] * 100, 0
)
sla_agg = sla_agg.sort_values(sort_col, ascending=False).reset_index(drop=True)

st.dataframe(
    sla_agg[['SLA Type', 'Clients', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %']],
    column_config={
        'Clients':     vol_col('Clients'),
        'Volume':      vol_col('Volume'),
        'Revenue':     idr_col('Revenue'),
        'Cost':        idr_col('Cost'),
        'GP':          idr_col('GP'),
        'GP Margin %': pct_col('GP Margin %', signed=False),
    },
    width="stretch", hide_index=True,
)

# Top SLA types bar
top_n = min(10, len(sla_agg))
top_sla = sla_agg.head(top_n)
fig_rank = px.bar(
    top_sla, x='SLA Type', y=sort_col,
    color_discrete_sequence=[C_GP if sort_col == 'GP' else C_REVENUE],
    height=380, title=f"Top {top_n} SLA Types by {sort_col}",
)
fig_rank.update_layout(xaxis_tickangle=-15)
apply_chart_theme(fig_rank)
st.plotly_chart(fig_rank, width="stretch")

st.divider()

# ── SLA Type Drilldown ───────────────────────────────────────────────────────
st.subheader("SLA Type Drilldown")
sel_sla = st.selectbox("Select an SLA type", sorted(df['SLA Type'].dropna().unique()))
sdf = df[df['SLA Type'] == sel_sla].copy()

if sdf.empty:
    st.stop()

# SLA-level KPIs
ck1, ck2, ck3, ck4, ck5 = st.columns(5)
ck1.metric("Revenue", fmt_idr(sdf['Total Revenue'].sum()))
ck2.metric("Cost", fmt_idr(sdf['Total Cost'].sum()))
ck3.metric("GP", fmt_idr(sdf['GP'].sum()))
gpm_s = sdf['GP'].sum() / sdf['Total Revenue'].sum() * 100 if sdf['Total Revenue'].sum() else 0
ck4.metric("Margin", fmt_pct(gpm_s))
ck5.metric("Volume", fmt_vol(sdf['Delivery Volume'].sum()))

# Clients within this SLA type
st.markdown("#### Clients in this SLA type")
client_in_sla = (
    sdf.groupby('Client Name', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'),
         Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'),
         GP=('GP', 'sum'))
    .reset_index()
)
client_in_sla['Margin %'] = np.where(
    client_in_sla['Revenue'] != 0,
    client_in_sla['GP'] / client_in_sla['Revenue'] * 100, 0
)
client_in_sla = client_in_sla.sort_values('GP', ascending=False)

st.dataframe(
    client_in_sla[['Client Name', 'Volume', 'Revenue', 'Cost', 'GP', 'Margin %']],
    column_config={
        'Volume':   vol_col('Volume'),
        'Revenue':  idr_col('Revenue'),
        'Cost':     idr_col('Cost'),
        'GP':       idr_col('GP'),
        'Margin %': pct_col('Margin', signed=False),
    },
    width="stretch", hide_index=True,
)

# Trend
st.markdown(f"#### {view_mode} P&L Trend")
trend_s = build_trend(sdf, [], view_mode)
trend_s['GP Margin %'] = np.where(
    trend_s['Revenue'] != 0, trend_s['GP'] / trend_s['Revenue'] * 100, 0
)
for m in ['Revenue', 'GP', 'Volume']:
    trend_s[f'{m} PoP%'] = trend_s[m].pct_change() * 100

fig = go.Figure()
fig.add_bar(x=trend_s['Label'], y=trend_s['Revenue'], name='Revenue',
            marker_color=C_REVENUE, opacity=0.8)
fig.add_bar(x=trend_s['Label'], y=trend_s['Cost'], name='Cost',
            marker_color=C_COST, opacity=0.8)
fig.add_scatter(x=trend_s['Label'], y=trend_s['GP'], mode='lines+markers',
                name='GP', line=dict(color=C_GP, width=2))
fig.update_layout(barmode='group', height=400, yaxis_title='IDR',
                  xaxis_tickangle=-45, title=f"{sel_sla} — {view_mode} P&L")
apply_chart_theme(fig)
st.plotly_chart(fig, width="stretch")

st.dataframe(
    trend_s[['Label', 'Volume', 'Volume PoP%', 'Revenue', 'Revenue PoP%',
             'Cost', 'GP', 'GP PoP%', 'GP Margin %']],
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
cost_data = {label: sdf[col].sum() for col, label in COST_COMPONENTS.items()
             if col in sdf.columns and sdf[col].sum() > 0}
if cost_data:
    cost_df = pd.DataFrame({'Component': list(cost_data.keys()), 'Amount': list(cost_data.values())})
    fig_cost = px.pie(cost_df, values='Amount', names='Component', hole=0.35,
                      height=360, title=f"{sel_sla} — Cost Structure")
    apply_chart_theme(fig_cost)
    st.plotly_chart(fig_cost, width="stretch")
