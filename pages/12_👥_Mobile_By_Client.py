import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_mobile_trend)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile By Client | Blitz", page_icon="👥", layout="wide")
st.title("👥 Mobile Sellers — By Client")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mobile_client_view")
pop_lbl = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df_full, view_mode, curr_yr, curr_p)
prev_df = filter_period(df_full, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

st.caption(f"Latest period: {curr_lbl}")

# ── Ranked table ────────────────────────────────────────────────────────────────
st.subheader("Client Rankings")

agg_curr = mobile_aggregate(curr_df, ['Client Name'])
agg_prev = mobile_aggregate(prev_df, ['Client Name']) if not prev_df.empty else pd.DataFrame()

if not agg_prev.empty:
    merged = agg_curr.merge(agg_prev, on='Client Name', how='left', suffixes=('', '_prev')).fillna(0)
    merged['PoP%'] = merged.apply(
        lambda r: pop_pct(r['Profit Calc'], r.get('Profit Calc_prev', 0)) if r.get('Profit Calc_prev', 0) != 0 else None,
        axis=1
    )
else:
    merged = agg_curr.copy()
    merged['PoP%'] = None

display = merged[['Client Name', 'Total Cups Sold', 'Gross Revenue', 'Blitz Revenue', 'Profit Calc', 'Total Active Riders']].copy()
display.columns = ['Client', 'Cups', 'Gross Revenue', 'Blitz Revenue', 'Profit', 'Riders']
display['Cups'] = display['Cups'].apply(fmt_vol)
display['Gross Revenue'] = display['Gross Revenue'].apply(fmt_idr)
display['Blitz Revenue'] = display['Blitz Revenue'].apply(fmt_idr)
display['Profit'] = display['Profit'].apply(fmt_idr)
display['Riders'] = display['Riders'].apply(fmt_vol)
display['PoP%'] = merged['PoP%'].apply(lambda x: f"▲ {x:.1f}%" if x and x > 0 else f"▼ {abs(x):.1f}%" if x and x < 0 else "—")

st.dataframe(display.sort_values('Client'), use_container_width=True, hide_index=True)

st.divider()

# ── Top 10 Profit bar chart ─────────────────────────────────────────────────────
st.subheader("Top 10 Clients by Profit")
top_profit = merged.nlargest(10, 'Profit Calc')[['Client Name', 'Profit Calc']]
fig_profit = px.bar(top_profit, y='Client Name', x='Profit Calc', orientation='h',
                    color='Profit Calc', color_continuous_scale='greens',
                    template='plotly_white', height=380,
                    labels={'Profit Calc': 'Profit (IDR)'})
fig_profit.update_layout(yaxis={'categoryorder': 'total ascending'})
st.plotly_chart(fig_profit, use_container_width=True)

st.divider()

# ── Blitz Revenue pie chart ─────────────────────────────────────────────────────
st.subheader("Blitz Revenue Mix")
brev_dist = merged[['Client Name', 'Blitz Revenue']].copy()
brev_dist = brev_dist.sort_values('Blitz Revenue', ascending=False)
top15 = brev_dist.head(15)
others = brev_dist.iloc[15:]['Blitz Revenue'].sum()
if others > 0:
    top15 = pd.concat([top15, pd.DataFrame([{'Client Name': 'Others', 'Blitz Revenue': others}])], ignore_index=True)

fig_pie = px.pie(top15, values='Blitz Revenue', names='Client Name', hole=0.4,
                 template='plotly_white', height=420)
fig_pie.update_traces(textposition='inside', textinfo='percent+label')
st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ── Drilldown: single client 12-period trend ────────────────────────────────────
st.subheader("Single Client — 12-Period Trend")
all_clients = sorted(df_full['Client Name'].dropna().unique())
sel_client = st.selectbox("Select Client", all_clients, key="mobile_client_drill")

cdf = df_full[df_full['Client Name'] == sel_client]
if not cdf.empty:
    trend_client = build_mobile_trend(cdf, [], view_mode)
    trend_12 = trend_client.tail(12)

    fig_drill = px.bar(trend_12, x='Label', y='Profit', color='Profit',
                       color_continuous_scale='blues', template='plotly_white', height=380,
                       labels={'Profit': 'Profit (IDR)', 'Label': 'Period'})
    fig_drill.update_layout(xaxis_tickangle=-45, hovermode='x unified')
    st.plotly_chart(fig_drill, use_container_width=True)
