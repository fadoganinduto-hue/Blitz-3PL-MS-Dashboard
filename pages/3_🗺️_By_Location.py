import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_trend)

st.set_page_config(page_title="By Location | Blitz", page_icon="🗺️", layout="wide")
st.title("🗺️ By Location")
st.caption("Location performance, period-over-period variance, and trend analysis.")

df_full = require_data()
df = sidebar_filters(df_full, page_key="locs")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode selector ───────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="loc_view")
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

curr_loc = curr_df.groupby('Client Location', observed=True).agg(
    GP=('GP', 'sum'), Revenue=('Total Revenue', 'sum'), Volume=('Delivery Volume', 'sum')
).reset_index()

if not prev_df.empty:
    prev_loc = (prev_df.groupby('Client Location', observed=True)['GP']
                .sum().reset_index().rename(columns={'GP': 'GP_prev'}))
else:
    prev_loc = pd.DataFrame(columns=['Client Location', 'GP_prev'])

lw_loc = curr_loc.merge(prev_loc, on='Client Location', how='left').fillna(0)
lw_loc[f'GP {pop} %'] = lw_loc.apply(lambda r: pop_pct(r['GP'], r['GP_prev']), axis=1)
lw_loc = lw_loc.sort_values('GP', ascending=False)

def fmt_delta(v):
    if v is None or pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"

disp_lw = lw_loc.copy()
disp_lw['Revenue']       = disp_lw['Revenue'].apply(fmt_idr)
disp_lw['GP']            = disp_lw['GP'].apply(fmt_idr)
disp_lw['Volume']        = disp_lw['Volume'].apply(fmt_vol)
disp_lw[f'GP {pop} %']  = disp_lw[f'GP {pop} %'].apply(fmt_delta)
st.dataframe(
    disp_lw[['Client Location', 'Volume', 'Revenue', 'GP', f'GP {pop} %']],
    use_container_width=True, hide_index=True
)

st.divider()

# ── Period rankings ───────────────────────────────────────────────────────────
st.subheader("Period Rankings (all filtered data)")

loc_agg = (
    df.groupby('Client Location', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
    .reset_index()
)
loc_agg['GP Margin %'] = np.where(loc_agg['Revenue'] != 0, loc_agg['GP'] / loc_agg['Revenue'] * 100, 0)
loc_agg = loc_agg.sort_values('GP', ascending=False)

fig_rank = px.bar(
    loc_agg.sort_values('GP'), x='GP', y='Client Location', orientation='h',
    color='GP', color_continuous_scale=['red', 'yellow', 'green'],
    template='plotly_white', height=max(350, len(loc_agg) * 28),
    title="Gross Profit by Location (Period)",
    labels={'GP': 'Gross Profit (IDR)', 'Client Location': ''}
)
fig_rank.add_vline(x=0, line_dash='dash', line_color='grey')
fig_rank.update_coloraxes(showscale=False)
st.plotly_chart(fig_rank, use_container_width=True)

disp_all = loc_agg.copy()
for col in ['Revenue', 'Cost', 'GP']:
    disp_all[col] = disp_all[col].apply(fmt_idr)
disp_all['GP Margin %'] = disp_all['GP Margin %'].apply(fmt_pct)
disp_all['Volume']      = disp_all['Volume'].apply(fmt_vol)
st.dataframe(
    disp_all[['Client Location', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %']],
    use_container_width=True, hide_index=True
)

st.divider()

# ── Location drilldown ────────────────────────────────────────────────────────
st.subheader("Location Drilldown")
sel_loc = st.selectbox("Select a location", sorted(df['Client Location'].dropna().unique()))
loc_df  = df[df['Client Location'] == sel_loc].copy()

lk1, lk2, lk3, lk4 = st.columns(4)
lk1.metric("Revenue", fmt_idr(loc_df['Total Revenue'].sum()))
lk2.metric("Cost",    fmt_idr(loc_df['Total Cost'].sum()))
lk3.metric("GP",      fmt_idr(loc_df['GP'].sum()))
gpm = loc_df['GP'].sum() / loc_df['Total Revenue'].sum() * 100 if loc_df['Total Revenue'].sum() else 0
lk4.metric("Margin",  fmt_pct(gpm))

# Trend follows the same view_mode
trend_l = build_trend(loc_df, [], view_mode)
for m in ['Revenue', 'GP', 'Volume']:
    trend_l[f'{m} PoP%'] = trend_l[m].pct_change() * 100

fig_l = go.Figure()
fig_l.add_bar(x=trend_l['Label'], y=trend_l['Revenue'], name='Revenue',
              marker_color=C_REVENUE, opacity=0.8)
fig_l.add_bar(x=trend_l['Label'], y=trend_l['Cost'],    name='Cost',
              marker_color=C_COST, opacity=0.8)
fig_l.add_scatter(x=trend_l['Label'], y=trend_l['GP'], mode='lines+markers',
                  name='GP', line=dict(color=C_GP, width=2))
fig_l.update_layout(barmode='group', hovermode='x unified', template='plotly_white',
                    height=400, legend=dict(orientation='h', y=1.05), yaxis_title='IDR',
                    xaxis_tickangle=-45, title=f"{sel_loc} — {view_mode} Trend")
st.plotly_chart(fig_l, use_container_width=True)

def fmt_pop_plain(v):
    if pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"

disp_loc = trend_l.copy()
for col in ['Revenue', 'Cost', 'GP']:
    disp_loc[col] = disp_loc[col].apply(fmt_idr)
disp_loc['Volume']    = disp_loc['Volume'].apply(fmt_vol)
disp_loc['Rev PoP%']  = disp_loc['Revenue PoP%'].apply(fmt_pop_plain)
disp_loc['GP PoP%']   = disp_loc['GP PoP%'].apply(fmt_pop_plain)
disp_loc['Vol PoP%']  = disp_loc['Volume PoP%'].apply(fmt_pop_plain)
st.dataframe(
    disp_loc[['Label', 'Volume', 'Vol PoP%', 'Revenue', 'Rev PoP%',
              'Cost', 'GP', 'GP PoP%']],
    use_container_width=True, hide_index=True
)
