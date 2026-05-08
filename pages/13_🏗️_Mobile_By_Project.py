"""Mobile By Project — per-project P&L for mobile sellers.

Project is a column in the mobile `NEW COLUMN TEMPLATE` sheet. Rows without a
project label are excluded from this view (similar to delivery's By Project).
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_mobile_trend,
                   apply_chart_theme, idr_col, vol_col, pct_col,
                   dataframe_with_freeze)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile By Project | Blitz", page_icon="🏗️", layout="wide")
st.title("🏗️ Mobile Sellers — By Project")
st.caption("Per-project P&L for mobile selling. Rows without a project label are excluded.")

df_full = require_mobile_data()

if 'Project' not in df_full.columns:
    st.error(
        "The 'Project' column is missing from the loaded mobile data. "
        "Confirm the source workbook still has the Project column in NEW COLUMN TEMPLATE."
    )
    st.stop()

df_full = df_full[
    df_full['Project'].notna()
    & (df_full['Project'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No rows with a project label found.")
    st.stop()

# ── Period mode ──────────────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mobile_project_view")
pop_lbl = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
if not periods:
    st.warning("No periods available.")
    st.stop()

curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)
curr_df = filter_period(df_full, view_mode, curr_yr, curr_p)
prev_df = filter_period(df_full, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

# ── Latest period snapshot ───────────────────────────────────────────────────
if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week Snapshot — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month Snapshot — {curr_lbl}")
if prev_info:
    st.caption(f"Comparing vs {prev_info[2]}")

agg_curr = mobile_aggregate(curr_df, ['Project'])
clients_curr = (
    curr_df.groupby('Project', observed=True)['Client Name']
    .nunique().reset_index().rename(columns={'Client Name': 'Clients'})
)
agg_curr = agg_curr.merge(clients_curr, on='Project', how='left')

if not prev_df.empty:
    agg_prev = mobile_aggregate(prev_df, ['Project'])
    snapshot = agg_curr.merge(
        agg_prev[['Project', 'Profit Calc']].rename(columns={'Profit Calc': 'Profit_prev'}),
        on='Project', how='left',
    ).fillna({'Profit_prev': 0})
    snapshot[f'Profit {pop_lbl} %'] = snapshot.apply(
        lambda r: pop_pct(r['Profit Calc'], r['Profit_prev']) if r['Profit_prev'] != 0 else None,
        axis=1,
    )
else:
    snapshot = agg_curr.copy()
    snapshot[f'Profit {pop_lbl} %'] = None

snapshot['Profit Margin %'] = np.where(
    snapshot['Gross Revenue'] != 0,
    snapshot['Profit Calc'] / snapshot['Gross Revenue'] * 100,
    0,
)
snapshot = snapshot.sort_values('Profit Calc', ascending=False).reset_index(drop=True)

snapshot_disp = snapshot[['Project', 'Clients', 'Total Cups Sold', 'Total Active Riders',
                          'Gross Revenue', 'Blitz Revenue', 'Profit Calc',
                          'Profit Margin %', f'Profit {pop_lbl} %']].rename(
    columns={'Total Cups Sold': 'Cups', 'Total Active Riders': 'Riders', 'Profit Calc': 'Profit'}
)

dataframe_with_freeze(
    snapshot_disp,
    key="mobile_project_snapshot",
    default_freeze=['Project'],
    column_config={
        'Clients':              vol_col('Clients'),
        'Cups':                 vol_col('Cups'),
        'Riders':               vol_col('Riders'),
        'Gross Revenue':        idr_col('Gross Revenue'),
        'Blitz Revenue':        idr_col('Blitz Revenue'),
        'Profit':               idr_col('Profit'),
        'Profit Margin %':      pct_col('Margin', signed=False),
        f'Profit {pop_lbl} %':  pct_col(f'Profit {pop_lbl} %', signed=True),
    },
    width="stretch", hide_index=True, height=380,
)

st.divider()

# ── Period Rankings (all data) ───────────────────────────────────────────────
st.subheader("Project Rankings (all data)")
sort_col = st.selectbox("Sort by", ['Profit', 'Gross Revenue', 'Blitz Revenue', 'Cups'], index=0)

all_agg = mobile_aggregate(df_full, ['Project'])
all_clients = (
    df_full.groupby('Project', observed=True)['Client Name']
    .nunique().reset_index().rename(columns={'Client Name': 'Clients'})
)
all_agg = all_agg.merge(all_clients, on='Project', how='left')
all_agg['Profit Margin %'] = np.where(
    all_agg['Gross Revenue'] != 0, all_agg['Profit Calc'] / all_agg['Gross Revenue'] * 100, 0
)
# Select-then-rename to avoid collision: mobile_aggregate sums the source
# 'Profit' column too, which clashes with renaming 'Profit Calc' → 'Profit'.
all_disp = all_agg[['Project', 'Clients', 'Total Cups Sold', 'Total Active Riders',
                    'Gross Revenue', 'Blitz Revenue', 'Profit Calc', 'Profit Margin %']].rename(
    columns={'Total Cups Sold': 'Cups', 'Total Active Riders': 'Riders', 'Profit Calc': 'Profit'}
)
all_disp = all_disp.sort_values(sort_col, ascending=False).reset_index(drop=True)

dataframe_with_freeze(
    all_disp[['Project', 'Clients', 'Cups', 'Riders', 'Gross Revenue', 'Blitz Revenue',
              'Profit', 'Profit Margin %']],
    key="mobile_project_rankings",
    default_freeze=['Project'],
    column_config={
        'Clients':         vol_col('Clients'),
        'Cups':            vol_col('Cups'),
        'Riders':          vol_col('Riders'),
        'Gross Revenue':   idr_col('Gross Revenue'),
        'Blitz Revenue':   idr_col('Blitz Revenue'),
        'Profit':          idr_col('Profit'),
        'Profit Margin %': pct_col('Margin', signed=False),
    },
    width="stretch", hide_index=True,
)

top_n = min(15, len(all_disp))
top_proj = all_disp.head(top_n)
fig_rank = px.bar(
    top_proj, x='Project', y=sort_col,
    color_discrete_sequence=[C_GP if sort_col == 'Profit' else C_REVENUE],
    height=380, title=f"Top {top_n} Projects by {sort_col}",
)
fig_rank.update_layout(xaxis_tickangle=-25)
apply_chart_theme(fig_rank)
st.plotly_chart(fig_rank, width="stretch")

st.divider()

# ── Project Drilldown ────────────────────────────────────────────────────────
st.subheader("Project Drilldown")
sel_project = st.selectbox("Select a project", sorted(df_full['Project'].dropna().unique()))
pdf = df_full[df_full['Project'] == sel_project].copy()

if pdf.empty:
    st.stop()

ck1, ck2, ck3, ck4, ck5 = st.columns(5)
ck1.metric("Cups Sold",     fmt_vol(pdf['Total Cups Sold'].sum()))
ck2.metric("Gross Revenue", fmt_idr(pdf['Gross Revenue'].sum()))
ck3.metric("Blitz Revenue", fmt_idr(pdf['Blitz Revenue'].sum()))
ck4.metric("Profit",        fmt_idr(pdf['Profit Calc'].sum()))
margin = pdf['Profit Calc'].sum() / pdf['Gross Revenue'].sum() * 100 if pdf['Gross Revenue'].sum() else 0
ck5.metric("Margin",        fmt_pct(margin))

# Clients within this project
st.markdown("#### Clients in this project")
client_in_proj = mobile_aggregate(pdf, ['Client Name'])
client_in_proj['Margin %'] = np.where(
    client_in_proj['Gross Revenue'] != 0,
    client_in_proj['Profit Calc'] / client_in_proj['Gross Revenue'] * 100, 0,
)
client_in_proj = client_in_proj.sort_values('Profit Calc', ascending=False)

dataframe_with_freeze(
    client_in_proj[['Client Name', 'Total Cups Sold', 'Total Active Riders',
                    'Gross Revenue', 'Blitz Revenue', 'Profit Calc', 'Margin %']].rename(
        columns={'Total Cups Sold': 'Cups', 'Total Active Riders': 'Riders', 'Profit Calc': 'Profit'}),
    key="mobile_project_client_in_proj",
    default_freeze=['Client Name'],
    column_config={
        'Cups':           vol_col('Cups'),
        'Riders':         vol_col('Riders'),
        'Gross Revenue':  idr_col('Gross Revenue'),
        'Blitz Revenue':  idr_col('Blitz Revenue'),
        'Profit':         idr_col('Profit'),
        'Margin %':       pct_col('Margin', signed=False),
    },
    width="stretch", hide_index=True,
)

# Trend
st.markdown(f"#### {view_mode} P&L Trend")
trend_p = build_mobile_trend(pdf, [], view_mode)
trend_p['Profit Margin %'] = np.where(
    trend_p['GrossRevenue'] != 0, trend_p['Profit'] / trend_p['GrossRevenue'] * 100, 0
)
for m in ['Cups', 'GrossRevenue', 'Profit']:
    trend_p[f'{m} PoP%'] = trend_p[m].pct_change() * 100

fig = go.Figure()
fig.add_bar(x=trend_p['Label'], y=trend_p['GrossRevenue'], name='Gross Revenue',
            marker_color=C_REVENUE, opacity=0.8)
fig.add_bar(x=trend_p['Label'], y=trend_p['Profit'], name='Profit',
            marker_color=C_GP, opacity=0.8)
fig.add_scatter(x=trend_p['Label'], y=trend_p['Cups'], mode='lines+markers',
                name='Cups', line=dict(color=C_VOLUME, width=2), yaxis='y2')
fig.update_layout(
    barmode='group', height=400, yaxis_title='IDR',
    yaxis2=dict(title='Cups', overlaying='y', side='right'),
    xaxis_tickangle=-45, title=f"{sel_project} — {view_mode} P&L",
)
apply_chart_theme(fig)
st.plotly_chart(fig, width="stretch")

dataframe_with_freeze(
    trend_p[['Label', 'Cups', 'Cups PoP%', 'GrossRevenue', 'GrossRevenue PoP%',
             'BlitzRevenue', 'Profit', 'Profit PoP%', 'Profit Margin %']].rename(
        columns={'GrossRevenue': 'Gross Revenue',
                 'GrossRevenue PoP%': 'Rev PoP%',
                 'BlitzRevenue': 'Blitz Revenue',
                 'Cups PoP%': 'Cups PoP%',
                 'Profit PoP%': 'Profit PoP%'}),
    key="mobile_project_drilldown_trend",
    default_freeze=['Label'],
    column_config={
        'Label':           st.column_config.TextColumn('Period'),
        'Cups':            vol_col('Cups'),
        'Cups PoP%':       pct_col('Cups PoP%', signed=True),
        'Gross Revenue':   idr_col('Gross Revenue'),
        'Rev PoP%':        pct_col('Rev PoP%', signed=True),
        'Blitz Revenue':   idr_col('Blitz Revenue'),
        'Profit':          idr_col('Profit'),
        'Profit PoP%':     pct_col('Profit PoP%', signed=True),
        'Profit Margin %': pct_col('Margin', signed=False),
    },
    width="stretch", hide_index=True,
)
