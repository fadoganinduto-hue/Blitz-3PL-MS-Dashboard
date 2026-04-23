import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   get_available_periods, filter_period, pop_pct, pop_label)
from data_loader import MOBILE_REVENUE_COLS, MOBILE_COST_COLS

st.set_page_config(page_title="Mobile Deep Dive | Blitz", page_icon="🔬", layout="wide")
st.title("🔬 Mobile Sellers Deep Dive")
st.caption(
    "Full line-item breakdown for any client across two periods. "
    "Pinpoint exactly which revenue or cost component is driving a change."
)

df_full = require_mobile_data()

if df_full.empty:
    st.warning("No data loaded.")
    st.stop()

df = df_full.copy()

col_client, col_mode = st.columns([2, 1])
with col_client:
    all_clients = sorted(df['Client Name'].dropna().unique())
    sel_client = st.selectbox("Client", all_clients)

with col_mode:
    view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mobile_dd_view")

pop = pop_label(view_mode)
cdf = df[df['Client Name'] == sel_client].copy()

if cdf.empty:
    st.warning(f"No data found for {sel_client}.")
    st.stop()

periods = get_available_periods(cdf, view_mode)
period_labels = [p[2] for p in periods]
label_map = {p[2]: (p[0], p[1]) for p in periods}

if len(periods) < 1:
    st.warning("Not enough periods available for this client.")
    st.stop()

col_pa, col_pb = st.columns(2)
with col_pb:
    lbl_b = st.selectbox("Period B (later)", period_labels[::-1], index=0, key="mobile_dd_pb")
with col_pa:
    prior_opts = [l for l in period_labels[::-1] if l != lbl_b]
    if prior_opts:
        lbl_a = st.selectbox("Period A (earlier)", prior_opts, index=0, key="mobile_dd_pa")
    else:
        lbl_a = None
        st.info("Only one period available; showing Period B only.")

yr_b, p_b = label_map[lbl_b]
df_b = filter_period(cdf, view_mode, yr_b, p_b)

if lbl_a:
    yr_a, p_a = label_map[lbl_a]
    df_a = filter_period(cdf, view_mode, yr_a, p_a)
else:
    yr_a, p_a = None, None
    df_a = pd.DataFrame()

st.caption(f"**{lbl_a or '—'}**  →  **{lbl_b}**")
st.divider()

def col_sum(d, c):
    return d[c].sum() if c in d.columns else 0.0

def col_max(d, c):
    return d[c].max() if c in d.columns else 0.0

def fmt_delta_abs(b, a):
    diff = b - a
    if diff == 0:
        return "—"
    return f"+{fmt_idr(diff)}" if diff > 0 else fmt_idr(diff)

def fmt_delta_pct(b, a):
    p = pop_pct(b, a)
    if p is None:
        return "—"
    arrow = "▲" if p > 0 else "▼"
    return f"{arrow} {abs(p):.1f}%"

# ── Summary KPIs ────────────────────────────────────────────────────────────────
st.subheader(f"Summary  ·  {sel_client}")

cups_a = col_sum(df_a, 'Total Cups Sold')
cups_b = col_sum(df_b, 'Total Cups Sold')
grev_a = col_sum(df_a, 'Gross Revenue')
grev_b = col_sum(df_b, 'Gross Revenue')
brev_a = col_sum(df_a, 'Blitz Revenue')
brev_b = col_sum(df_b, 'Blitz Revenue')
cogs_a = col_sum(df_a, 'COGS')
cogs_b = col_sum(df_b, 'COGS')
opcost_a = col_sum(df_a, 'Total Operational Cost')
opcost_b = col_sum(df_b, 'Total Operational Cost')
totalcost_a = cogs_a + opcost_a
totalcost_b = cogs_b + opcost_b
profit_a = grev_a - totalcost_a
profit_b = grev_b - totalcost_b
margin_a = profit_a / grev_a * 100 if grev_a > 0 else 0
margin_b = profit_b / grev_b * 100 if grev_b > 0 else 0

metrics_compare = [
    ("Cups", fmt_vol(cups_a), fmt_vol(cups_b), pop_pct(cups_b, cups_a)),
    ("Gross Revenue", fmt_idr(grev_a), fmt_idr(grev_b), pop_pct(grev_b, grev_a)),
    ("Blitz Revenue", fmt_idr(brev_a), fmt_idr(brev_b), pop_pct(brev_b, brev_a)),
    ("COGS", fmt_idr(cogs_a), fmt_idr(cogs_b), pop_pct(cogs_b, cogs_a)),
    ("OpCost", fmt_idr(opcost_a), fmt_idr(opcost_b), pop_pct(opcost_b, opcost_a)),
    ("Total Cost", fmt_idr(totalcost_a), fmt_idr(totalcost_b), pop_pct(totalcost_b, totalcost_a)),
    ("Profit", fmt_idr(profit_a), fmt_idr(profit_b), pop_pct(profit_b, profit_a)),
    ("Margin %", fmt_pct(margin_a), fmt_pct(margin_b), (margin_b - margin_a) if grev_a > 0 else None),
]

