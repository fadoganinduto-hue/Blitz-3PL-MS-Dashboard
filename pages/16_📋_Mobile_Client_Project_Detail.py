"""Mobile Client → Project Detail — pick one client, see each of their
projects broken out week-by-week or month-by-month.

Mirrors pages/2_📋_Client_Project_Detail.py but on mobile data, with the
Spec 4 reconciled metrics (Delivery PV, Delivery PnL %, EV PV, EV PnL %,
Total PV, Mobile Profit) as primary columns. Legacy Profit Calc / Margin
and Blitz Revenue & Margin demoted rightmost for continuity.

Critical correctness invariant: Delivery PnL % and EV PnL % are NEVER
summed. They're recomputed from the post-groupby `_delivery_pv_base` /
`_ev_pv_base` columns added by load_mobile_data, both for per-period rows
and the TOTAL row. Same approach used in Mobile Detailed and Mobile
Project Detailed.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from utils import (require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   period_selector, MONTH_ORDER,
                   apply_chart_theme, idr_col, vol_col, pct_col)
from data_loader import (MOBILE_REVENUE_COLS, MOBILE_COST_COLS, MOBILE_OPS_COLS)

st.set_page_config(page_title="Mobile Client → Project Detail | Blitz",
                   page_icon="📋", layout="wide")
st.title("📋 Mobile Client → Project Detail")
st.caption(
    "Pick a client; see each of their mobile-seller projects broken out "
    "week-by-week (or month-by-month). Surfaces the Spec 4 reconciled "
    "metrics — Delivery PV, EV PV, Total PV — alongside the full P&L "
    "components."
)

df_full = require_mobile_data()

if 'Project' not in df_full.columns:
    st.error("'Project' column missing from mobile data.")
    st.stop()

df_full = df_full[
    df_full['Project'].notna()
    & (df_full['Project'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No mobile rows with a project label found.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────
clients_with_projects = sorted(df_full['Client Name'].dropna().unique().tolist())
if not clients_with_projects:
    st.warning("No mobile clients with project labels found.")
    st.stop()

c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
with c1:
    sel_client = st.selectbox("Select Client", clients_with_projects,
                              key="mcpd_client")
with c2:
    view_mode = period_selector(page_key="mobile_client_project_detail",
                                label="Period")
with c3:
    available_years = sorted(df_full['Year'].dropna().unique().astype(int).tolist())
    sel_years = st.multiselect("Year(s)", available_years,
                               default=available_years, key="mcpd_years")
with c4:
    available_months = [m for m in MONTH_ORDER if m in df_full['Month'].cat.categories]
    sel_months = st.multiselect("Month(s) — optional", available_months,
                                default=[], key="mcpd_months",
                                help="Leave empty for all months.")

# ── Filter ───────────────────────────────────────────────────────────────────
cdf = df_full[df_full['Client Name'] == sel_client].copy()
if sel_years:
    cdf = cdf[cdf['Year'].isin(sel_years)]
if sel_months:
    cdf = cdf[cdf['Month'].isin(sel_months)]

if cdf.empty:
    st.info("No data for this client in the selected range.")
    st.stop()

projects = sorted(cdf['Project'].dropna().unique().tolist())
if not projects:
    st.info("No projects recorded for this client in the selected range.")
    st.stop()

# ── Period aggregation helper ────────────────────────────────────────────────
group_cols = ['Year', 'Week (by Year)'] if view_mode == "Weekly" else ['Year', 'Month']
rev_cols   = [c for c in MOBILE_REVENUE_COLS if c in cdf.columns]
cost_cols  = [c for c in MOBILE_COST_COLS    if c in cdf.columns]
ops_cols   = [c for c in MOBILE_OPS_COLS     if c in cdf.columns]
spec4_pv   = [c for c in ('Mobile Profit', 'Delivery PV', 'EV PV', 'Total PV')
              if c in cdf.columns]

# Numeric cols summed through groupby. Includes the underscore-prefixed
# `_delivery_pv_base` / `_ev_pv_base` so weighted PnL % can be recomputed
# from the aggregated frame.
numeric_cols = ops_cols + rev_cols + cost_cols + spec4_pv
for c in ('_delivery_pv_base', '_ev_pv_base'):
    if c in cdf.columns:
        numeric_cols.append(c)
numeric_cols = [c for c in numeric_cols if c in cdf.columns]


def _col(d: pd.DataFrame, name: str) -> pd.Series:
    return d[name] if name in d.columns else pd.Series(0, index=d.index)


def _label_periods(df: pd.DataFrame) -> pd.DataFrame:
    if view_mode == "Weekly":
        df = df.sort_values(['Year', 'Week (by Year)'])
        df['Period'] = (
            df['Year'].astype(str)
            + ' W'
            + df['Week (by Year)'].astype(int).astype(str)
        )
    else:
        df = df.copy()
        df['Month'] = pd.Categorical(df['Month'], categories=MONTH_ORDER, ordered=True)
        df = df.sort_values(['Year', 'Month'])
        df['Period'] = df['Year'].astype(str) + ' ' + df['Month'].astype(str)
    return df


def _aggregate(pdf: pd.DataFrame) -> pd.DataFrame:
    """Group by period; recompute legacy + Spec 4 ratios from summed totals."""
    agg_dict = {c: 'sum' for c in numeric_cols}
    if 'Date Range' in pdf.columns:
        agg_dict['Date Range'] = 'first'
    agg = pdf.groupby(group_cols, observed=True).agg(agg_dict).reset_index()

    # Legacy derived (kept for the demoted block)
    agg['Blitz Revenue']      = _col(agg, 'Total Revenue Sharing % (Weekly)')
    agg['Gross Revenue']      = _col(agg, 'Total Revenue')
    agg['COGS']               = _col(agg, 'Total Income Sales (Weekly)')
    agg['Total Cost (Mobile)'] = agg['COGS'] + _col(agg, 'Total Operational Cost')
    agg['Profit Calc']        = agg['Gross Revenue'] - agg['Total Cost (Mobile)']
    agg['Profit Margin %']    = np.where(agg['Gross Revenue'] != 0,
                                         agg['Profit Calc'] / agg['Gross Revenue'] * 100, 0)
    agg['Blitz Margin %']     = np.where(agg['Blitz Revenue'] != 0,
                                         (agg['Blitz Revenue'] - agg['COGS']) / agg['Blitz Revenue'] * 100, 0)

    # Spec 4 weighted PnL % from base sums
    if '_delivery_pv_base' in agg.columns and 'Delivery PV' in agg.columns:
        agg['Delivery PnL %'] = np.where(
            agg['_delivery_pv_base'] > 0,
            agg['Delivery PV'] / agg['_delivery_pv_base'] * 100, 0
        )
    if '_ev_pv_base' in agg.columns and 'EV PV' in agg.columns:
        agg['EV PnL %'] = np.where(
            agg['_ev_pv_base'] > 0,
            agg['EV PV'] / agg['_ev_pv_base'] * 100, 0
        )
    if 'Delivery PV' in agg.columns and 'EV PV' in agg.columns:
        agg['Total PV'] = agg['Delivery PV'].fillna(0) + agg['EV PV'].fillna(0)

    # Per-driver
    riders = _col(agg, 'Total Active Riders').replace(0, np.nan)
    cups   = _col(agg, 'Total Cups Sold')
    agg['Cups per Driver']    = (cups / riders).fillna(0)
    agg['Revenue per Driver'] = (agg['Gross Revenue'] / riders).fillna(0)

    return _label_periods(agg)


# ── Headline KPI strip ───────────────────────────────────────────────────────
total_cups   = cdf['Total Cups Sold'].sum() if 'Total Cups Sold' in cdf.columns else 0
total_riders = cdf['Total Active Riders'].sum() if 'Total Active Riders' in cdf.columns else 0
total_dpv    = cdf['Delivery PV'].sum() if 'Delivery PV' in cdf.columns else 0
total_evpv   = cdf['EV PV'].sum()       if 'EV PV'       in cdf.columns else 0
total_tpv    = total_dpv + total_evpv
n_projects   = len(projects)
if view_mode == "Weekly":
    n_active = cdf.groupby(['Year', 'Week (by Year)']).ngroups
else:
    n_active = cdf.groupby(['Year', 'Month'], observed=True).ngroups

st.subheader(f"{sel_client} — across {n_projects} project(s)")
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("Cups",          fmt_vol(total_cups))
k2.metric("Riders",        fmt_vol(total_riders))
k3.metric("Delivery PV",   fmt_idr(total_dpv))
k4.metric("EV PV",         fmt_idr(total_evpv))
k5.metric("Total PV",      fmt_idr(total_tpv))
k6.metric("# Projects",    f"{n_projects}")
k7.metric("Active periods", f"{n_active}")

st.divider()
st.caption(
    "**Reading order in each table:** ops · per-driver · revenue components · "
    "cost components · **Spec 4 reconciled** (PV/PnL%/Mobile Profit) · "
    "*legacy high-level rollup — excludes rider, manpower, claim, and "
    "storing costs.*"
)

# ── Per-project expanders ────────────────────────────────────────────────────
combined_long: list[pd.DataFrame] = []
project_period_rows: list[pd.DataFrame] = []

# Display column order (mirrors Mobile Project Detailed)
spec4_order  = ['Mobile Profit', 'Delivery PV', 'Delivery PnL %',
                'EV PV', 'EV PnL %', 'Total PV']
legacy_order = ['Blitz Revenue', 'Gross Revenue', 'COGS', 'Total Cost (Mobile)',
                'Profit Calc', 'Profit Margin %', 'Blitz Margin %']

for i, proj in enumerate(projects):
    pdf = cdf[cdf['Project'] == proj]
    if pdf.empty:
        continue

    agg_df = _aggregate(pdf)
    if agg_df.empty:
        continue

    display_cols: list[str] = []
    display_cols += ops_cols
    display_cols += ['Cups per Driver', 'Revenue per Driver']
    display_cols += rev_cols
    display_cols += cost_cols
    display_cols += [c for c in spec4_order  if c in agg_df.columns]
    display_cols += [c for c in legacy_order if c in agg_df.columns]
    # Filter to existing + dedupe preserving order (rev_cols and legacy_cols
    # both alias to 'Total Revenue' / 'Blitz Revenue' under different names)
    seen: set = set()
    display_cols = [c for c in display_cols
                    if c in agg_df.columns and not (c in seen or seen.add(c))]

    # TOTAL row — sum financials, recompute ratios from sums
    total_row: dict = {'Period': 'TOTAL'}
    _ratio_cols = {'Profit Margin %', 'Blitz Margin %', 'Delivery PnL %',
                   'EV PnL %', 'Cups per Driver', 'Revenue per Driver'}
    for c in display_cols:
        if c not in _ratio_cols:
            total_row[c] = agg_df[c].sum()
    gr = total_row.get('Gross Revenue', 0)
    total_row['Profit Margin %'] = (
        total_row.get('Profit Calc', 0) / gr * 100 if gr else 0
    )
    br = total_row.get('Blitz Revenue', 0)
    total_row['Blitz Margin %'] = (
        (br - total_row.get('COGS', 0)) / br * 100 if br else 0
    )
    t_riders = total_row.get('Total Active Riders', 0) or 0
    t_cups   = total_row.get('Total Cups Sold', 0) or 0
    total_row['Cups per Driver']    = t_cups / t_riders if t_riders else 0
    total_row['Revenue per Driver'] = gr / t_riders if t_riders else 0
    # Spec 4 weighted recompute for TOTAL row
    _dbase = agg_df['_delivery_pv_base'].sum() if '_delivery_pv_base' in agg_df.columns else 0
    _ebase = agg_df['_ev_pv_base'].sum()       if '_ev_pv_base'       in agg_df.columns else 0
    if 'Delivery PnL %' in display_cols:
        total_row['Delivery PnL %'] = (
            total_row.get('Delivery PV', 0) / _dbase * 100 if _dbase else 0
        )
    if 'EV PnL %' in display_cols:
        total_row['EV PnL %'] = (
            total_row.get('EV PV', 0) / _ebase * 100 if _ebase else 0
        )

    table = pd.concat(
        [agg_df[['Period'] + display_cols], pd.DataFrame([total_row])],
        ignore_index=True,
    )

    # Expander caption — Spec 4 metrics for the headline (Total PV / Margin)
    proj_tpv = agg_df['Total PV'].sum() if 'Total PV' in agg_df.columns else 0
    proj_dpv = agg_df['Delivery PV'].sum() if 'Delivery PV' in agg_df.columns else 0
    proj_dbase = agg_df['_delivery_pv_base'].sum() if '_delivery_pv_base' in agg_df.columns else 0
    proj_dpnl  = (proj_dpv / proj_dbase * 100) if proj_dbase else 0
    n_periods = len(agg_df)
    summary = (
        f"{n_periods} {view_mode.lower()} period{'s' if n_periods != 1 else ''} · "
        f"Total PV {fmt_idr(proj_tpv)} · Delivery PnL {fmt_pct(proj_dpnl)}"
    )

    with st.expander(f"📦 {proj} — {summary}", expanded=(i == 0)):
        col_cfg: dict = {'Period': st.column_config.TextColumn('Period')}
        for c in display_cols:
            if c in ('Total Cups Sold', 'Total Active Riders'):
                col_cfg[c] = vol_col(c)
            elif c == 'Cups per Driver':
                col_cfg[c] = st.column_config.NumberColumn(c, format="%.1f")
            elif c in ('Profit Margin %', 'Blitz Margin %',
                       'Delivery PnL %', 'EV PnL %'):
                col_cfg[c] = pct_col(c, signed=False)
            else:
                col_cfg[c] = idr_col(c)
        height = min(38 * (len(table) + 2), 420)
        st.dataframe(
            table,
            column_config=col_cfg,
            width="stretch",
            hide_index=True,
            height=height,
            key=f"mcpd_table_{proj}_{view_mode}",
        )

    proj_long = agg_df[['Period'] + display_cols].copy()
    proj_long.insert(0, 'Project', proj)
    combined_long.append(proj_long)

    if 'Total PV' in agg_df.columns:
        project_period_rows.append(
            agg_df[['Period', 'Total PV']].assign(Project=proj)
        )

# ── Total-PV-by-project stacked bar ──────────────────────────────────────────
if project_period_rows:
    chart_df = pd.concat(project_period_rows, ignore_index=True)
    if not chart_df.empty:
        st.divider()
        st.subheader("Total PV per period, stacked by project")
        fig = px.bar(
            chart_df, x='Period', y='Total PV', color='Project',
            barmode='stack', height=380,
            labels={'Total PV': 'Total PV (IDR)', 'Period': ''},
        )
        fig.update_layout(xaxis_tickangle=-45)
        apply_chart_theme(fig)
        st.plotly_chart(fig, width="stretch")

# ── CSV download ─────────────────────────────────────────────────────────────
if combined_long:
    st.divider()
    full = pd.concat(combined_long, ignore_index=True)
    client_slug = sel_client.replace(' ', '_').replace('/', '-')
    csv_data = full.to_csv(index=False)
    st.download_button(
        "📥 Download as CSV",
        data=csv_data,
        file_name=f"client_project_detail_mobile_{client_slug}_{view_mode.lower()}.csv",
        mime="text/csv",
    )
