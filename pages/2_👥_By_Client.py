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

st.set_page_config(page_title="By Client | Blitz", page_icon="👥", layout="wide")
st.title("👥 By Client")
st.caption("Per-client P&L rankings, unit economics, and drilldown.")

df_full = require_data()
df = sidebar_filters(df_full, page_key="client")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode selector ───────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="client_view")
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
    st.subheader(f"Latest Week Snapshot — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month Snapshot — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")

lw_agg = (
    curr_df.groupby('Client Name', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
    .reset_index()
)
if not prev_df.empty:
    pw_agg = (
        prev_df.groupby('Client Name', observed=True)
        .agg(GP_prev=('GP', 'sum'), Revenue_prev=('Total Revenue', 'sum'))
        .reset_index()
    )
else:
    pw_agg = pd.DataFrame(columns=['Client Name', 'GP_prev', 'Revenue_prev'])

lw = lw_agg.merge(pw_agg, on='Client Name', how='left').fillna(0)
lw['GP Margin %'] = np.where(lw['Revenue'] != 0, lw['GP'] / lw['Revenue'] * 100, 0)
lw[f'GP {pop} %'] = lw.apply(lambda r: pop_pct(r['GP'], r['GP_prev']), axis=1)
lw = lw.sort_values('GP', ascending=False).reset_index(drop=True)

def fmt_delta(v):
    if v is None or pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"

disp_lw = lw.copy()
disp_lw['Revenue']      = disp_lw['Revenue'].apply(fmt_idr)
disp_lw['Cost']         = disp_lw['Cost'].apply(fmt_idr)
disp_lw['GP']           = disp_lw['GP'].apply(fmt_idr)
disp_lw['Margin']       = disp_lw['GP Margin %'].apply(fmt_pct)
disp_lw['Volume']       = disp_lw['Volume'].apply(fmt_vol)
disp_lw[f'GP {pop} %'] = disp_lw[f'GP {pop} %'].apply(fmt_delta)
st.dataframe(
    disp_lw[['Client Name', 'Volume', 'Revenue', 'Cost', 'GP', 'Margin', f'GP {pop} %']],
    use_container_width=True, hide_index=True, height=400
)

st.divider()

# ── Period rankings ───────────────────────────────────────────────────────────
st.subheader("Period Rankings (all filtered data)")
sort_col = st.selectbox("Sort by", ['GP', 'Revenue', 'Volume', 'GP Margin %'], index=0)

client_agg = (
    df.groupby('Client Name', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
    .reset_index()
)
client_agg['GP Margin %'] = np.where(
    client_agg['Revenue'] != 0, client_agg['GP'] / client_agg['Revenue'] * 100, 0
)
client_agg = client_agg.sort_values(sort_col, ascending=False).reset_index(drop=True)

disp_all = client_agg.copy()
disp_all['Revenue']     = disp_all['Revenue'].apply(fmt_idr)
disp_all['Cost']        = disp_all['Cost'].apply(fmt_idr)
disp_all['GP']          = disp_all['GP'].apply(fmt_idr)
disp_all['GP Margin %'] = disp_all['GP Margin %'].apply(fmt_pct)
disp_all['Volume']      = disp_all['Volume'].apply(fmt_vol)
st.dataframe(
    disp_all[['Client Name', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %']],
    use_container_width=True, hide_index=True
)

st.divider()

# ── Client drilldown ──────────────────────────────────────────────────────────
st.subheader("Client Drilldown")
sel_client = st.selectbox("Select a client", sorted(df['Client Name'].dropna().unique()))
cdf = df[df['Client Name'] == sel_client].copy()

if cdf.empty:
    st.stop()

ck1, ck2, ck3, ck4 = st.columns(4)
ck1.metric("Revenue",  fmt_idr(cdf['Total Revenue'].sum()))
ck2.metric("Cost",     fmt_idr(cdf['Total Cost'].sum()))
ck3.metric("GP",       fmt_idr(cdf['GP'].sum()))
gpm = cdf['GP'].sum() / cdf['Total Revenue'].sum() * 100 if cdf['Total Revenue'].sum() else 0
ck4.metric("Margin",   fmt_pct(gpm))

# Trend + drilldown table (follows the same view_mode chosen at top)
trend_c = build_trend(cdf, [], view_mode)
trend_c['GP Margin %'] = np.where(
    trend_c['Revenue'] != 0, trend_c['GP'] / trend_c['Revenue'] * 100, 0
)
for m in ['Revenue', 'GP', 'Volume']:
    trend_c[f'{m} PoP%'] = trend_c[m].pct_change() * 100

fig = go.Figure()
fig.add_bar(x=trend_c['Label'], y=trend_c['Revenue'], name='Revenue',
            marker_color=C_REVENUE, opacity=0.8)
fig.add_bar(x=trend_c['Label'], y=trend_c['Cost'],    name='Cost',
            marker_color=C_COST, opacity=0.8)
fig.add_scatter(x=trend_c['Label'], y=trend_c['GP'], mode='lines+markers',
                name='GP', line=dict(color=C_GP, width=2))
fig.update_layout(barmode='group', hovermode='x unified', template='plotly_white',
                  height=400, legend=dict(orientation='h', y=1.05), yaxis_title='IDR',
                  xaxis_tickangle=-45, title=f"{sel_client} — {view_mode} P&L")
st.plotly_chart(fig, use_container_width=True)

def fmt_pop_plain(v):
    if pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"

disp_drill = trend_c.copy()
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
    use_container_width=True, hide_index=True
)

# Cost structure pie
cost_data = {label: cdf[col].sum() for col, label in COST_COMPONENTS.items()
             if col in cdf.columns and cdf[col].sum() > 0}
if cost_data:
    cost_df = pd.DataFrame({'Component': list(cost_data.keys()), 'Amount': list(cost_data.values())})
    fig_cost = px.pie(cost_df, values='Amount', names='Component', hole=0.35,
                      template='plotly_white', height=360,
                      title=f"{sel_client} — Cost Structure")
    st.plotly_chart(fig_cost, use_container_width=True)
