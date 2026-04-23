import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, pop_pct, pop_label)
from data_loader import REVENUE_COLS, COST_COLS, COST_COMPONENTS

st.set_page_config(page_title="Deep Dive | Blitz", page_icon="🔬", layout="wide")
st.title("🔬 Deep Dive")
st.caption(
    "Full line-item breakdown for any client across two periods. "
    "Pinpoint exactly which revenue or cost component is driving a change."
)

df_full = require_data()
# Deep Dive uses the FULL unfiltered data so the user can compare any two periods
# (sidebar team/month filters would restrict available periods)
df = df_full.copy()

if df.empty:
    st.warning("No data loaded.")
    st.stop()

# ── Selectors: Client + Period mode ──────────────────────────────────────────
col_client, col_mode = st.columns([2, 1])
with col_client:
    all_clients = sorted(df['Client Name'].dropna().unique())
    sel_client = st.selectbox("Client", all_clients)

with col_mode:
    view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="dd_view")

pop = pop_label(view_mode)
cdf = df[df['Client Name'] == sel_client].copy()

if cdf.empty:
    st.warning(f"No data found for {sel_client}.")
    st.stop()

# Period selectors for this client's data
periods     = get_available_periods(cdf, view_mode)
period_labels = [p[2] for p in periods]
label_map   = {p[2]: (p[0], p[1]) for p in periods}

if len(periods) < 1:
    st.warning("Not enough periods available for this client.")
    st.stop()

col_pa, col_pb = st.columns(2)
with col_pb:
    lbl_b = st.selectbox("Period B (later)", period_labels[::-1], index=0, key="dd_pb")
with col_pa:
    prior_opts = [l for l in period_labels[::-1] if l != lbl_b]
    if prior_opts:
        lbl_a = st.selectbox("Period A (earlier)", prior_opts, index=0, key="dd_pa")
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

if view_mode == "Weekly":
    date_a = df_a['Date Range'].dropna().iloc[0] if (lbl_a and not df_a['Date Range'].dropna().empty) else ''
    date_b = df_b['Date Range'].dropna().iloc[0] if not df_b['Date Range'].dropna().empty else ''
    st.caption(f"**{lbl_a or '—'}**  ·  {date_a}  →  **{lbl_b}**  ·  {date_b}")
else:
    st.caption(f"**{lbl_a or '—'}**  →  **{lbl_b}**")

st.divider()


# ── Helper: sum a list of columns for a dataframe ─────────────────────────────
def col_sums(d: pd.DataFrame, cols: list[str]) -> dict:
    return {c: d[c].sum() if c in d.columns else 0.0 for c in cols}


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


# ── Section 1: Headline KPI comparison ───────────────────────────────────────
st.subheader(f"Summary  ·  {sel_client}")

sums_a = col_sums(df_a, ['Total Revenue', 'Total Cost', 'Delivery Volume'])
sums_b = col_sums(df_b, ['Total Revenue', 'Total Cost', 'Delivery Volume'])
gp_a = sums_a['Total Revenue'] - sums_a['Total Cost']
gp_b = sums_b['Total Revenue'] - sums_b['Total Cost']
margin_a = gp_a / sums_a['Total Revenue'] * 100 if sums_a['Total Revenue'] else 0
margin_b = gp_b / sums_b['Total Revenue'] * 100 if sums_b['Total Revenue'] else 0

