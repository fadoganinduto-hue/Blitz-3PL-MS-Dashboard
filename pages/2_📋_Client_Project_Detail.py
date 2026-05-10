"""Client → Project Detail (delivery) — pick one client, see each of their
projects broken out week-by-week or month-by-month with full P&L line items.

Layout:
  Client + period + (year/month) controls
  ─────────────────────────────────────────
  Headline KPI strip — totals across the selected client+range
  ─────────────────────────────────────────
  ▼ Project A   (12 periods · GP X · Margin Y%)
       Period │ Volume │ revenue cols… │ Total Revenue │ cost cols… │ Total Cost │ GP │ Margin │ TRPO
       …
       TOTAL  │ … (ratios recomputed from sums, not summed)
  ▼ Project B  (collapsed by default)
  …
  Stacked-bar GP-by-project chart
  CSV download (combined long-format across all projects)

Sibling: pages/16_📋_Mobile_Client_Project_Detail.py (mobile equivalent).
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from utils import (require_data, fmt_idr, fmt_pct, fmt_vol,
                   period_selector, MONTH_ORDER,
                   apply_chart_theme, idr_col, vol_col, pct_col)
from data_loader import REVENUE_COLS, COST_COLS

st.set_page_config(page_title="Client → Project Detail | Blitz", page_icon="📋", layout="wide")
st.title("📋 Client → Project Detail")
st.caption(
    "Pick a client; see each of their projects broken out week-by-week "
    "(or month-by-month) with full P&L columns. Useful for per-project "
    "analysis within a single client."
)

df_full = require_data()

if 'Project' not in df_full.columns:
    st.error("'Project' column missing.")
    st.stop()

# Keep only rows with a non-blank Project label
df_full = df_full[
    df_full['Project'].notna()
    & (df_full['Project'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No rows with a project label found.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────
clients_with_projects = sorted(df_full['Client Name'].dropna().unique().tolist())
if not clients_with_projects:
    st.warning("No clients with project labels found.")
    st.stop()

c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
with c1:
    sel_client = st.selectbox("Select Client", clients_with_projects,
                              key="cpd_client")
with c2:
    view_mode = period_selector(page_key="client_project_detail", label="Period")
with c3:
    available_years = sorted(df_full['Year'].dropna().unique().astype(int).tolist())
    sel_years = st.multiselect("Year(s)", available_years,
                               default=available_years, key="cpd_years")
with c4:
    available_months = [m for m in MONTH_ORDER if m in df_full['Month'].cat.categories]
    sel_months = st.multiselect("Month(s) — optional", available_months,
                                default=[], key="cpd_months",
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
rev_cols  = [c for c in REVENUE_COLS if c in cdf.columns and c != 'Total Revenue']
cost_cols = [c for c in COST_COLS    if c in cdf.columns and c != 'Total Cost']
numeric_cols = ['Delivery Volume'] + rev_cols + ['Total Revenue'] + cost_cols + ['Total Cost']
numeric_cols = [c for c in numeric_cols if c in cdf.columns]


def _label_periods(df: pd.DataFrame) -> pd.DataFrame:
    """Add a sortable, human-readable Period column. Pandas 3.0+ pyarrow-backed
    strings need explicit .astype(str) on every operand to concat cleanly."""
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
    """Group by period; recompute ratios from summed totals after groupby."""
    agg_dict = {c: 'sum' for c in numeric_cols}
    if 'Date Range' in pdf.columns:
        agg_dict['Date Range'] = 'first'
    agg = pdf.groupby(group_cols, observed=True).agg(agg_dict).reset_index()
    agg['GP'] = agg['Total Revenue'] - agg['Total Cost']
    agg['GP Margin %'] = np.where(
        agg['Total Revenue'] != 0,
        agg['GP'] / agg['Total Revenue'] * 100, 0
    )
    vol = agg['Delivery Volume'].replace(0, np.nan)
    agg['TRPO'] = (agg['Total Revenue'] / vol).fillna(0)
    return _label_periods(agg)


# ── Headline KPI strip — whole client+range ──────────────────────────────────
total_volume   = cdf['Delivery Volume'].sum()
total_revenue  = cdf['Total Revenue'].sum()
total_cost     = cdf['Total Cost'].sum()
total_gp       = total_revenue - total_cost
total_margin   = (total_gp / total_revenue * 100) if total_revenue else 0
n_projects     = len(projects)
# Active periods count = unique (year, period) combos in cdf for chosen view
if view_mode == "Weekly":
    n_active = cdf.groupby(['Year', 'Week (by Year)']).ngroups
else:
    n_active = cdf.groupby(['Year', 'Month'], observed=True).ngroups

st.subheader(f"{sel_client} — across {n_projects} project(s)")
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("Volume",        fmt_vol(total_volume))
k2.metric("Revenue",       fmt_idr(total_revenue))
k3.metric("Cost",          fmt_idr(total_cost))
k4.metric("GP",            fmt_idr(total_gp))
k5.metric("Margin",        fmt_pct(total_margin))
k6.metric("# Projects",    f"{n_projects}")
k7.metric(f"Active {view_mode.lower()[:-2]}s" if False else f"Active periods", f"{n_active}")

st.divider()

# ── Per-project expanders ────────────────────────────────────────────────────
combined_long: list[pd.DataFrame] = []   # accumulator for the CSV download
project_period_rows: list[pd.DataFrame] = []  # for the chart at the bottom

for i, proj in enumerate(projects):
    pdf = cdf[cdf['Project'] == proj]
    if pdf.empty:
        continue

    agg_df = _aggregate(pdf)
    if agg_df.empty:
        continue

    # TOTAL row — sum financials, recompute ratios from the sums
    display_cols = ['Delivery Volume'] + rev_cols + ['Total Revenue'] \
                 + cost_cols + ['Total Cost', 'GP', 'GP Margin %', 'TRPO']
    display_cols = [c for c in display_cols if c in agg_df.columns]

    total_row: dict = {'Period': 'TOTAL'}
    _ratio_cols = {'GP Margin %', 'TRPO'}
    for c in display_cols:
        if c not in _ratio_cols:
            total_row[c] = agg_df[c].sum()
    total_row['GP Margin %'] = (
        total_row.get('GP', 0) / total_row.get('Total Revenue', 0) * 100
        if total_row.get('Total Revenue', 0) else 0
    )
    total_vol = total_row.get('Delivery Volume', 0) or 0
    total_row['TRPO'] = (total_row.get('Total Revenue', 0) / total_vol) if total_vol else 0

    table = pd.concat(
        [agg_df[['Period'] + display_cols], pd.DataFrame([total_row])],
        ignore_index=True,
    )

    # Expander caption
    proj_gp     = agg_df['GP'].sum()
    proj_rev    = agg_df['Total Revenue'].sum()
    proj_margin = (proj_gp / proj_rev * 100) if proj_rev else 0
    n_periods   = len(agg_df)
    summary = (
        f"{n_periods} {view_mode.lower()} period{'s' if n_periods != 1 else ''} · "
        f"GP {fmt_idr(proj_gp)} · Margin {fmt_pct(proj_margin)}"
    )

    with st.expander(f"📦 {proj} — {summary}", expanded=(i == 0)):
        col_cfg: dict = {'Period': st.column_config.TextColumn('Period')}
        for c in display_cols:
            if c == 'Delivery Volume':
                col_cfg[c] = vol_col('Volume')
            elif c == 'GP Margin %':
                col_cfg[c] = pct_col('Margin', signed=False)
            else:
                col_cfg[c] = idr_col(c)
        # 38 px per row + header — clamp so 40+ rows don't blow out the page
        height = min(38 * (len(table) + 2), 420)
        st.dataframe(
            table,
            column_config=col_cfg,
            width="stretch",
            hide_index=True,
            height=height,
            key=f"cpd_table_{proj}_{view_mode}",
        )

    # For the chart and CSV
    proj_long = agg_df[['Period'] + display_cols].copy()
    proj_long.insert(0, 'Project', proj)
    combined_long.append(proj_long)

    project_period_rows.append(
        agg_df[['Period', 'GP']].assign(Project=proj)
    )

# ── GP-by-project stacked bar ────────────────────────────────────────────────
if project_period_rows:
    chart_df = pd.concat(project_period_rows, ignore_index=True)
    if not chart_df.empty:
        st.divider()
        st.subheader("GP per period, stacked by project")
        fig = px.bar(
            chart_df, x='Period', y='GP', color='Project', barmode='stack',
            height=380, labels={'GP': 'GP (IDR)', 'Period': ''},
        )
        fig.update_layout(xaxis_tickangle=-45)
        apply_chart_theme(fig)
        st.plotly_chart(fig, width="stretch")

# ── CSV download — combined long-format across all projects ──────────────────
if combined_long:
    st.divider()
    full = pd.concat(combined_long, ignore_index=True)
    client_slug = sel_client.replace(' ', '_').replace('/', '-')
    csv_data = full.to_csv(index=False)
    st.download_button(
        "📥 Download as CSV",
        data=csv_data,
        file_name=f"client_project_detail_{client_slug}_{view_mode.lower()}.csv",
        mime="text/csv",
    )
