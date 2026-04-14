import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, pop_pct, pop_label, build_mobile_trend)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Mobile Period Performance | Blitz", page_icon="📅", layout="wide")
st.title("📅 Mobile Sellers — Period Performance")

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mobile_perf_view")
pop_label_val = pop_label(view_mode)

periods = get_available_periods(df_full, view_mode)
period_labels = [p[2] for p in periods]
label_map = {p[2]: (p[0], p[1]) for p in periods}

col_a, col_b = st.columns(2)
with col_b:
    lbl_b = st.selectbox("Period B (later)", period_labels[::-1], index=0, key="mobile_perf_b")
with col_a:
    prior_opts = [l for l in period_labels[::-1] if l != lbl_b]
    if prior_opts:
        lbl_a = st.selectbox("Period A (earlier)", prior_opts, index=0, key="mobile_perf_a")
    else:
        lbl_a = None
        st.info("Only one period available.")

yr_b, p_b = label_map[lbl_b]
df_b = filter_period(df_full, view_mode, yr_b, p_b)

if lbl_a:
    yr_a, p_a = label_map[lbl_a]
    df_a = filter_period(df_full, view_mode, yr_a, p_a)
else:
    yr_a, p_a = None, None
    df_a = pd.DataFrame()

st.caption(f"**{lbl_a or '—'}**  →  **{lbl_b}**")
st.divider()

# ── Headline KPIs ───────────────────────────────────────────────────────────────
st.subheader("Headline KPIs")

def get_kpi_val(df, col):
    if col == 'Total Active Riders':
        return df[col].max() if not df.empty else 0
    return df[col].sum() if not df.empty else 0

metrics_data = [
    ("Cups Sold", 'Total Cups Sold', fmt_vol),
    ("Gross Revenue", 'Gross Revenue', fmt_idr),
    ("Blitz Revenue", 'Blitz Revenue', fmt_idr),
    ("Profit", 'Profit Calc', fmt_idr),
    ("Riders", 'Total Active Riders', fmt_vol),
]

h0, h1, h2, h3, h4, h5 = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1])
h0.markdown("**Metric**")
h1.markdown(f"**{lbl_a or '—'}**")
h2.markdown(f"**{lbl_b}**")
h3.markdown(f"**Δ**")
h4.markdown(f"**Δ %**")
h5.markdown("")

for metric_label, col, formatter in metrics_data:
    val_a = get_kpi_val(df_a, col)
    val_b = get_kpi_val(df_b, col)
    delta = val_b - val_a
    delta_pct = pop_pct(val_b, val_a)

    c0, c1, c2, c3, c4, c5 = st.columns([2, 1.5, 1.5, 1.5, 1.5, 1])
    c0.write(metric_label)
    c1.write(formatter(val_a) if lbl_a else "—")
    c2.write(formatter(val_b))
    c3.write(f"{delta:+,.0f}" if lbl_a else "—")
    if lbl_a and delta_pct is not None:
        arrow = "▲" if delta_pct > 0 else "▼"
        color = "green" if delta_pct > 0 else "red"
        c4.markdown(f":{color}[{arrow} {abs(delta_pct):.1f}%]")
    else:
        c4.write("—")

st.divider()

# ── Client matrix: A vs B ───────────────────────────────────────────────────────
st.subheader("Client Comparison Matrix")

if lbl_a:
    agg_a = mobile_aggregate(df_a, ['Client Name'])
    agg_b = mobile_aggregate(df_b, ['Client Name'])
    merged = agg_a.merge(agg_b, on='Client Name', how='outer', suffixes=('_A', '_B')).fillna(0)

    merged['Cups_A'] = merged.get('Total Cups Sold_A', 0)
    merged['Cups_B'] = merged.get('Total Cups Sold_B', 0)
    merged['BlitzRev_A'] = merged.get('Blitz Revenue_A', 0)
    merged['BlitzRev_B'] = merged.get('Blitz Revenue_B', 0)
    merged['Profit_A'] = merged.get('Profit Calc_A', 0)
    merged['Profit_B'] = merged.get('Profit Calc_B', 0)
    merged['Profit_Change'] = merged['Profit_B'] - merged['Profit_A']
    merged['Profit_Change_Pct'] = np.where(
        merged['Profit_A'] != 0,
        (merged['Profit_B'] - merged['Profit_A']) / abs(merged['Profit_A']) * 100,
        0
    )

    disp = merged[['Client Name', 'Cups_A', 'Cups_B', 'BlitzRev_A', 'BlitzRev_B', 'Profit_A', 'Profit_B', 'Profit_Change_Pct']].copy()
    disp.columns = ['Client', f'Cups {lbl_a}', f'Cups {lbl_b}', f'BlitzRev {lbl_a}', f'BlitzRev {lbl_b}', f'Profit {lbl_a}', f'Profit {lbl_b}', 'Δ Profit %']

    for col in [f'Cups {lbl_a}', f'Cups {lbl_b}', f'BlitzRev {lbl_a}', f'BlitzRev {lbl_b}', f'Profit {lbl_a}', f'Profit {lbl_b}']:
        if col.startswith('Cups'):
            disp[col] = disp[col].apply(fmt_vol)
        else:
            disp[col] = disp[col].apply(fmt_idr)

    disp['Δ Profit %'] = disp['Δ Profit %'].apply(lambda x: f"▲ {x:.1f}%" if x > 0 else f"▼ {abs(x):.1f}%" if x < 0 else "—")

    st.dataframe(disp.sort_values('Client'), use_container_width=True, hide_index=True)
