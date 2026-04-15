import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (require_mobile_data, fmt_idr, fmt_vol,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_mobile_trend)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile By Team | Blitz", page_icon="🏙️", layout="wide")
st.title("🏙️ Mobile Sellers — By Team")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mobile_team_view")
pop_lbl = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df_full, view_mode, curr_yr, curr_p)
prev_df = filter_period(df_full, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

st.caption(f"Latest period: {curr_lbl}")

# ── Team summary table ──────────────────────────────────────────────────────────
st.subheader("Team Summary")

agg_curr = mobile_aggregate(curr_df, ['Blitz Team'])
agg_prev = mobile_aggregate(prev_df, ['Blitz Team']) if not prev_df.empty else pd.DataFrame()

if not agg_prev.empty:
    merged = agg_curr.merge(agg_prev, on='Blitz Team', how='left', suffixes=('', '_prev')).fillna(0)
    merged['PoP%'] = merged.apply(
        lambda r: pop_pct(r['Profit Calc'], r.get('Profit Calc_prev', 0)) if r.get('Profit Calc_prev', 0) != 0 else None,
        axis=1
    )
else:
    merged = agg_curr.copy()
    merged['PoP%'] = None

display = merged.copy()
n_clients = merged['Blitz Team'].apply(lambda t: len(df_full[df_full['Blitz Team'] == t]['Client Name'].unique()))
display = display.rename(columns={'Blitz Team': 'Team'})
display['# Clients'] = n_clients.values
display['Cups'] = display['Total Cups Sold'].apply(fmt_vol)
display['Blitz Revenue'] = display['Blitz Revenue'].apply(fmt_idr)
display['Profit'] = display['Profit Calc'].apply(fmt_idr)
display['PoP%'] = merged['PoP%'].apply(lambda x: f"▲ {x:.1f}%" if x and x > 0 else f"▼ {abs(x):.1f}%" if x and x < 0 else "—")

st.dataframe(display[['Team', '# Clients', 'Cups', 'Blitz Revenue', 'Profit', 'PoP%']].sort_values('Team'),
             use_container_width=True, hide_index=True)

st.divider()

# ── Stacked bar: Profit by team across last 6 periods ─────────────────────────
st.subheader("Profit by Team — Last 6 Periods")

trend_all = build_mobile_trend(df_full, ['Blitz Team'], view_mode)
trend_6 = trend_all[trend_all['Label'].isin(trend_all['Label'].tail(6).unique())].copy()

fig_stack = px.bar(
    trend_6, x='Label', y='Profit', color='Blitz Team',
    barmode='stack', template='plotly_white', height=400,
    labels={'Profit': 'Profit (IDR)', 'Label': 'Period'}
)
fig_stack.update_layout(xaxis_tickangle=-45, hovermode='x unified', legend=dict(orientation='h', y=1.05))
st.plotly_chart(fig_stack, use_container_width=True)