h0, h1, h2, h3, h4 = st.columns([2, 2, 2, 2, 1])
h0.markdown("**Metric**")
h1.markdown(f"**{lbl_a or '—'}**")
h2.markdown(f"**{lbl_b}**")
h3.markdown(f"**Δ {pop}**")
h4.markdown("")

for metric, val_a, val_b, delta in metrics_compare:
    c0, c1, c2, c3, c4 = st.columns([2, 2, 2, 2, 1])
    c0.write(metric)
    c1.write(val_a if lbl_a else "—")
    c2.write(val_b)
    if delta is not None:
        arrow = "▲" if delta > 0 else "▼"
        color = "green" if delta > 0 else "red"
        if metric == "Margin %":
            c3.markdown(f":{color}[{arrow} {abs(delta):.1f}pp]")
        else:
            c3.markdown(f":{color}[{arrow} {abs(delta):.1f}%]")
    else:
        c3.write("—")

st.divider()

# ── Revenue breakdown ───────────────────────────────────────────────────────────
st.subheader("Revenue Breakdown")

rev_cols_present = [c for c in MOBILE_REVENUE_COLS if c in cdf.columns]
rev_rows = []
for col in rev_cols_present:
    va = col_sum(df_a, col)
    vb = col_sum(df_b, col)
    if va == 0 and vb == 0:
        continue
    rev_rows.append({
        'Line Item': col,
        lbl_a or "Period A": fmt_idr(va) if lbl_a else "—",
        lbl_b: fmt_idr(vb),
        'Δ (abs)': fmt_delta_abs(vb, va) if lbl_a else "—",
        'Δ %': fmt_delta_pct(vb, va) if lbl_a else "—",
    })

if rev_rows:
    rev_df = pd.DataFrame(rev_rows)
    st.dataframe(rev_df, use_container_width=True, hide_index=True)

st.divider()

# ── Cost breakdown ──────────────────────────────────────────────────────────────
st.subheader("Cost Breakdown")

cost_cols_present = [c for c in MOBILE_COST_COLS if c in cdf.columns]
cost_rows = []
for col in cost_cols_present:
    va = col_sum(df_a, col)
    vb = col_sum(df_b, col)
    if va == 0 and vb == 0:
        continue
    cost_rows.append({
        'Line Item': col,
        lbl_a or "Period A": fmt_idr(va) if lbl_a else "—",
        lbl_b: fmt_idr(vb),
        'Δ (abs)': fmt_delta_abs(vb, va) if lbl_a else "—",
        'Δ %': fmt_delta_pct(vb, va) if lbl_a else "—",
    })

if cost_rows:
    cost_df = pd.DataFrame(cost_rows)
    st.dataframe(cost_df, use_container_width=True, hide_index=True)

st.divider()

# ── Profit bridge waterfall ─────────────────────────────────────────────────────
if lbl_a:
    st.subheader("Profit Bridge Waterfall")

    profit_change = profit_b - profit_a
    rev_change = grev_b - grev_a
    cogs_change = -(cogs_b - cogs_a)
    opcost_change = -(opcost_b - opcost_a)

    wf_labels = [f'Profit ({lbl_a})', 'Gross Rev Δ', 'COGS Δ', 'OpCost Δ', f'Profit ({lbl_b})']
    wf_values = [profit_a, rev_change, cogs_change, opcost_change, profit_b]
    wf_measure = ['absolute', 'relative', 'relative', 'relative', 'total']
    wf_colors = ['#4CAF50',
                 '#4CAF50' if rev_change > 0 else '#F44336',
                 '#4CAF50' if cogs_change > 0 else '#F44336',
                 '#4CAF50' if opcost_change > 0 else '#F44336',
                 '#2196F3']

    fig_wf = go.Figure(go.Waterfall(
        name="Profit Bridge", orientation="v",
        measure=wf_measure,
        x=wf_labels, y=wf_values,
        textposition="outside",
        text=[fmt_idr(v) for v in wf_values],
        connector=dict(line=dict(color='rgb(63,63,63)')),
        increasing=dict(marker_color='#4CAF50'),
        decreasing=dict(marker_color='#F44336'),
        totals=dict(marker_color='#2196F3'),
    ))
    fig_wf.update_layout(
        template='plotly_white', height=450,
        title=f"Profit Bridge: {lbl_a} → {lbl_b}  (Rp {profit_change:+,.0f})",
        yaxis_title='IDR', xaxis_tickangle=-35,
        showlegend=False
    )
    st.plotly_chart(fig_wf, use_container_width=True)

    st.divider()