else:
    agg_b = mobile_aggregate(df_b, ['Client Name'])
    disp = agg_b[['Client Name', 'Total Cups Sold', 'Blitz Revenue', 'Profit Calc']].copy()
    disp.columns = ['Client', 'Cups Sold', 'Blitz Revenue', 'Profit']
    disp['Cups Sold'] = disp['Cups Sold'].apply(fmt_vol)
    disp['Blitz Revenue'] = disp['Blitz Revenue'].apply(fmt_idr)
    disp['Profit'] = disp['Profit'].apply(fmt_idr)
    st.dataframe(disp.sort_values('Client'), use_container_width=True, hide_index=True)

st.divider()

# ── Grouped bar: Profit by client A vs B ────────────────────────────────────────
if lbl_a and not merged.empty:
    st.subheader(f"Profit Comparison — Top 15 Clients")
    top_profit = merged.nlargest(15, 'Profit_B')
    chart_data = pd.DataFrame({
        'Client': list(top_profit['Client Name']) * 2,
        'Period': [lbl_a] * len(top_profit) + [lbl_b] * len(top_profit),
        'Profit': list(top_profit['Profit_A']) + list(top_profit['Profit_B']),
    })
    fig = px.bar(chart_data, x='Client', y='Profit', color='Period', barmode='group',
                 template='plotly_white', height=400,
                 color_discrete_map={lbl_a: '#90CAF9', lbl_b: C_GP})
    fig.update_layout(xaxis_tickangle=-45, hovermode='x unified', yaxis_title='IDR')
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Multi-period trend ──────────────────────────────────────────────────────────
st.subheader("Multi-Period Trend")
trend = build_mobile_trend(df_full, [], view_mode)
fig_trend = go.Figure()
fig_trend.add_scatter(x=trend['Label'], y=trend['Profit'], name='Profit',
                      line=dict(color=C_GP, width=2), mode='lines+markers')
fig_trend.add_scatter(x=trend['Label'], y=trend['Cups'], name='Cups Sold',
                      line=dict(color=C_VOLUME, width=2), mode='lines+markers', yaxis='y2')
fig_trend.update_layout(
    hovermode='x unified', template='plotly_white', height=400,
    yaxis_title='Profit (IDR)', yaxis2=dict(title='Cups', overlaying='y', side='right'),
    xaxis_tickangle=-45
)
st.plotly_chart(fig_trend, use_container_width=True)

st.divider()

# ── Single client drilldown ─────────────────────────────────────────────────────
st.subheader("Single Client — Full History")
all_clients = sorted(df_full['Client Name'].dropna().unique())
sel_client = st.selectbox("Select Client", all_clients, key="mobile_perf_client")

cdf = df_full[df_full['Client Name'] == sel_client]
if not cdf.empty:
    trend_client = build_mobile_trend(cdf, [], view_mode)
    fig_client = go.Figure()
    fig_client.add_bar(x=trend_client['Label'], y=trend_client['Profit'], name='Profit',
                       marker_color=C_GP, opacity=0.8, yaxis='y')
    fig_client.add_scatter(x=trend_client['Label'], y=trend_client['Cups'], name='Cups',
                           line=dict(color=C_VOLUME, width=2), mode='lines+markers', yaxis='y2')
    fig_client.update_layout(
        barmode='overlay', hovermode='x unified', template='plotly_white', height=400,
        yaxis_title='Profit (IDR)', yaxis2=dict(title='Cups', overlaying='y', side='right'),
        xaxis_tickangle=-45, legend=dict(orientation='h', y=1.05)
    )
    st.plotly_chart(fig_client, use_container_width=True)
