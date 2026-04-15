import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label)

st.set_page_config(page_title="Period Performance | Blitz", page_icon="📅", layout="wide")
st.title("📅 Period Performance")
st.caption(
    "Side-by-side comparison of any two periods — consecutive weeks, consecutive months, "
    "or the same month across years (e.g. Jan 2025 vs Jan 2026)."
)

df_full = require_data()
df = sidebar_filters(df_full, page_key="period_perf")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode + selectors ───────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="pp_view")
pop = pop_label(view_mode)

periods = get_available_periods(df, view_mode)
period_labels = [p[2] for p in periods]
label_map = {p[2]: (p[0], p[1]) for p in periods}

col_a, col_b = st.columns(2)
with col_b:
    # "Current" — latest by default
    curr_label = st.selectbox("Period B (current / later)", period_labels[::-1], index=0)
with col_a:
    prior_options = [lbl for lbl in period_labels[::-1] if lbl != curr_label]
    if prior_options:
        # Default to the period immediately before Period B
        curr_idx = period_labels.index(curr_label)
        default_prior_idx = 0 if curr_idx == 0 else 0  # first in reversed list
        prior_label = st.selectbox(
            "Period A (compare / earlier)", prior_options,
            index=0,
            help="Pick any earlier period — consecutive or year-over-year"
        )
    else:
        st.info("No earlier period available for comparison.")
        prior_label = None

curr_yr, curr_p   = label_map[curr_label]
curr_df = filter_period(df, view_mode, curr_yr, curr_p)

if prior_label:
    prior_yr, prior_p = label_map[prior_label]
    prior_df = filter_period(df, view_mode, prior_yr, prior_p)
else:
    prior_yr, prior_p = None, None
    prior_df = pd.DataFrame()

if view_mode == "Weekly":
    date_a = prior_df['Date Range'].dropna().iloc[0] if (prior_label and not prior_df['Date Range'].dropna().empty) else ''
    date_b = curr_df['Date Range'].dropna().iloc[0]  if not curr_df['Date Range'].dropna().empty else ''
    st.caption(f"**A:** {prior_label or '—'}  ·  {date_a}  →  **B:** {curr_label}  ·  {date_b}")
else:
    st.caption(f"**A:** {prior_label or '—'}  →  **B:** {curr_label}")

st.divider()


# ── Headline KPIs — both periods side by side ─────────────────────────────────
def period_totals(d):
    if d.empty:
        return dict(Revenue=0, Cost=0, GP=0, Volume=0)
    return dict(
        Revenue=d['Total Revenue'].sum(),
        Cost=d['Total Cost'].sum(),
        GP=(d['Total Revenue'] - d['Total Cost']).sum(),
        Volume=d['Delivery Volume'].sum(),
    )

tot_a = period_totals(prior_df)
tot_b = period_totals(curr_df)

metric_labels = {'Revenue': fmt_idr, 'Cost': fmt_idr, 'GP': fmt_idr, 'Volume': fmt_vol}

kpi_cols = st.columns(len(metric_labels))
for col, (metric, fmt_fn) in zip(kpi_cols, metric_labels.items()):
    va, vb = tot_a[metric], tot_b[metric]
    delta  = pop_pct(vb, va)
    arrow  = ("▲ " if delta >= 0 else "▼ ") if delta is not None else ""
    delta_str = f"{arrow}{abs(delta):.1f}% {pop}" if delta is not None else None
    col.metric(
        label=metric,
        value=f"{fmt_fn(vb)}",
        delta=delta_str,
        delta_color=("normal" if metric != "Cost" else "inverse")
    )
    col.caption(f"A: {fmt_fn(va)}")

st.divider()