metrics_compare = [
    ("Volume",     fmt_vol(sums_a['Delivery Volume']),    fmt_vol(sums_b['Delivery Volume']),    pop_pct(sums_b['Delivery Volume'],    sums_a['Delivery Volume'])),
    ("Revenue",    fmt_idr(sums_a['Total Revenue']),      fmt_idr(sums_b['Total Revenue']),      pop_pct(sums_b['Total Revenue'],      sums_a['Total Revenue'])),
    ("Total Cost", fmt_idr(sums_a['Total Cost']),         fmt_idr(sums_b['Total Cost']),         pop_pct(sums_b['Total Cost'],         sums_a['Total Cost'])),
    ("GP",         fmt_idr(gp_a),                         fmt_idr(gp_b),                         pop_pct(gp_b, gp_a)),
    ("Margin",     fmt_pct(margin_a),                     fmt_pct(margin_b),                     (margin_b - margin_a) if margin_a else None),
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
        if metric == "Margin":
            c3.markdown(f":{color}[{arrow} {abs(delta):.1f}pp]")
        else:
            c3.markdown(f":{color}[{arrow} {abs(delta):.1f}%]")
    else:
        c3.write("—")

st.divider()


# ── Section 2: Revenue line-item breakdown ────────────────────────────────────
st.subheader("Revenue Breakdown")

rev_cols_present = [c for c in REVENUE_COLS if c in cdf.columns]
rev_a = col_sums(df_a, rev_cols_present)
rev_b = col_sums(df_b, rev_cols_present)

rev_rows = []
for col in rev_cols_present:
    va, vb = rev_a[col], rev_b[col]
    if va == 0 and vb == 0:
        continue
    rev_rows.append({
        'Line Item':        col,
        lbl_a or "Period A": fmt_idr(va) if lbl_a else "—",
        lbl_b:              fmt_idr(vb),
        'Δ (abs)':          fmt_delta_abs(vb, va) if lbl_a else "—",
        'Δ %':              fmt_delta_pct(vb, va) if lbl_a else "—",
    })

if rev_rows:
    rev_df = pd.DataFrame(rev_rows)
    # Highlight Total Revenue row
    st.dataframe(rev_df, use_container_width=True, hide_index=True)

    # Visual: side-by-side bar per revenue component (excluding totals)
    plot_cols = [c for c in rev_cols_present if c != 'Total Revenue' and
                 (rev_a.get(c, 0) != 0 or rev_b.get(c, 0) != 0)]
    if plot_cols and lbl_a:
        chart_data = pd.DataFrame({
            'Component': plot_cols * 2,
            'Period':    [lbl_a] * len(plot_cols) + [lbl_b] * len(plot_cols),
            'Amount':    [rev_a[c] for c in plot_cols] + [rev_b[c] for c in plot_cols],
        })
        fig_rev = px.bar(
            chart_data, x='Component', y='Amount', color='Period',
            barmode='group', template='plotly_white', height=400,
            color_discrete_map={lbl_a: '#90CAF9', lbl_b: C_REVENUE},
            title="Revenue Components — Side by Side",
            labels={'Amount': 'IDR', 'Component': ''}
        )
        fig_rev.update_layout(xaxis_tickangle=-35, hovermode='x unified',
                              legend=dict(orientation='h', y=1.05))
        st.plotly_chart(fig_rev, use_container_width=True)

st.divider()


# ── Section 3: Cost line-item breakdown ───────────────────────────────────────
st.subheader("Cost Breakdown")

cost_cols_present = [c for c in COST_COLS if c in cdf.columns]
cost_a = col_sums(df_a, cost_cols_present)
cost_b = col_sums(df_b, cost_cols_present)

cost_rows = []
for col in cost_cols_present:
    va, vb = cost_a[col], cost_b[col]
    if va == 0 and vb == 0:
        continue
    cost_rows.append({
        'Line Item':        col,
        lbl_a or "Period A": fmt_idr(va) if lbl_a else "—",
        lbl_b:              fmt_idr(vb),
        'Δ (abs)':          fmt_delta_abs(vb, va) if lbl_a else "—",
        'Δ %':              fmt_delta_pct(vb, va) if lbl_a else "—",
    })

if cost_rows:
    cost_df_disp = pd.DataFrame(cost_rows)
    st.dataframe(cost_df_disp, use_container_width=True, hide_index=True)

    # Visual: side-by-side bar per cost component (excluding total)
    plot_cost_cols = [c for c in cost_cols_present if c != 'Total Cost' and
                      (cost_a.get(c, 0) != 0 or cost_b.get(c, 0) != 0)]
    if plot_cost_cols and lbl_a:
        chart_cost = pd.DataFrame({
            'Component': plot_cost_cols * 2,
            'Period':    [lbl_a] * len(plot_cost_cols) + [lbl_b] * len(plot_cost_cols),
            'Amount':    [cost_a[c] for c in plot_cost_cols] + [cost_b[c] for c in plot_cost_cols],
        })
        fig_cost = px.bar(
            chart_cost, x='Component', y='Amount', color='Period',
            barmode='group', template='plotly_white', height=400,
            color_discrete_map={lbl_a: '#FFCDD2', lbl_b: C_COST},
            title="Cost Components — Side by Side",
            labels={'Amount': 'IDR', 'Component': ''}
        )
        fig_cost.update_layout(xaxis_tickangle=-35, hovermode='x unified',
                               legend=dict(orientation='h', y=1.05))
        st.plotly_chart(fig_cost, use_container_width=True)

    # Waterfall: what drove the GP change?
    if lbl_a:
        st.markdown("##### GP Change Waterfall — What drove the change?")
        gp_change = gp_b - gp_a
        component_changes = []
        # Revenue components drove GP up
        for col in [c for c in rev_cols_present if c != 'Total Revenue']:
            delta = rev_b.get(col, 0) - rev_a.get(col, 0)
            if delta != 0:
                component_changes.append(('Rev: ' + col, delta))
        # Cost components drove GP down (a cost increase → GP decrease)
        for col in [c for c in cost_cols_present if c != 'Total Cost']:
            delta = -(cost_b.get(col, 0) - cost_a.get(col, 0))  # inverse for GP
            if delta != 0:
                component_changes.append(('Cost: ' + col, delta))

        if component_changes:
            wf_labels = [f'GP ({lbl_a})'] + [c[0] for c in component_changes] + [f'GP ({lbl_b})']
            wf_values = [gp_a] + [c[1] for c in component_changes] + [gp_b]
            wf_measure = ['absolute'] + ['relative'] * len(component_changes) + ['total']
            wf_colors  = ['#4CAF50'] + ['#4CAF50' if v > 0 else '#F44336' for _, v in component_changes] + ['#2196F3']

            fig_wf = go.Figure(go.Waterfall(
                name="GP Bridge", orientation="v",
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
                title=f"GP Bridge: {lbl_a} → {lbl_b}  (Rp {gp_change:+,.0f})",
                yaxis_title='IDR', xaxis_tickangle=-35,
                showlegend=False
            )
            st.plotly_chart(fig_wf, use_container_width=True)

st.divider()


# ── Section 4: Operational metrics ───────────────────────────────────────────
st.subheader("Operational Metrics")

ops_cols = ['Delivery Volume', '_total_deliveries', '_total_ontime', '_total_late', 'OTP Rate %']
ops_labels = {
    'Delivery Volume':    'Delivery Volume',
    '_total_deliveries':  'SLA-Tracked Deliveries',
    '_total_ontime':      'On-Time',
    '_total_late':        'Late',
    'OTP Rate %':         'OTP Rate %',
}

ops_rows = []
for col, label in ops_labels.items():
    if col not in cdf.columns:
        continue
    va = df_a[col].sum() if (lbl_a and not df_a.empty) else None
    vb = df_b[col].sum() if not df_b.empty else 0

    if col == 'OTP Rate %':
        # Weighted average, not sum
        va = (df_a['_total_ontime'].sum() / df_a['_total_deliveries'].sum() * 100
              if (lbl_a and not df_a.empty and df_a['_total_deliveries'].sum() > 0) else None)
        vb = (df_b['_total_ontime'].sum() / df_b['_total_deliveries'].sum() * 100
              if (not df_b.empty and df_b['_total_deliveries'].sum() > 0) else 0)
        ops_rows.append({
            'Metric':           label,
            lbl_a or "Period A": fmt_pct(va) if va is not None else "—",
            lbl_b:              fmt_pct(vb),
            'Δ':                f"{'▲' if vb > va else '▼'} {abs(vb - va):.1f}pp" if (va is not None and va > 0) else "—",
        })
    else:
        ops_rows.append({
            'Metric':           label,
            lbl_a or "Period A": fmt_vol(va) if va is not None else "—",
            lbl_b:              fmt_vol(vb),
            'Δ %':              fmt_delta_pct(vb, va) if va is not None else "—",
        })

if ops_rows:
    st.dataframe(pd.DataFrame(ops_rows), use_container_width=True, hide_index=True)

st.divider()


# ── Section 5: Full raw data table ───────────────────────────────────────────
st.subheader("Raw Data — All Columns")
st.caption(
    "Every row for this client in the selected period(s). "
    "Use column headers to sort. Mirrors the Raw Data Source sheet."
)

period_choice = st.radio(
    "Show data for", ["Period B only", "Period A only", "Both periods"],
    horizontal=True, key="dd_raw_period"
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
    # Drop internal helper columns and sort sensibly
    drop_cols = [c for c in raw_show.columns if c.startswith('_')]
    raw_show = raw_show.drop(columns=drop_cols, errors='ignore')

    # Human-friendly column order: key dimensions first, then financials
    priority_cols = [
        'Period', 'Year', 'Week (by Year)', 'Month', 'Week (by Month)', 'Date Range',
        'Client Name', 'Project', 'Client Level', 'SLA Type', 'Blitz Team', 'Client Location',
        'Delivery Volume',
        'Total Revenue', 'Selling Price (Regular Rate)', 'Additional Charge (KM, KG, Etc)',
        'Return/Delivery Rate', 'Lalamove Bills (Invoicing to Client)', 'TOTAL DELIVERY REVENUE',
        'EV Reduction (3PL & KSJ)', 'EV Manpower', 'EV Revenue + Battery (Rental Client)',
        'Claim/COD/Own Risk', 'Hub, COD Fee (SBY) & Service Korlap', 'Other Revenue',
        'Attribute Fee',
        'Total Cost', 'Rider Cost', 'Manpower Cost', 'OEM Cost', 'Mid-Mile/ Linehaul Cost',
        'Add. 3PL Cost', 'DM Program', 'Claim Damaged/Loss', 'Outstanding COD',
        'Claim Ownrisk', 'Attribute Cost', 'HUB Cost', 'Other Cost',
        'GP', 'GP Margin %',
        'Deliveries', '#Ontime', '#Late', 'OTP Rate %',
    ]
    ordered = [c for c in priority_cols if c in raw_show.columns]
    remaining = [c for c in raw_show.columns if c not in ordered]
    raw_show = raw_show[ordered + remaining]

    st.dataframe(raw_show, use_container_width=True, hide_index=True, height=500)
    st.caption(f"{len(raw_show):,} rows · {len(raw_show.columns)} columns")