# ── Operational metrics ─────────────────────────────────────────────────────────
st.subheader("Operational Metrics")

ops_rows = [
    {
        'Metric': 'Cups Sold',
        lbl_a or "Period A": fmt_vol(cups_a) if lbl_a else "—",
        lbl_b: fmt_vol(cups_b),
        'Δ %': fmt_delta_pct(cups_b, cups_a) if lbl_a else "—",
    },
    {
        'Metric': 'Active Riders',
        lbl_a or "Period A": fmt_vol(col_max(df_a, 'Total Active Riders')) if lbl_a else "—",
        lbl_b: fmt_vol(col_max(df_b, 'Total Active Riders')),
        'Δ %': "—",
    },
]

# Add % Commission, % Incentive, % Commission+Incentive if present
if '% Commision' in cdf.columns:
    pct_comm_a = df_a['% Commision'].mean() if not df_a.empty else 0
    pct_comm_b = df_b['% Commision'].mean() if not df_b.empty else 0
    ops_rows.append({
        'Metric': '% Commission',
        lbl_a or "Period A": fmt_pct(pct_comm_a) if lbl_a else "—",
        lbl_b: fmt_pct(pct_comm_b),
        'Δ %': fmt_pct(pct_comm_b - pct_comm_a) if lbl_a else "—",
    })

if '% Incentive' in cdf.columns:
    pct_inc_a = df_a['% Incentive'].mean() if not df_a.empty else 0
    pct_inc_b = df_b['% Incentive'].mean() if not df_b.empty else 0
    ops_rows.append({
        'Metric': '% Incentive',
        lbl_a or "Period A": fmt_pct(pct_inc_a) if lbl_a else "—",
        lbl_b: fmt_pct(pct_inc_b),
        'Δ %': fmt_pct(pct_inc_b - pct_inc_a) if lbl_a else "—",
    })

if ops_rows:
    st.dataframe(pd.DataFrame(ops_rows), use_container_width=True, hide_index=True)

st.divider()

# ── Raw data ────────────────────────────────────────────────────────────────────
st.subheader("Raw Data — All Columns")
st.caption("Every row for this client in the selected period(s).")

period_choice = st.radio(
    "Show data for", ["Period B only", "Period A only", "Both periods"],
    horizontal=True, key="mobile_dd_raw_period"
)

if period_choice == "Period B only":
    raw_show = df_b.copy()
    raw_show.insert(0, 'Period', lbl_b)
elif period_choice == "Period A only":
    raw_show = df_a.copy() if not df_a.empty else pd.DataFrame()
    if not raw_show.empty:
        raw_show.insert(0, 'Period', lbl_a)
else:
    parts = []
    if not df_a.empty and lbl_a:
        tmp_a = df_a.copy()
        tmp_a.insert(0, 'Period', lbl_a)
        parts.append(tmp_a)
    tmp_b = df_b.copy()
    tmp_b.insert(0, 'Period', lbl_b)
    parts.append(tmp_b)
    raw_show = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

if raw_show.empty:
    st.info("No rows to display for this selection.")
else:
    priority_cols = [
        'Period', 'Year', 'Week (by Year)', 'Month', 'Week (by Month)', 'Date Range',
        'Client Name', 'Project', 'Client Level', 'Blitz Team', 'Client Location',
        'Total Cups Sold', 'Total Active Riders',
        'Total Selling (Clients Revenue)', 'Total Revenue Sharing % (Weekly)', 'Total Revenue',
        'Total Selling Comission/Sales (Weekly)', 'Total Daily Incentive (Weekly)',
        'Total 26 Days Attendance Bonus (Monthly)', 'Referral', 'Total Selling 20Mio Bonus (Monthly)',
        'Bonus+Beras', 'Total Income Sales (Weekly)',
        'Manpower (Korlap)', 'Total Cost Molis (Weekly)', 'Cost Claim', 'Storing Cost',
        'Total Operational Cost', 'Total Potongan Molis (Weekly)',
        'Total Subsidi Molis KSJ (Monthly)', 'Biaya Registrasi',
        'Rider Penalty (Claim, Other Denda to Riders)',
        'Profit', 'Delivery PV', 'Delivery Only PnL', 'EV Related PV', 'EV Related Only PnL',
    ]
    ordered = [c for c in priority_cols if c in raw_show.columns]
    remaining = [c for c in raw_show.columns if c not in ordered]
    raw_show = raw_show[ordered + remaining]

    st.dataframe(raw_show, use_container_width=True, hide_index=True, height=500)
    st.caption(f"{len(raw_show):,} rows · {len(raw_show.columns)} columns")