# ── Helper: build client summary for a given period dataframe ─────────────────
def period_summary(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame()
    agg = (
        d.groupby('Client Name', observed=True)
        .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
             Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
        .reset_index()
    )
    agg['GP Margin %'] = np.where(agg['Revenue'] != 0, agg['GP'] / agg['Revenue'] * 100, 0)
    return agg


def fmt_pop(val):
    if val is None or pd.isna(val):
        return "—"
    arrow = "▲" if val > 0 else "▼"
    color_tag = "green" if val > 0 else "red"
    return f":{color_tag}[{arrow} {abs(val):.1f}%]"


curr_summary  = period_summary(curr_df)
prior_summary = period_summary(prior_df)

# Merge so every client appears even if only in one period
if not prior_summary.empty:
    merged = curr_summary.merge(
        prior_summary, on='Client Name', how='outer', suffixes=('_b', '_a')
    ).fillna(0)
else:
    merged = curr_summary.rename(columns={
        'Volume': 'Volume_b', 'Revenue': 'Revenue_b',
        'Cost': 'Cost_b', 'GP': 'GP_b', 'GP Margin %': 'GP Margin %_b'
    })
    for col in ['Volume_a', 'Revenue_a', 'Cost_a', 'GP_a', 'GP Margin %_a']:
        merged[col] = 0.0

for m in ['Volume', 'Revenue', 'GP']:
    merged[f'{m}_pop'] = merged.apply(
        lambda r, c=m: pop_pct(r[f'{c}_b'], r[f'{c}_a']), axis=1
    )
merged = merged.sort_values('GP_b', ascending=False).reset_index(drop=True)


# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Side-by-Side Comparison", "📈 GP Trend", "🔍 Single Client History"])


# ── Tab 1: Side-by-side matrix ────────────────────────────────────────────────
with tab1:
    lbl_a = prior_label or "Period A"
    lbl_b = curr_label

    st.subheader(f"{lbl_a}  →  {lbl_b}")

    # Build wide comparison table
    rows = []
    for _, r in merged.iterrows():
        row = {
            'Client': r['Client Name'],
            # Volume
            f'Vol ({lbl_a})':  fmt_vol(r['Volume_a']),
            f'Vol ({lbl_b})':  fmt_vol(r['Volume_b']),
            'Vol Δ':            fmt_pop(r['Volume_pop']),
            # Revenue
            f'Rev ({lbl_a})':  fmt_idr(r['Revenue_a']),
            f'Rev ({lbl_b})':  fmt_idr(r['Revenue_b']),
            'Rev Δ':            fmt_pop(r['Revenue_pop']),
            # GP
            f'GP ({lbl_a})':   fmt_idr(r['GP_a']),
            f'GP ({lbl_b})':   fmt_idr(r['GP_b']),
            'GP Δ':             fmt_pop(r['GP_pop']),
            # Margin
            f'Margin ({lbl_a})': fmt_pct(r.get('GP Margin %_a', 0)),
            f'Margin ({lbl_b})': fmt_pct(r.get('GP Margin %_b', 0)),
        }
        rows.append(row)

    disp_df = pd.DataFrame(rows)
    st.dataframe(disp_df, use_container_width=True, hide_index=True, height=520)

    st.markdown("---")

    # GP comparison chart — grouped bars A vs B
    chart_data = merged.copy()
    chart_data = chart_data.sort_values('GP_b', ascending=True)
    fig_gp = go.Figure()
    fig_gp.add_bar(
        x=chart_data['GP_a'], y=chart_data['Client Name'],
        name=lbl_a, orientation='h',
        marker_color='#90CAF9', opacity=0.9,
        hovertemplate='%{y}<br>GP: Rp %{x:,.0f}<extra>' + lbl_a + '</extra>'
    )
    fig_gp.add_bar(
        x=chart_data['GP_b'], y=chart_data['Client Name'],
        name=lbl_b, orientation='h',
        marker_color=C_GP, opacity=0.9,
        hovertemplate='%{y}<br>GP: Rp %{x:,.0f}<extra>' + lbl_b + '</extra>'
    )
    fig_gp.add_vline(x=0, line_dash='dash', line_color='grey')
    fig_gp.update_layout(
        barmode='group', template='plotly_white',
        height=max(420, len(chart_data) * 28),
        legend=dict(orientation='h', y=1.02),
        xaxis_title='Gross Profit (IDR)',
        yaxis_title='', yaxis={'categoryorder': 'total ascending'},
        title=f"GP Comparison — {lbl_a} vs {lbl_b}"
    )
    st.plotly_chart(fig_gp, use_container_width=True)

    # Revenue comparison
    fig_rev = go.Figure()
    fig_rev.add_bar(
        x=chart_data['Revenue_a'], y=chart_data['Client Name'],
        name=lbl_a, orientation='h', marker_color='#90CAF9', opacity=0.9
    )
    fig_rev.add_bar(
        x=chart_data['Revenue_b'], y=chart_data['Client Name'],
        name=lbl_b, orientation='h', marker_color=C_REVENUE, opacity=0.9
    )
    fig_rev.update_layout(
        barmode='group', template='plotly_white',
        height=max(420, len(chart_data) * 28),
        legend=dict(orientation='h', y=1.02),
        xaxis_title='Revenue (IDR)',
        yaxis_title='', yaxis={'categoryorder': 'total ascending'},
        title=f"Revenue Comparison — {lbl_a} vs {lbl_b}"
    )
    st.plotly_chart(fig_rev, use_container_width=True)


# ── Tab 2: Multi-period GP trend ──────────────────────────────────────────────
with tab2:
    st.subheader(f"GP Trend — Last N {'Weeks' if view_mode == 'Weekly' else 'Months'}")

    n_periods = st.slider(
        f"Show last N {'weeks' if view_mode == 'Weekly' else 'months'}",
        min_value=4, max_value=len(periods), value=min(12, len(periods)), step=1
    )
    selected_periods = periods[-n_periods:]

    trend_frames = [filter_period(df, view_mode, yr, p) for yr, p, _ in selected_periods]
    trend_df = pd.concat(trend_frames, ignore_index=True) if trend_frames else pd.DataFrame()

    if not trend_df.empty:
        if view_mode == "Weekly":
            trend_agg = (
                trend_df.groupby(['Client Name', 'Year', 'Week (by Year)'], observed=True)
                .agg(GP=('GP', 'sum'), Revenue=('Total Revenue', 'sum'))
                .reset_index()
                .sort_values(['Year', 'Week (by Year)'])
            )
            trend_agg['Period Label'] = (trend_agg['Year'].astype(str) + ' W' +
                                         trend_agg['Week (by Year)'].astype(int).astype(str))
        else:
            trend_agg = (
                trend_df.groupby(['Client Name', 'Year', 'Month'], observed=True)
                .agg(GP=('GP', 'sum'), Revenue=('Total Revenue', 'sum'))
                .reset_index()
            )
            trend_agg['Month'] = pd.Categorical(trend_agg['Month'], categories=MONTH_ORDER, ordered=True)
            trend_agg = trend_agg.sort_values(['Year', 'Month'])
            trend_agg['Period Label'] = trend_agg['Year'].astype(str) + ' ' + trend_agg['Month'].astype(str)

        top_clients = (trend_agg.groupby('Client Name')['GP'].sum().nlargest(10).index.tolist())
        sel_clients = st.multiselect(
            "Filter clients (default: top 10 by GP)",
            sorted(trend_agg['Client Name'].unique()), default=top_clients
        )
        if sel_clients:
            trend_agg = trend_agg[trend_agg['Client Name'].isin(sel_clients)]

        fig_trend = px.line(
            trend_agg, x='Period Label', y='GP', color='Client Name',
            markers=True, template='plotly_white', height=500,
            title="GP per Client", labels={'GP': 'Gross Profit (IDR)', 'Period Label': 'Period'}
        )
        fig_trend.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.4)
        fig_trend.update_layout(hovermode='x unified', legend=dict(orientation='h', y=-0.25),
                                xaxis_tickangle=-45)
        st.plotly_chart(fig_trend, use_container_width=True)


