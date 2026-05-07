"""By Project — per-project P&L for delivery clients with project-level breakdowns.

Project is a column in the delivery `Raw Data Source` sheet. Many clients have
no project label (single-stream business), so this page filters to only rows
where Project is populated.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_trend, apply_chart_theme)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="By Project | Blitz", page_icon="🏗️", layout="wide")
st.title("🏗️ By Project")
st.caption("Per-project P&L for clients with multi-project structures. "
           "Clients without a project label are excluded from this view.")

df_full = require_data()

if 'Project' not in df_full.columns:
    st.error(
        "The 'Project' column is missing from the loaded delivery data. "
        "Confirm the source workbook still has the Project column in Raw Data Source."
    )
    st.stop()

# Keep only rows with a non-blank Project value
df_full = df_full[
    df_full['Project'].notna()
    & (df_full['Project'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No rows with a project label found.")
    st.stop()

df = sidebar_filters(df_full, page_key="project")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode ──────────────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="project_view")
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


def fmt_delta(v):
    if v is None or pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"


lw_agg = (
    curr_df.groupby('Project', observed=True)
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
        prev_df.groupby('Project', observed=True)
        .agg(GP_prev=('GP', 'sum'), Revenue_prev=('Total Revenue', 'sum'))
        .reset_index()
    )
else:
    pw_agg = pd.DataFrame(columns=['Project', 'GP_prev', 'Revenue_prev'])

lw = lw_agg.merge(pw_agg, on='Project', how='left').fillna(0)
lw['GP Margin %'] = np.where(lw['Revenue'] != 0, lw['GP'] / lw['Revenue'] * 100, 0)
lw[f'GP {pop} %'] = lw.apply(lambda r: pop_pct(r['GP'], r['GP_prev']), axis=1)
lw = lw.sort_values('GP', ascending=False).reset_index(drop=True)

disp_lw = lw.copy()
disp_lw['Revenue']      = disp_lw['Revenue'].apply(fmt_idr)
disp_lw['Cost']         = disp_lw['Cost'].apply(fmt_idr)
disp_lw['GP']           = disp_lw['GP'].apply(fmt_idr)
disp_lw['Margin']       = disp_lw['GP Margin %'].apply(fmt_pct)
disp_lw['Volume']       = disp_lw['Volume'].apply(fmt_vol)
disp_lw[f'GP {pop} %']  = disp_lw[f'GP {pop} %'].apply(fmt_delta)

st.dataframe(
    disp_lw[['Project', 'Clients', 'Volume', 'Revenue', 'Cost', 'GP', 'Margin', f'GP {pop} %']],
    width="stretch", hide_index=True, height=380,
)

st.divider()

# ── Period Rankings ──────────────────────────────────────────────────────────
st.subheader("Period Rankings (all filtered data)")
sort_col = st.selectbox("Sort by", ['GP', 'Revenue', 'Volume', 'GP Margin %'], index=0)

project_agg = (
    df.groupby('Project', observed=True)
    .agg(
        Volume=('Delivery Volume', 'sum'),
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Clients=('Client Name', 'nunique'),
    )
    .reset_index()
)
project_agg['GP Margin %'] = np.where(
    project_agg['Revenue'] != 0, project_agg['GP'] / project_agg['Revenue'] * 100, 0
)
project_agg = project_agg.sort_values(sort_col, ascending=False).reset_index(drop=True)

disp_all = project_agg.copy()
disp_all['Revenue']     = disp_all['Revenue'].apply(fmt_idr)
disp_all['Cost']        = disp_all['Cost'].apply(fmt_idr)
disp_all['GP']          = disp_all['GP'].apply(fmt_idr)
disp_all['GP Margin %'] = disp_all['GP Margin %'].apply(fmt_pct)
disp_all['Volume']      = disp_all['Volume'].apply(fmt_vol)
st.dataframe(
    disp_all[['Project', 'Clients', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %']],
    width="stretch", hide_index=True,
)

# Top N bar chart
top_n = min(15, len(project_agg))
top_projects = project_agg.head(top_n)
fig_rank = px.bar(
    top_projects, x='Project', y=sort_col,
    color_discrete_sequence=[C_GP if sort_col == 'GP' else C_REVENUE],
    height=380, title=f"Top {top_n} Projects by {sort_col}",
)
fig_rank.update_layout(xaxis_tickangle=-25)
apply_chart_theme(fig_rank)
st.plotly_chart(fig_rank, width="stretch")

st.divider()

# ── Project Drilldown ────────────────────────────────────────────────────────
st.subheader("Project Drilldown")
sel_project = st.selectbox("Select a project", sorted(df['Project'].dropna().unique()))
pdf = df[df['Project'] == sel_project].copy()

if pdf.empty:
    st.stop()

# Project-level KPIs
ck1, ck2, ck3, ck4, ck5 = st.columns(5)
ck1.metric("Revenue", fmt_idr(pdf['Total Revenue'].sum()))
ck2.metric("Cost", fmt_idr(pdf['Total Cost'].sum()))
ck3.metric("GP", fmt_idr(pdf['GP'].sum()))
gpm_p = pdf['GP'].sum() / pdf['Total Revenue'].sum() * 100 if pdf['Total Revenue'].sum() else 0
ck4.metric("Margin", fmt_pct(gpm_p))
ck5.metric("Volume", fmt_vol(pdf['Delivery Volume'].sum()))

# Clients within this project
st.markdown("#### Clients in this project")
client_in_proj = (
    pdf.groupby('Client Name', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'),
         Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'),
         GP=('GP', 'sum'))
    .reset_index()
)
client_in_proj['Margin %'] = np.where(
    client_in_proj['Revenue'] != 0,
    client_in_proj['GP'] / client_in_proj['Revenue'] * 100, 0
)
client_in_proj = client_in_proj.sort_values('GP', ascending=False)

disp_c = client_in_proj.copy()
disp_c['Revenue'] = disp_c['Revenue'].apply(fmt_idr)
disp_c['Cost']    = disp_c['Cost'].apply(fmt_idr)
disp_c['GP']      = disp_c['GP'].apply(fmt_idr)
disp_c['Margin']  = disp_c['Margin %'].apply(fmt_pct)
disp_c['Volume']  = disp_c['Volume'].apply(fmt_vol)
st.dataframe(
    disp_c[['Client Name', 'Volume', 'Revenue', 'Cost', 'GP', 'Margin']],
    width="stretch", hide_index=True,
)

# Trend
st.markdown(f"#### {view_mode} P&L Trend")
trend_p = build_trend(pdf, [], view_mode)
trend_p['GP Margin %'] = np.where(
    trend_p['Revenue'] != 0, trend_p['GP'] / trend_p['Revenue'] * 100, 0
)
for m in ['Revenue', 'GP', 'Volume']:
    trend_p[f'{m} PoP%'] = trend_p[m].pct_change() * 100

fig = go.Figure()
fig.add_bar(x=trend_p['Label'], y=trend_p['Revenue'], name='Revenue',
            marker_color=C_REVENUE, opacity=0.8)
fig.add_bar(x=trend_p['Label'], y=trend_p['Cost'], name='Cost',
            marker_color=C_COST, opacity=0.8)
fig.add_scatter(x=trend_p['Label'], y=trend_p['GP'], mode='lines+markers',
                name='GP', line=dict(color=C_GP, width=2))
fig.update_layout(barmode='group', height=400, yaxis_title='IDR',
                  xaxis_tickangle=-45, title=f"{sel_project} — {view_mode} P&L")
apply_chart_theme(fig)
st.plotly_chart(fig, width="stretch")


def fmt_pop_plain(v):
    if pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"


disp_drill = trend_p.copy()
for col in ['Revenue', 'Cost', 'GP']:
    disp_drill[col] = disp_drill[col].apply(fmt_idr)
disp_drill['Margin']   = disp_drill['GP Margin %'].apply(fmt_pct)
disp_drill['Volume']   = disp_drill['Volume'].apply(fmt_vol)
disp_drill['Rev PoP%'] = disp_drill['Revenue PoP%'].apply(fmt_pop_plain)
disp_drill['GP PoP%']  = disp_drill['GP PoP%'].apply(fmt_pop_plain)
disp_drill['Vol PoP%'] = disp_drill['Volume PoP%'].apply(fmt_pop_plain)
st.dataframe(
    disp_drill[['Label', 'Volume', 'Vol PoP%', 'Revenue', 'Rev PoP%',
                'Cost', 'GP', 'GP PoP%', 'Margin']],
    width="stretch", hide_index=True,
)

# Cost structure pie
cost_data = {label: pdf[col].sum() for col, label in COST_COMPONENTS.items()
             if col in pdf.columns and pdf[col].sum() > 0}
if cost_data:
    cost_df = pd.DataFrame({'Component': list(cost_data.keys()), 'Amount': list(cost_data.values())})
    fig_cost = px.pie(cost_df, values='Amount', names='Component', hole=0.35,
                      height=360, title=f"{sel_project} — Cost Structure")
    apply_chart_theme(fig_cost)
    st.plotly_chart(fig_cost, width="stretch")
