import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_GP, get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label,
                   apply_chart_theme, idr_col, vol_col, pct_col,
                   dataframe_with_freeze)
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

display = merged[['Client Location', 'Total Cups Sold', 'Blitz Revenue', 'Profit Calc', 'Total Active Riders', 'PoP%']].copy()
display.columns = ['Location', 'Cups', 'Blitz Revenue', 'Profit', 'Riders', 'PoP%']

display['Margin %'] = (merged['Profit Calc'] / merged['Gross Revenue'].replace(0, 1) * 100).fillna(0)

dataframe_with_freeze(
    display[['Location', 'Cups', 'Riders', 'Blitz Revenue', 'Profit', 'Margin %', 'PoP%']]
    .sort_values('Profit', ascending=False),
    key="mobile_location_rankings",
    default_freeze=['Location'],
    column_config={
        'Cups':           vol_col('Cups'),
        'Riders':         vol_col('Riders'),
        'Blitz Revenue':  idr_col('Blitz Revenue'),
        'Profit':         idr_col('Profit'),
        'Margin %':       pct_col('Margin', signed=False),
        'PoP%':           pct_col('PoP%', signed=True),
    },
    width="stretch", hide_index=True,
)

st.divider()

# ── Horizontal bar: Profit by location ──────────────────────────────────────────
st.subheader("Profit by Location")
loc_profit = merged[['Client Location', 'Profit Calc']].sort_values('Profit Calc', ascending=True)
fig_loc = px.bar(loc_profit, y='Client Location', x='Profit Calc', orientation='h',
                 color='Profit Calc', color_continuous_scale='greens',
                 height=max(300, len(loc_profit) * 25),
                 labels={'Profit Calc': 'Profit (IDR)'})
apply_chart_theme(fig_loc)
st.plotly_chart(fig_loc, width="stretch")