# ── Tab 3: Single client full history ────────────────────────────────────────
with tab3:
    st.subheader("Single Client — Full History")

    all_clients = sorted(df['Client Name'].dropna().unique())
    sel_client = st.selectbox("Select client", all_clients, key="pp_single_client")
    cdf = df[df['Client Name'] == sel_client].copy()

    detail_view = st.radio("History view", ["Weekly", "Monthly"], horizontal=True,
                           key="pp_client_hist_view")

    if detail_view == "Weekly":
        hist = (
            cdf.groupby(['Year', 'Week (by Year)'], observed=True)
            .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
                 Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
            .reset_index().sort_values(['Year', 'Week (by Year)'])
        )
        hist['Label'] = hist['Year'].astype(str) + ' W' + hist['Week (by Year)'].astype(int).astype(str)
    else:
        hist = (
            cdf.groupby(['Year', 'Month'], observed=True)
            .agg(Volume=('Delivery Volume', 'sum'), Revenue=('Total Revenue', 'sum'),
                 Cost=('Total Cost', 'sum'), GP=('GP', 'sum'))
            .reset_index()
        )
        hist['Month'] = pd.Categorical(hist['Month'], categories=MONTH_ORDER, ordered=True)
        hist = hist.sort_values(['Year', 'Month'])
        hist['Label'] = hist['Year'].astype(str) + ' ' + hist['Month'].astype(str)

    hist['GP Margin %'] = np.where(hist['Revenue'] != 0, hist['GP'] / hist['Revenue'] * 100, 0)
    for m in ['Volume', 'Revenue', 'GP']:
        hist[f'{m} PoP%'] = hist[m].pct_change() * 100

    # Chart
    fig_c = go.Figure()
    fig_c.add_bar(x=hist['Label'], y=hist['Revenue'], name='Revenue',
                  marker_color=C_REVENUE, opacity=0.8)
    fig_c.add_bar(x=hist['Label'], y=hist['Cost'], name='Cost',
                  marker_color=C_COST, opacity=0.8)
    fig_c.add_scatter(x=hist['Label'], y=hist['GP'], mode='lines+markers',
                      name='GP', line=dict(color=C_GP, width=2))
    fig_c.update_layout(barmode='group', hovermode='x unified', template='plotly_white',
                        height=420, legend=dict(orientation='h', y=1.05),
                        yaxis_title='IDR', xaxis_tickangle=-45,
                        title=f"{sel_client} — {detail_view} P&L History")
    st.plotly_chart(fig_c, use_container_width=True)

    def fmt_pop_plain(v):
        if pd.isna(v):
            return '—'
        return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"

    disp_c = hist.copy()
    disp_c['Revenue']  = disp_c['Revenue'].apply(fmt_idr)
    disp_c['Cost']     = disp_c['Cost'].apply(fmt_idr)
    disp_c['GP']       = disp_c['GP'].apply(fmt_idr)
    disp_c['Margin']   = disp_c['GP Margin %'].apply(fmt_pct)
    disp_c['Volume']   = disp_c['Volume'].apply(fmt_vol)
    disp_c['Rev PoP%'] = disp_c['Revenue PoP%'].apply(fmt_pop_plain)
    disp_c['GP PoP%']  = disp_c['GP PoP%'].apply(fmt_pop_plain)
    disp_c['Vol PoP%'] = disp_c['Volume PoP%'].apply(fmt_pop_plain)

    st.dataframe(
        disp_c[['Label', 'Volume', 'Vol PoP%', 'Revenue', 'Rev PoP%',
                'Cost', 'GP', 'GP PoP%', 'Margin']],
        use_container_width=True, hide_index=True
    )
