import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (require_mobile_data, fmt_idr, fmt_vol,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, period_selector, build_mobile_trend,
                   apply_chart_theme, idr_col, vol_col, pct_col,
                   dataframe_with_freeze)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile By Team | Blitz", page_icon="🏙️", layout="wide")
st.title("🏙️ Mobile Sellers — By Team")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

view_mode = period_selector(page_key="mobile_team")
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

# Select-then-rename to avoid collision: mobile_aggregate sums the source
# 'Profit' column, which clashes with renaming 'Profit Calc' → 'Profit'.
display = merged[['Blitz Team', 'Total Cups Sold', 'Blitz Revenue',
                  'Profit Calc', 'PoP%']].rename(
    columns={'Blitz Team': 'Team', 'Total Cups Sold': 'Cups', 'Profit Calc': 'Profit'}
).copy()
display['# Clients'] = merged['Blitz Team'].apply(
    lambda t: df_full[df_full['Blitz Team'] == t]['Client Name'].nunique()
).values

dataframe_with_freeze(
    display[['Team', '# Clients', 'Cups', 'Blitz Revenue', 'Profit', 'PoP%']].sort_values('Team'),
    key="mobile_team_summary",
    default_freeze=['Team'],
    column_config={
        '# Clients':      vol_col('# Clients'),
        'Cups':           vol_col('Cups'),
        'Blitz Revenue':  idr_col('Blitz Revenue'),
        'Profit':         idr_col('Profit'),
        'PoP%':           pct_col('PoP%', signed=True),
    },
    width="stretch", hide_index=True,
)

st.divider()

# ── Stacked bar: Profit by team across last 6 periods ─────────────────────────
st.subheader("Profit by Team — Last 6 Periods")

trend_all = build_mobile_trend(df_full, ['Blitz Team'], view_mode)
trend_6 = trend_all[trend_all['Label'].isin(trend_all['Label'].tail(6).unique())].copy()

fig_stack = px.bar(
    trend_6, x='Label', y='Profit', color='Blitz Team',
    barmode='stack', height=400,
    labels={'Profit': 'Profit (IDR)', 'Label': 'Period'},
)
fig_stack.update_layout(xaxis_tickangle=-45)
apply_chart_theme(fig_stack)
st.plotly_chart(fig_stack, width="stretch")

st.divider()

# ── Client breakdown by team ─────────────────────────────────────────────────
st.subheader("Clients by Team")
st.caption("Which clients fall under each team, with key metrics for the selected period.")

teams = sorted(df_full['Blitz Team'].dropna().unique().tolist())
for team in teams:
    team_df = curr_df[curr_df['Blitz Team'] == team]
    if team_df.empty:
        continue

    client_agg = mobile_aggregate(team_df, ['Client Name'])
    client_agg = client_agg.sort_values('Profit Calc', ascending=False)

    # PoP%
    if not prev_df.empty:
        prev_team_df = prev_df[prev_df['Blitz Team'] == team]
        prev_client = mobile_aggregate(prev_team_df, ['Client Name'])
        if not prev_client.empty:
            prev_client = prev_client[['Client Name', 'Profit Calc']].rename(columns={'Profit Calc': 'Profit_prev'})
            client_agg = client_agg.merge(prev_client, on='Client Name', how='left').fillna(0)
            client_agg[f'Profit {pop_lbl}%'] = client_agg.apply(
                lambda r: pop_pct(r['Profit Calc'], r['Profit_prev']) if r.get('Profit_prev', 0) != 0 else None, axis=1
            )
        else:
            client_agg[f'Profit {pop_lbl}%'] = None
    else:
        client_agg[f'Profit {pop_lbl}%'] = None

    with st.expander(f"🏙️ {team} — {len(client_agg)} clients", expanded=True):
        pop_col = f'Profit {pop_lbl}%'
        # Select-then-rename so the source 'Profit' column doesn't collide with
        # the 'Profit Calc' → 'Profit' rename.
        src_cols = [c for c in ['Client Name', 'Total Cups Sold', 'Total Active Riders',
                                'Blitz Revenue', 'Profit Calc', pop_col]
                    if c in client_agg.columns]
        display_cl = client_agg[src_cols].rename(columns={
            'Total Cups Sold': 'Cups',
            'Total Active Riders': 'Riders',
            'Blitz Revenue': 'Blitz Rev',
            'Profit Calc': 'Profit',
        }).copy()
        show_cols = [c for c in ['Client Name', 'Cups', 'Riders', 'Blitz Rev', 'Profit', pop_col]
                     if c in display_cl.columns]
        dataframe_with_freeze(
            display_cl[show_cols],
            key=f"mobile_team_clients_{team}",
            default_freeze=['Client Name'],
            column_config={
                'Cups':       vol_col('Cups'),
                'Riders':     vol_col('Riders'),
                'Blitz Rev':  idr_col('Blitz Rev'),
                'Profit':     idr_col('Profit'),
                pop_col:      pct_col(pop_col, signed=True),
            },
            width="stretch", hide_index=True,
        )
