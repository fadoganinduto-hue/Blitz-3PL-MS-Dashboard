import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_GP, get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile By Location | Blitz", page_icon="🗺️", layout="wide")
st.title("🗺️ Mobile Sellers — By Location")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mobile_loc_view")
pop_lbl = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df_full, view_mode, curr_yr, curr_p)
prev_df = filter_period(df_full, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

st.caption(f"Latest period: {curr_lbl}")

# ── Ranked table by location ────────────────────────────────────────────────────
st.subheader("Location Rankings")

agg_curr = mobile_aggregate(curr_df, ['Client Location'])
agg_prev = mobile_aggregate(prev_df, ['Client Location']) if not prev_df.empty else pd.DataFrame()

if not agg_prev.empty:
    merged = agg_curr.merge(agg_prev, on='Client Location', how='left', suffixes=('', '_prev')).fillna(0)
    merged['PoP%'] = merged.apply(
        lambda r: pop_pct(r['Profit Calc'], r.get('Profit Calc_prev', 0)) if r.get('Profit Calc_prev', 0) != 0 else None,
        axis=1
    )
else:
    merged = agg_curr.copy()
    merged['PoP%'] = None

display = merged[['Client Location', 'Total Cups Sold', 'Blitz Revenue', 'Profit Calc', 'Total Active Riders']].copy()
display.columns = ['Location', 'Cups', 'Blitz Revenue', 'Profit', 'Riders']

profit_margin = (merged['Profit Calc'] / merged['Gross Revenue'].replace(0, 1) * 100).fillna(0)
display['Profit'] = merged['Profit Calc'].apply(fmt_idr)
display['Margin %'] = profit_margin.apply(fmt_pct)
display['Cups'] = display['Cups'].apply(fmt_vol)
display['Blitz Revenue'] = display['Blitz Revenue'].apply(fmt_idr)
display['Riders'] = display['Riders'].apply(fmt_vol)
display['PoP%'] = merged['PoP%'].apply(lambda x: f"▲ {x:.1f}%" if x and x > 0 else f"▼ {abs(x):.1f}%" if x and x < 0 else "—")

st.dataframe(display.sort_values('Location'), use_container_width=True, hide_index=True)

st.divider()

# ── Horizontal bar: Profit by location ──────────────────────────────────────────
st.subheader("Profit by Location")
loc_profit = merged[['Client Location', 'Profit Calc']].sort_values('Profit Calc', ascending=True)
fig_loc = px.bar(loc_profit, y='Client Location', x='Profit Calc', orientation='h',
                 color='Profit Calc', color_continuous_scale='greens',
                 template='plotly_white', height=max(300, len(loc_profit) * 25),
                 labels={'Profit Calc': 'Profit (IDR)'})
st.plotly_chart(fig_loc, use_container_width=True)
