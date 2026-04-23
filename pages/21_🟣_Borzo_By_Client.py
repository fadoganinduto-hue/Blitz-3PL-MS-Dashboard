"""Borzo — By Client. Per-client drilldown (2025 coverage)."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils import (
    fmt_idr, fmt_pct, fmt_vol, MONTH_ORDER,
    C_REVENUE, C_COST, C_GP,
    require_borzo_clients,
)

st.set_page_config(page_title="Borzo By Client | Blitz", page_icon="🟣", layout="wide")
st.title("🟣 Borzo — By Client")
st.caption("Per-client breakdown. Currently 2025 only — historical data will arrive gradually. "
           "**Revenue = GMV**, **GP = Commission**, **Cost = Courier Cost**.")

df = require_borzo_clients()
if df.empty:
    st.info("No per-client data loaded.")
    st.stop()

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    years = sorted(df['Year'].dropna().astype(int).unique().tolist())
    sel_years = st.multiselect("Year", years, default=years, key="borzo_cl_year")

    months_avail = [m for m in MONTH_ORDER
                    if m in df['Month'].cat.categories and m in df['Month'].values]
    sel_months = st.multiselect("Month", months_avail, default=months_avail,
                                key="borzo_cl_month")

    min_gmv_m = st.number_input(
        "Minimum total GMV in selected period (Rp millions)",
        value=0, step=10, min_value=0,
        help="Hide tiny clients. 0 = show all."
    )

fdf = df.copy()
if sel_years:
    fdf = fdf[fdf['Year'].isin(sel_years)]
if sel_months:
    fdf = fdf[fdf['Month'].isin(sel_months)]

if fdf.empty:
    st.info("No rows for selected filters.")
    st.stop()

# Aggregate per client across the filtered period
by_client = (fdf.groupby(['ClientID', 'ClientName'], as_index=False)
               .agg(GMV=('GMV', 'sum'),
                    Cost=('CourierCost', 'sum'),
                    GP=('Commission', 'sum'),
                    Orders=('Orders', 'sum'),
                    Months=('MonthNum', 'nunique')))
by_client['GP Margin %'] = by_client.apply(
    lambda r: (r['GP'] / r['GMV'] * 100) if r['GMV'] else 0, axis=1
)

if min_gmv_m > 0:
    by_client = by_client[by_client['GMV'] >= min_gmv_m * 1e6]

if by_client.empty:
    st.info("No clients match the minimum GMV threshold.")
    st.stop()

# ── KPI row ────────────────────────────────────────────────────────────────────
total_gmv = by_client['GMV'].sum()
total_cost = by_client['Cost'].sum()
total_gp = by_client['GP'].sum()
n_clients = by_client['ClientID'].nunique()
overall_margin = total_gp / total_gmv * 100 if total_gmv else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Clients", fmt_vol(n_clients))
k2.metric("Revenue (GMV)", fmt_idr(total_gmv))
k3.metric("Cost (Courier)", fmt_idr(total_cost))
k4.metric("GP (Commission)", fmt_idr(total_gp))
k5.metric("GP Margin %", fmt_pct(overall_margin))

st.divider()

# ── Top clients by GMV ─────────────────────────────────────────────────────────
st.subheader("🏆 Top 15 Clients by GMV")
top = by_client.nlargest(15, 'GMV').copy()
top['ClientLabel'] = top['ClientName'].str.slice(0, 40)

fig_top = go.Figure()
fig_top.add_bar(y=top['ClientLabel'], x=top['GMV'], orientation='h',
                name='GMV', marker_color=C_REVENUE)
fig_top.add_bar(y=top['ClientLabel'], x=top['GP'], orientation='h',
                name='GP', marker_color=C_GP)
fig_top.update_layout(
    template='plotly_white', height=520, barmode='group',
    xaxis_title='IDR', yaxis=dict(autorange='reversed'),
    legend=dict(orientation='h', y=1.08)
)
st.plotly_chart(fig_top, use_container_width=True)

# ── Concentration — Pareto ─────────────────────────────────────────────────────
st.subheader("📊 Client Concentration (Pareto)")
pareto = by_client.sort_values('GMV', ascending=False).reset_index(drop=True).copy()
pareto['Cum GMV %'] = pareto['GMV'].cumsum() / pareto['GMV'].sum() * 100
pareto['Rank'] = pareto.index + 1

n80 = int((pareto['Cum GMV %'] <= 80).sum()) + 1
pct80 = n80 / len(pareto) * 100 if len(pareto) else 0

pc1, pc2 = st.columns([1, 2])
with pc1:
    st.metric(f"Clients driving 80% of GMV", f"{n80}",
              f"{pct80:.1f}% of all {len(pareto):,} clients")
    top10_share = pareto.head(10)['GMV'].sum() / pareto['GMV'].sum() * 100
    top50_share = pareto.head(50)['GMV'].sum() / pareto['GMV'].sum() * 100
    st.metric("Top 10 share", fmt_pct(top10_share))
    st.metric("Top 50 share", fmt_pct(top50_share))

with pc2:
    # Only plot the first ~200 for readability
    plot_n = min(200, len(pareto))
    fig_p = go.Figure()
    fig_p.add_bar(x=pareto['Rank'].head(plot_n), y=pareto['GMV'].head(plot_n),
                  name='GMV', marker_color=C_REVENUE)
    fig_p.add_scatter(x=pareto['Rank'].head(plot_n), y=pareto['Cum GMV %'].head(plot_n),
                      mode='lines', name='Cumulative GMV %',
                      line=dict(color=C_GP, width=2), yaxis='y2')
    fig_p.update_layout(
        template='plotly_white', height=380,
        xaxis_title=f'Client rank (top {plot_n} of {len(pareto):,})',
        yaxis_title='GMV (IDR)',
        yaxis2=dict(overlaying='y', side='right', title='Cumulative %',
                    range=[0, 105]),
        hovermode='x unified',
        legend=dict(orientation='h', y=1.08)
    )
    st.plotly_chart(fig_p, use_container_width=True)

st.divider()

# ── Client monthly trend (single-client drilldown) ─────────────────────────────
st.subheader("🔎 Client Drilldown — Monthly Trend")
client_choices = (by_client.sort_values('GMV', ascending=False)
                           .apply(lambda r: f"{r['ClientName']} (GMV {r['GMV']/1e6:,.0f}M)",
                                  axis=1).tolist())
client_ids = by_client.sort_values('GMV', ascending=False)['ClientID'].tolist()

if client_choices:
    sel_idx = st.selectbox("Pick a client", range(len(client_choices)),
                           format_func=lambda i: client_choices[i])
    cid = client_ids[sel_idx]
    client_df = fdf[fdf['ClientID'] == cid].copy()
    client_df['MonthNum'] = client_df['Month'].cat.codes + 1
    client_df = client_df.sort_values(['Year', 'MonthNum'])
    client_df['PeriodLabel'] = client_df['Year'].astype(int).astype(str) + ' ' + \
                               client_df['Month'].astype(str)

    fig_cl = go.Figure()
    fig_cl.add_bar(x=client_df['PeriodLabel'], y=client_df['GMV'],
                   name='GMV', marker_color=C_REVENUE)
    fig_cl.add_bar(x=client_df['PeriodLabel'], y=client_df['CourierCost'],
                   name='Courier Cost', marker_color=C_COST)
    fig_cl.add_bar(x=client_df['PeriodLabel'], y=client_df['Commission'],
                   name='Commission (GP)', marker_color=C_GP)
    fig_cl.update_layout(template='plotly_white', height=380,
                         barmode='group', yaxis_title='IDR',
                         hovermode='x unified',
                         legend=dict(orientation='h', y=1.08))
    st.plotly_chart(fig_cl, use_container_width=True)

    st.markdown("**Monthly detail for selected client**")
    cdisp = client_df[['Year', 'Month', 'Orders', 'GMV', 'CourierCost', 'Commission']].copy()
    cdisp['GP Margin %'] = cdisp.apply(
        lambda r: (r['Commission'] / r['GMV'] * 100) if r['GMV'] else 0, axis=1
    )
    for c in ['GMV', 'CourierCost', 'Commission']:
        cdisp[c] = cdisp[c].apply(fmt_idr)
    cdisp['Orders'] = cdisp['Orders'].apply(fmt_vol)
    cdisp['GP Margin %'] = cdisp['GP Margin %'].apply(fmt_pct)
    st.dataframe(cdisp.rename(columns={'GMV': 'Revenue (GMV)',
                                       'CourierCost': 'Cost (Courier)',
                                       'Commission': 'GP (Commission)'}),
                 use_container_width=True, hide_index=True)

st.divider()

# ── Full client table ──────────────────────────────────────────────────────────
st.subheader("📋 All Clients — Selected Period")
disp = by_client.sort_values('GMV', ascending=False).copy()
for c in ['GMV', 'Cost', 'GP']:
    disp[c] = disp[c].apply(fmt_idr)
disp['GP Margin %'] = disp['GP Margin %'].apply(fmt_pct)
disp['Orders'] = disp['Orders'].apply(fmt_vol)
disp = disp.rename(columns={'GMV': 'Revenue (GMV)',
                            'Cost': 'Cost (Courier)',
                            'GP': 'GP (Commission)',
                            'Months': '# Months Active'})
st.dataframe(disp, use_container_width=True, hide_index=True)
