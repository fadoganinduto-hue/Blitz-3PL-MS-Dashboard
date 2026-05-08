"""By Project — per-project P&L for delivery clients with project-level breakdowns.

Project is a column in the delivery `Raw Data Source` sheet. Many clients have
no project label (single-stream business), so this page filters to only rows
where Project is populated.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   selected_period_df,
                   pop_pct, pop_label, period_selector, build_trend, apply_chart_theme,
                   idr_col, vol_col, pct_col, dataframe_with_freeze)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="By Project | Blitz", page_icon="🏗️", layout="wide")
st.title("🏗️ By Project")
st.caption("Per-project P&L for clients with multi-project structures. "
           "Clients without a project label are excluded from this view.")

df_full = require_data()

if 'Project' not in df_full.columns:
    st.error(
        "The 'Project' column is missing from the loaded delivery data. "
        "Confirm the source workbook still has the Project column in Raw Data Source."
    )
    st.stop()

# Keep only rows with a non-blank Project value
df_full = df_full[
    df_full['Project'].notna()
    & (df_full['Project'].astype(str).str.strip() != '')
]

if df_full.empty:
    st.warning("No rows with a project label found.")
    st.stop()

df = sidebar_filters(df_full, page_key="project")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── Period mode ──────────────────────────────────────────────────────────────
view_mode = period_selector(page_key="project")
pop = pop_label(view_mode)

periods = get_available_periods(df, view_mode)
if not periods:
    st.warning("No periods available.")
    st.stop()

curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)
curr_df = selected_period_df(df, view_mode, page_key="project")
prev_df = filter_period(df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()
prev_lbl = prev_info[2] if prev_info else "—"

# ── Latest period snapshot ───────────────────────────────────────────────────
if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week Snapshot — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month Snapshot — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")


def fmt_delta(v):
    if v is None or pd.isna(v):
        return '—'
    return f"{'▲' if v > 0 else '▼'} {abs(v):.1f}%"


lw_agg = (
    curr_df.groupby('Project', observed=True)
    .agg(
        Volume=('Delivery Volume', 'sum'),
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Clients=('Client Name', 'nunique'),
    )
    .reset_index()
)
if not prev_df.empty:
    pw_agg = (
        prev_df.groupby('Project', observed=True)
        .agg(GP_prev=('GP', 'sum'), Revenue_prev=('Total Revenue', 'sum'))
        .reset_index()
    )
else:
    pw_agg = pd.DataFrame(columns=['Project', 'GP_prev', 'Revenue_prev'])

lw = lw_agg.merge(pw_agg, on='Project', how='left').fillna(0)
lw['GP Margin %'] = np.where(lw['Revenue'] != 0, lw['GP'] / lw['Revenue'] * 100, 0)
lw[f'GP {pop} %'] = lw.apply(lambda r: pop_pct(r['GP'], r['GP_prev']), axis=1)
lw = lw.sort_values('GP', ascending=False).reset_index(drop=True)

dataframe_with_freeze(
    lw[['Project', 'Clients', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %', f'GP {pop} %']],
    key="project_snapshot",
    default_freeze=['Project'],
    column_config={
        'Clients':     vol_col('Clients'),
        'Volume':      vol_col('Volume'),
        'Revenue':     idr_col('Revenue'),
        'Cost':        idr_col('Cost'),
        'GP':          idr_col('GP'),
        'GP Margin %': pct_col('Margin', signed=False),
        f'GP {pop} %': pct_col(f'GP {pop} %', signed=True),
    },
    width="stretch", hide_index=True, height=380,
)

st.divider()

# ── Period Rankings ──────────────────────────────────────────────────────────
st.subheader("Period Rankings (all filtered data)")
sort_col = st.selectbox("Sort by", ['GP', 'Revenue', 'Volume', 'GP Margin %'], index=0)

project_agg = (
    df.groupby('Project', observed=True)
    .agg(
        Volume=('Delivery Volume', 'sum'),
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Clients=('Client Name', 'nunique'),
    )
    .reset_index()
)
project_agg['GP Margin %'] = np.where(
    project_agg['Revenue'] != 0, project_agg['GP'] / project_agg['Revenue'] * 100, 0
)
project_agg = project_agg.sort_values(sort_col, ascending=False).reset_index(drop=True)

dataframe_with_freeze(
    project_agg[['Project', 'Clients', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %']],
    key="project_rankings",
    default_freeze=['Project'],
    column_config={
        'Clients':     vol_col('Clients'),
        'Volume':      vol_col('Volume'),
        'Revenue':     idr_col('Revenue'),
        'Cost':        idr_col('Cost'),
        'GP':          idr_col('GP'),
        'GP Margin %': pct_col('GP Margin %', signed=False),
    },
    width="stretch", hide_index=True,
)

# Top N bar chart
top_n = min(15, len(project_agg))
top_projects = project_agg.head(top_n)
fig_rank = px.bar(
    top_projects, x='Project', y=sort_col,
    color_discrete_sequence=[C_GP if sort_col == 'GP' else C_REVENUE],
    height=380, title=f"Top {top_n} Projects by {sort_col}",
)
fig_rank.update_layout(xaxis_tickangle=-25)
apply_chart_theme(fig_rank)
st.plotly_chart(fig_rank, width="stretch")

st.divider()

# ── Per-Client-Per-Project matrix ────────────────────────────────────────────
st.subheader("Per-Client-Per-Project Breakdown")
st.caption("Every (client, project) pair across the filtered period. "
           "Use the search box to narrow down.")

cp_agg = (
    df.groupby(['Client Name', 'Project'], observed=True)
    .agg(
        Volume=('Delivery Volume', 'sum'),
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
    )
    .reset_index()
)
cp_agg['Margin %'] = np.where(
    cp_agg['Revenue'] != 0, cp_agg['GP'] / cp_agg['Revenue'] * 100, 0
)
cp_agg = cp_agg.sort_values('GP', ascending=False).reset_index(drop=True)

cp_search = st.text_input(
    "Filter by client or project name", "",
    key="project_cp_filter",
    placeholder="e.g. JNT, last-mile, …",
)
if cp_search:
    mask = (
        cp_agg['Client Name'].str.contains(cp_search, case=False, na=False)
        | cp_agg['Project'].str.contains(cp_search, case=False, na=False)
    )
    cp_view = cp_agg[mask]
else:
    cp_view = cp_agg

if cp_view.empty:
    st.info("No (client, project) pairs match the search.")
else:
    dataframe_with_freeze(
        cp_view[['Client Name', 'Project', 'Volume', 'Revenue', 'Cost', 'GP', 'Margin %']],
        key="project_client_project_matrix",
        default_freeze=['Client Name', 'Project'],
        column_config={
            'Volume':   vol_col('Volume'),
            'Revenue':  idr_col('Revenue'),
            'Cost':     idr_col('Cost'),
            'GP':       idr_col('GP'),
            'Margin %': pct_col('Margin', signed=False),
        },
        width="stretch", hide_index=True, height=420,
    )

st.divider()

# ── Client → Project drilldown ───────────────────────────────────────────────
st.subheader("Client → Project Drilldown")
st.caption("Pick a client to see how their volume and P&L split across projects.")

all_clients_proj = sorted(df['Client Name'].dropna().unique().tolist())
sel_client_proj = st.selectbox(
    "Client", all_clients_proj, index=None,
    key="project_client_drilldown",
    placeholder="Select a client…",
)

if sel_client_proj is None:
    st.info("Select a client above to see their project breakdown.")
else:
    cdf = df[df['Client Name'] == sel_client_proj].copy()
    if cdf.empty:
        st.warning("No data for the selected client under current filters.")
    else:
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("Revenue", fmt_idr(cdf['Total Revenue'].sum()))
        s2.metric("Cost",    fmt_idr(cdf['Total Cost'].sum()))
        s3.metric("GP",      fmt_idr(cdf['GP'].sum()))
        cmargin = cdf['GP'].sum() / cdf['Total Revenue'].sum() * 100 if cdf['Total Revenue'].sum() else 0
        s4.metric("Margin",  fmt_pct(cmargin))
        s5.metric("Volume",  fmt_vol(cdf['Delivery Volume'].sum()))

        st.markdown(f"#### {sel_client_proj} — Project Breakdown")
        proj_c = (
            cdf.groupby('Project', observed=True)
            .agg(
                Volume=('Delivery Volume', 'sum'),
                Revenue=('Total Revenue', 'sum'),
                Cost=('Total Cost', 'sum'),
                GP=('GP', 'sum'),
            )
            .reset_index()
        )
        proj_c['GP Margin %'] = np.where(
            proj_c['Revenue'] != 0, proj_c['GP'] / proj_c['Revenue'] * 100, 0
        )
        proj_c = proj_c.sort_values('GP', ascending=False).reset_index(drop=True)

        if proj_c.empty:
            st.info("This client has no Project data under the current filters.")
        else:
            dataframe_with_freeze(
                proj_c[['Project', 'Volume', 'Revenue', 'Cost', 'GP', 'GP Margin %']],
                key="project_client_drill_table",
                default_freeze=['Project'],
                column_config={
                    'Volume':      vol_col('Volume'),
                    'Revenue':     idr_col('Revenue'),
                    'Cost':        idr_col('Cost'),
                    'GP':          idr_col('GP'),
                    'GP Margin %': pct_col('Margin', signed=False),
                },
                width="stretch", hide_index=True,
            )

            st.markdown(f"#### {view_mode} Trend Stacked by Project")
            trend_c = build_trend(cdf, ['Project'], view_mode)
            tab_gp, tab_vol = st.tabs(["GP", "Volume"])
            with tab_gp:
                fig_gp = px.bar(
                    trend_c, x='Label', y='GP', color='Project',
                    height=380, labels={'GP': 'GP (IDR)', 'Label': 'Period'},
                )
                fig_gp.update_layout(barmode='stack', xaxis_tickangle=-45)
                apply_chart_theme(fig_gp)
                st.plotly_chart(fig_gp, width="stretch")
            with tab_vol:
                fig_v = px.bar(
                    trend_c, x='Label', y='Volume', color='Project',
                    height=380, labels={'Volume': 'Deliveries', 'Label': 'Period'},
                )
                fig_v.update_layout(barmode='stack', xaxis_tickangle=-45)
                apply_chart_theme(fig_v)
                st.plotly_chart(fig_v, width="stretch")

st.divider()

# ── Project Drilldown ────────────────────────────────────────────────────────
st.subheader("Project Drilldown")
dd_left, dd_right = st.columns([2, 2])
with dd_left:
    sel_project = st.selectbox("Select a project", sorted(df['Project'].dropna().unique()))
# Offer only dimensions that actually exist in the filtered slice
_deeper_choices = [c for c in ['Client Location', 'Blitz Team', 'SLA Type', 'Client Level']
                   if c in df.columns]
with dd_right:
    deeper_dim = st.selectbox(
        "Then break down by",
        ["—"] + _deeper_choices,
        index=0, key="project_drill_deeper",
        help="Pick a secondary dimension to split this project's clients further "
             "(e.g. by Location to see geographic mix).",
    )
pdf = df[df['Project'] == sel_project].copy()

if pdf.empty:
    st.stop()

# Optional client-scoped drill — independent of the dimension selector above.
# Renders a (project, client) section further down between the clients table
# and the deeper-dimension breakdown.
sel_client_in_project = st.selectbox(
    "Drill into a specific client (optional)",
    ['(All clients in this project)'] + sorted(pdf['Client Name'].dropna().unique().tolist()),
    key="proj_drill_client",
    help="Pick one client to see KPIs, a 12-period trend, and cost mix scoped to "
         "this (project, client) pair. Independent of the dimension selector above.",
)

# Project-level KPIs
ck1, ck2, ck3, ck4, ck5 = st.columns(5)
ck1.metric("Revenue", fmt_idr(pdf['Total Revenue'].sum()))
ck2.metric("Cost", fmt_idr(pdf['Total Cost'].sum()))
ck3.metric("GP", fmt_idr(pdf['GP'].sum()))
gpm_p = pdf['GP'].sum() / pdf['Total Revenue'].sum() * 100 if pdf['Total Revenue'].sum() else 0
ck4.metric("Margin", fmt_pct(gpm_p))
ck5.metric("Volume", fmt_vol(pdf['Delivery Volume'].sum()))

# Clients within this project
st.markdown("#### Clients in this project")
client_in_proj = (
    pdf.groupby('Client Name', observed=True)
    .agg(Volume=('Delivery Volume', 'sum'),
         Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'),
         GP=('GP', 'sum'))
    .reset_index()
)
client_in_proj['Margin %'] = np.where(
    client_in_proj['Revenue'] != 0,
    client_in_proj['GP'] / client_in_proj['Revenue'] * 100, 0
)
client_in_proj = client_in_proj.sort_values('GP', ascending=False)

dataframe_with_freeze(
    client_in_proj[['Client Name', 'Volume', 'Revenue', 'Cost', 'GP', 'Margin %']],
    key="project_client_in_proj",
    default_freeze=['Client Name'],
    column_config={
        'Volume':   vol_col('Volume'),
        'Revenue':  idr_col('Revenue'),
        'Cost':     idr_col('Cost'),
        'GP':       idr_col('GP'),
        'Margin %': pct_col('Margin', signed=False),
    },
    width="stretch", hide_index=True,
)

# ── Per-(project, client) drilldown (Spec 2.3/2.4) ───────────────────────────
if sel_client_in_project != '(All clients in this project)':
    cdf_pc = pdf[pdf['Client Name'] == sel_client_in_project].copy()
    if cdf_pc.empty:
        st.info(f"No data for {sel_client_in_project} under {sel_project} with current filters.")
    else:
        st.markdown(f"#### {sel_project} → {sel_client_in_project}")

        # 5-column KPI strip scoped to this (project, client) pair
        rev_pc = cdf_pc['Total Revenue'].sum()
        cst_pc = cdf_pc['Total Cost'].sum()
        gp_pc  = cdf_pc['GP'].sum()
        mg_pc  = (gp_pc / rev_pc * 100) if rev_pc else 0
        vol_pc = cdf_pc['Delivery Volume'].sum()
        kc1, kc2, kc3, kc4, kc5 = st.columns(5)
        kc1.metric("Revenue", fmt_idr(rev_pc))
        kc2.metric("Cost",    fmt_idr(cst_pc))
        kc3.metric("GP",      fmt_idr(gp_pc))
        kc4.metric("Margin",  fmt_pct(mg_pc))
        kc5.metric("Volume",  fmt_vol(vol_pc))

        # 12-period trend (Revenue & Cost bars, GP line)
        trend_pc = build_trend(cdf_pc, [], view_mode).tail(12)
        if not trend_pc.empty:
            fig_pc = go.Figure()
            fig_pc.add_bar(x=trend_pc['Label'], y=trend_pc['Revenue'], name='Revenue',
                           marker_color=C_REVENUE, opacity=0.8)
            fig_pc.add_bar(x=trend_pc['Label'], y=trend_pc['Cost'], name='Cost',
                           marker_color=C_COST, opacity=0.8)
            fig_pc.add_scatter(x=trend_pc['Label'], y=trend_pc['GP'], mode='lines+markers',
                               name='GP', line=dict(color=C_GP, width=2))
            fig_pc.update_layout(
                barmode='group', height=380, yaxis_title='IDR', xaxis_tickangle=-45,
                title=f"{sel_client_in_project} — last 12 {view_mode.lower()} periods"
            )
            apply_chart_theme(fig_pc)
            st.plotly_chart(fig_pc, width="stretch")

        # Cost waterfall — pie of components present for this (project, client)
        cost_data_pc = {
            label: cdf_pc[col].sum() for col, label in COST_COMPONENTS.items()
            if col in cdf_pc.columns and cdf_pc[col].sum() > 0
        }
        if cost_data_pc:
            cost_df_pc = pd.DataFrame({
                'Component': list(cost_data_pc.keys()),
                'Amount':    list(cost_data_pc.values()),
            })
            fig_wf_pc = px.pie(
                cost_df_pc, values='Amount', names='Component', hole=0.35,
                height=360, title=f"{sel_client_in_project} — Cost Structure",
            )
            apply_chart_theme(fig_wf_pc)
            st.plotly_chart(fig_wf_pc, width="stretch")

# ── Deeper breakdown (optional, controlled by selector above) ────────────────
if deeper_dim != "—":
    st.markdown(f"#### {sel_project} — by {deeper_dim}")
    deeper_slice = pdf[pdf[deeper_dim].notna()
                       & (pdf[deeper_dim].astype(str).str.strip() != '')]
    if deeper_slice.empty:
        st.info(f"No rows in this project carry a {deeper_dim} value.")
    else:
        deeper_agg = (
            deeper_slice.groupby(deeper_dim, observed=True)
            .agg(
                Clients=('Client Name', 'nunique'),
                Volume=('Delivery Volume', 'sum'),
                Revenue=('Total Revenue', 'sum'),
                Cost=('Total Cost', 'sum'),
                GP=('GP', 'sum'),
            )
            .reset_index()
        )
        deeper_agg['Margin %'] = np.where(
            deeper_agg['Revenue'] != 0,
            deeper_agg['GP'] / deeper_agg['Revenue'] * 100, 0
        )
        deeper_agg = deeper_agg.sort_values('GP', ascending=False).reset_index(drop=True)

        dataframe_with_freeze(
            deeper_agg[[deeper_dim, 'Clients', 'Volume', 'Revenue', 'Cost', 'GP', 'Margin %']],
            key=f"project_deeper_{deeper_dim.replace(' ', '_').lower()}",
            default_freeze=[deeper_dim],
            column_config={
                'Clients':  vol_col('Clients'),
                'Volume':   vol_col('Volume'),
                'Revenue':  idr_col('Revenue'),
                'Cost':     idr_col('Cost'),
                'GP':       idr_col('GP'),
                'Margin %': pct_col('Margin', signed=False),
            },
            width="stretch", hide_index=True,
        )

        # Stacked GP trend by the chosen dimension
        deeper_trend = build_trend(deeper_slice, [deeper_dim], view_mode)
        fig_deeper = px.bar(
            deeper_trend, x='Label', y='GP', color=deeper_dim,
            height=360, labels={'GP': 'GP (IDR)', 'Label': 'Period'},
            title=f"{view_mode} GP — {sel_project} stacked by {deeper_dim}",
        )
        fig_deeper.update_layout(barmode='stack', xaxis_tickangle=-45)
        apply_chart_theme(fig_deeper)
        st.plotly_chart(fig_deeper, width="stretch")

# Trend
st.markdown(f"#### {view_mode} P&L Trend")
trend_p = build_trend(pdf, [], view_mode)
trend_p['GP Margin %'] = np.where(
    trend_p['Revenue'] != 0, trend_p['GP'] / trend_p['Revenue'] * 100, 0
)
for m in ['Revenue', 'GP', 'Volume']:
    trend_p[f'{m} PoP%'] = trend_p[m].pct_change() * 100

fig = go.Figure()
fig.add_bar(x=trend_p['Label'], y=trend_p['Revenue'], name='Revenue',
            marker_color=C_REVENUE, opacity=0.8)
fig.add_bar(x=trend_p['Label'], y=trend_p['Cost'], name='Cost',
            marker_color=C_COST, opacity=0.8)
fig.add_scatter(x=trend_p['Label'], y=trend_p['GP'], mode='lines+markers',
                name='GP', line=dict(color=C_GP, width=2))
fig.update_layout(barmode='group', height=400, yaxis_title='IDR',
                  xaxis_tickangle=-45, title=f"{sel_project} — {view_mode} P&L")
apply_chart_theme(fig)
st.plotly_chart(fig, width="stretch")


dataframe_with_freeze(
    trend_p[['Label', 'Volume', 'Volume PoP%', 'Revenue', 'Revenue PoP%',
             'Cost', 'GP', 'GP PoP%', 'GP Margin %']],
    key="project_drilldown_trend",
    default_freeze=['Label'],
    column_config={
        'Label':        st.column_config.TextColumn('Period'),
        'Volume':       vol_col('Volume'),
        'Volume PoP%':  pct_col('Vol PoP%', signed=True),
        'Revenue':      idr_col('Revenue'),
        'Revenue PoP%': pct_col('Rev PoP%', signed=True),
        'Cost':         idr_col('Cost'),
        'GP':           idr_col('GP'),
        'GP PoP%':      pct_col('GP PoP%', signed=True),
        'GP Margin %':  pct_col('Margin', signed=False),
    },
    width="stretch", hide_index=True,
)

# Cost structure pie
cost_data = {label: pdf[col].sum() for col, label in COST_COMPONENTS.items()
             if col in pdf.columns and pdf[col].sum() > 0}
if cost_data:
    cost_df = pd.DataFrame({'Component': list(cost_data.keys()), 'Amount': list(cost_data.values())})
    fig_cost = px.pie(cost_df, values='Amount', names='Component', hole=0.35,
                      height=360, title=f"{sel_project} — Cost Structure")
    apply_chart_theme(fig_cost)
    st.plotly_chart(fig_cost, width="stretch")
