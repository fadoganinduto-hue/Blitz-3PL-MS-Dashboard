import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_trend)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="By Team | Blitz", page_icon="🏙️", layout="wide")
st.title("🏙️ By Team")
st.caption("Jakarta vs. Surabaya — latest period snapshot, cost structure, and trend comparison.")

df_full = require_data()
df = sidebar_filters(df_full, page_key="team")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

teams = sorted(df['Blitz Team'].dropna().unique().tolist())

# ── Period mode selector ───────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="team_view")
pop = pop_label(view_mode)

periods   = get_available_periods(df, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df, view_mode, curr_yr, curr_p)
prev_df = filter_period(df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()
prev_lbl = prev_info[2] if prev_info else "—"

# ── Latest period snapshot ────────────────────────────────────────────────────
if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")

curr_team = curr_df.groupby('Blitz Team', observed=True).agg(
    Revenue=('Total Revenue', 'sum'), Cost=('Total Cost', 'sum'),
    GP=('GP', 'sum'), Volume=('Delivery Volume', 'sum')
).reset_index()

if not prev_df.empty:
    prev_team = (prev_df.groupby('Blitz Team', observed=True)['GP']
                 .sum().reset_index().rename(columns={'GP': 'GP_prev'}))
else:
    prev_team = pd.DataFrame(columns=['Blitz Team', 'GP_prev'])

lw_team = curr_team.merge(prev_team, on='Blitz Team', how='left').fillna(0)
lw_team['GP Margin %'] = np.where(lw_team['Revenue'] != 0, lw_team['GP'] / lw_team['Revenue'] * 100, 0)
lw_team[f'GP {pop} %'] = lw_team.apply(lambda r: pop_pct(r['GP'], r['GP_prev']), axis=1)

cols_list = st.columns(len(lw_team)) if len(lw_team) > 0 else st.columns(1)
for col, (_, row) in zip(cols_list, lw_team.iterrows()):
    with col:
        delta_v = row[f'GP {pop} %']
        delta_str = f"{delta_v:+.1f}% {pop}" if pd.notna(delta_v) else None
        st.markdown(f"### 🏙️ {row['Blitz Team']}")
        st.metric("Revenue", fmt_idr(row['Revenue']))
        st.metric("GP",      fmt_idr(row['GP']), delta_str)
        st.metric("Margin",  fmt_pct(row['GP Margin %']))
        st.metric("Volume",  fmt_vol(row['Volume']))

st.divider()

# ── Period comparison chart ───────────────────────────────────────────────────
st.subheader("Period Comparison")
metric_choice = st.radio("Metric", ['GP', 'Revenue', 'Cost'], horizontal=True)

trend_t = build_trend(df, ['Blitz Team'], view_mode)

fig_t = px.bar(
    trend_t, x='Label', y=metric_choice, color='Blitz Team',
    barmode='group', template='plotly_white', height=400,
    color_discrete_map={'Jakarta': C_REVENUE, 'Surabaya': C_GP},
    title=f"{metric_choice} — {view_mode} by Team",
    labels={metric_choice: 'IDR'}
)
fig_t.update_layout(hovermode='x unified', xaxis_tickangle=-45,
                    legend=dict(orientation='h', y=1.05))
if metric_choice == 'GP':
    fig_t.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.4)
st.plotly_chart(fig_t, use_container_width=True)

# PoP % table per team
st.markdown("**Period-over-Period % Change by Team**")
def fmt_pop_plain(v):
    if pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"

pop_rows = []
for team in teams:
    team_trend = trend_t[trend_t['Blitz Team'] == team].copy()
    if len(team_trend) >= 2:
        last = team_trend.iloc[-1]
        prev_r = team_trend.iloc[-2]
        pop_rows.append({
            'Team': team,
            f'GP {pop}%':  fmt_pop_plain(pop_pct(last['GP'], prev_r['GP'])),
            f'Rev {pop}%': fmt_pop_plain(pop_pct(last['Revenue'], prev_r['Revenue'])),
            f'Vol {pop}%': fmt_pop_plain(pop_pct(last['Volume'], prev_r['Volume'])),
            'Latest GP':  fmt_idr(last['GP']),
            'Latest Rev': fmt_idr(last['Revenue']),
        })
if pop_rows:
    st.dataframe(pd.DataFrame(pop_rows), use_container_width=True, hide_index=True)

st.divider()

# ── Cost structure ────────────────────────────────────────────────────────────
st.subheader("Cost Structure by Team")
cost_cols  = [c for c in COST_COMPONENTS.keys() if c in df.columns]
cost_by_t  = df.groupby('Blitz Team', observed=True)[cost_cols].sum().reset_index()
cost_long  = cost_by_t.melt(id_vars='Blitz Team', var_name='Component', value_name='Amount')
cost_long['Label'] = cost_long['Component'].map(COST_COMPONENTS)
cost_long = cost_long[cost_long['Amount'] > 0]

fig_cost = px.bar(
    cost_long, x='Blitz Team', y='Amount', color='Label',
    barmode='stack', template='plotly_white', height=400,
    title="Cost Breakdown by Team", labels={'Amount': 'IDR', 'Label': 'Component'}
)
fig_cost.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.05))
st.plotly_chart(fig_cost, use_container_width=True)

rider_pct = (
    df.groupby('Blitz Team', observed=True)
    .apply(lambda g: g['Rider Cost'].sum() / g['Total Revenue'].sum() * 100
           if g['Total Revenue'].sum() else 0)
    .reset_index().rename(columns={0: 'Rider % of Revenue'})
)
r_cols = st.columns(max(len(rider_pct), 1))
for col, (_, row) in zip(r_cols, rider_pct.iterrows()):
    col.metric(f"{row['Blitz Team']} — Rider Cost %", fmt_pct(row['Rider % of Revenue']))

st.divider()

# ── SLA mix ───────────────────────────────────────────────────────────────────
st.subheader("SLA Type Mix by Team")
sla_t = (
    df.dropna(subset=['SLA Type'])
    .groupby(['Blitz Team', 'SLA Type'], observed=True)['Delivery Volume']
    .sum().reset_index()
)
fig_sla = px.bar(
    sla_t, x='Blitz Team', y='Delivery Volume', color='SLA Type',
    barmode='stack', template='plotly_white', height=360,
    title="Delivery Volume by SLA Type and Team",
    labels={'Delivery Volume': 'Deliveries'}
)
fig_sla.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.05))
st.plotly_chart(fig_sla, use_container_width=True)
