"""Group Overview — cross-company monthly view (Blitz Delivery + Blitz Mobile + Borzo)."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils import (
    fmt_idr, fmt_pct, fmt_vol, MONTH_ORDER,
    C_REVENUE, C_COST, C_GP, C_VOLUME, C_NEUTRAL,
    get_blitz_delivery_optional, get_blitz_mobile_optional,
    get_borzo_monthly_optional,
    blitz_delivery_monthly, blitz_mobile_monthly, borzo_monthly_std,
)

st.set_page_config(page_title="Group Overview | Blitz", page_icon="🌐", layout="wide")
st.title("🌐 Group Overview")
st.caption("Monthly revenue, cost, and gross profit across Blitz & Borzo. "
           "Terminology normalized: **Revenue = GMV**, **GP = Margin/Commission**.")

# ── Build the cross-company monthly dataset ────────────────────────────────────
blitz_del   = get_blitz_delivery_optional()
blitz_mob   = get_blitz_mobile_optional()
borzo_mon   = get_borzo_monthly_optional()

frames = []
if blitz_del is not None:
    frames.append(blitz_delivery_monthly(blitz_del))
if blitz_mob is not None:
    frames.append(blitz_mobile_monthly(blitz_mob))
if borzo_mon is not None:
    frames.append(borzo_monthly_std(borzo_mon))

frames = [f for f in frames if f is not None and not f.empty]
if not frames:
    st.warning("⚠️ No company data available. Ask your admin to publish data via the Updater page.")
    st.stop()

all_df = pd.concat(frames, ignore_index=True)
all_df['Month'] = pd.Categorical(all_df['Month'], categories=MONTH_ORDER, ordered=True)
all_df['MonthNum'] = all_df['Month'].cat.codes + 1
all_df['GP Margin %'] = all_df.apply(
    lambda r: (r['GP'] / r['Revenue'] * 100) if r['Revenue'] else 0, axis=1
)
all_df['Period'] = all_df['Year'].astype(int).astype(str) + '-' + \
                   all_df['MonthNum'].astype(int).astype(str).str.zfill(2)

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Group Filters")

    streams_avail = sorted(all_df['Stream'].unique().tolist())
    sel_streams = st.multiselect("Streams", streams_avail, default=streams_avail)

    years_avail = sorted(all_df['Year'].dropna().astype(int).unique().tolist())
    sel_years = st.multiselect("Years", years_avail, default=years_avail)

    st.caption("Filter which companies/streams and years are included.")

fdf = all_df[all_df['Stream'].isin(sel_streams) & all_df['Year'].isin(sel_years)].copy()

if fdf.empty:
    st.info("No rows for the selected filters.")
    st.stop()

# ── KPI row — latest common month ──────────────────────────────────────────────
fdf = fdf.sort_values(['Year', 'MonthNum'])
latest = fdf.groupby(['Year', 'MonthNum']).size().reset_index().tail(1).iloc[0]
latest_y, latest_m = int(latest['Year']), int(latest['MonthNum'])
latest_label = f"{MONTH_ORDER[latest_m - 1]} {latest_y}"

cur = fdf[(fdf['Year'] == latest_y) & (fdf['MonthNum'] == latest_m)]

# Prior month in the filtered set
unique_months = (fdf[['Year', 'MonthNum']].drop_duplicates()
                 .sort_values(['Year', 'MonthNum']).reset_index(drop=True))
prev_row = None
for i, r in unique_months.iterrows():
    if int(r['Year']) == latest_y and int(r['MonthNum']) == latest_m and i > 0:
        prev_row = unique_months.iloc[i - 1]
        break
prev = fdf[(fdf['Year'] == int(prev_row['Year'])) & (fdf['MonthNum'] == int(prev_row['MonthNum']))] \
       if prev_row is not None else None

def sumcol(d, c):
    return d[c].sum() if d is not None and not d.empty else 0

def mom(curr_v, prev_v):
    if prev_v in (0, None) or prev_v == 0:
        return None
    return (curr_v - prev_v) / abs(prev_v) * 100

cur_rev = sumcol(cur, 'Revenue'); prev_rev = sumcol(prev, 'Revenue')
cur_cost = sumcol(cur, 'Cost');    prev_cost = sumcol(prev, 'Cost')
cur_gp = sumcol(cur, 'GP');        prev_gp = sumcol(prev, 'GP')
cur_margin = (cur_gp / cur_rev * 100) if cur_rev else 0
prev_margin = (prev_gp / prev_rev * 100) if prev_rev else None

st.subheader(f"📊 Group KPIs — {latest_label}")
k1, k2, k3, k4 = st.columns(4)
rev_p = mom(cur_rev, prev_rev)
k1.metric("Revenue (GMV)", fmt_idr(cur_rev),
          f"{rev_p:+.1f}% MoM" if rev_p is not None else None)
cost_p = mom(cur_cost, prev_cost)
k2.metric("Cost", fmt_idr(cur_cost),
          f"{cost_p:+.1f}% MoM" if cost_p is not None else None,
          delta_color="inverse")
gp_p = mom(cur_gp, prev_gp)
k3.metric("GP (Margin)", fmt_idr(cur_gp),
          f"{gp_p:+.1f}% MoM" if gp_p is not None else None)
margin_p = cur_margin - prev_margin if prev_margin is not None else None
k4.metric("GP Margin %", fmt_pct(cur_margin),
          f"{margin_p:+.1f}pp MoM" if margin_p is not None else None)

st.divider()

# ── Grouped monthly bars by stream ─────────────────────────────────────────────
st.subheader("📈 Monthly Revenue (GMV) by Stream")
fdf_plot = fdf.copy().sort_values(['Year', 'MonthNum'])
fig = px.bar(
    fdf_plot, x='Period', y='Revenue', color='Stream',
    barmode='group',
    color_discrete_map={
        'Blitz — Delivery':       '#1976D2',
        'Blitz — Mobile Sellers': '#F57C00',
        'Borzo — 3PL':            '#7B1FA2',
    }
)
fig.update_layout(
    template='plotly_white', height=420, yaxis_title='IDR',
    hovermode='x unified', legend=dict(orientation='h', y=1.08),
    bargap=0.15, bargroupgap=0.05
)
st.plotly_chart(fig, use_container_width=True)

# ── GP & GP Margin by company ──────────────────────────────────────────────────
g_col1, g_col2 = st.columns(2)

with g_col1:
    st.markdown("#### GP by Stream (monthly)")
    fig_gp = px.line(
        fdf_plot, x='Period', y='GP', color='Stream', markers=True,
        color_discrete_map={
            'Blitz — Delivery':       '#1976D2',
            'Blitz — Mobile Sellers': '#F57C00',
            'Borzo — 3PL':            '#7B1FA2',
        }
    )
    fig_gp.update_layout(template='plotly_white', height=360,
                         yaxis_title='IDR', hovermode='x unified',
                         legend=dict(orientation='h', y=1.08))
    st.plotly_chart(fig_gp, use_container_width=True)

with g_col2:
    st.markdown("#### GP Margin % by Stream")
    fig_m = px.line(
        fdf_plot, x='Period', y='GP Margin %', color='Stream', markers=True,
        color_discrete_map={
            'Blitz — Delivery':       '#1976D2',
            'Blitz — Mobile Sellers': '#F57C00',
            'Borzo — 3PL':            '#7B1FA2',
        }
    )
    fig_m.update_layout(template='plotly_white', height=360,
                        yaxis_title='%', hovermode='x unified',
                        legend=dict(orientation='h', y=1.08))
    st.plotly_chart(fig_m, use_container_width=True)

st.divider()

# ── Latest-month contribution pie ──────────────────────────────────────────────
st.subheader(f"🥧 Stream Contribution — {latest_label}")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Revenue (GMV) share**")
    contrib = cur.groupby('Stream', as_index=False)['Revenue'].sum()
    if not contrib.empty and contrib['Revenue'].sum() > 0:
        fig_pie = px.pie(contrib, names='Stream', values='Revenue', hole=0.5)
        fig_pie.update_layout(template='plotly_white', height=320,
                              legend=dict(orientation='h', y=-0.1))
        st.plotly_chart(fig_pie, use_container_width=True)

with c2:
    st.markdown("**GP share**")
    contrib_gp = cur.groupby('Stream', as_index=False)['GP'].sum()
    if not contrib_gp.empty and contrib_gp['GP'].sum() > 0:
        fig_pie2 = px.pie(contrib_gp, names='Stream', values='GP', hole=0.5)
        fig_pie2.update_layout(template='plotly_white', height=320,
                               legend=dict(orientation='h', y=-0.1))
        st.plotly_chart(fig_pie2, use_container_width=True)

# ── Data table ─────────────────────────────────────────────────────────────────
st.divider()
st.subheader("📋 Monthly Detail")
tbl = fdf[['Year', 'Month', 'Stream', 'Revenue', 'Cost', 'GP', 'GP Margin %', 'Volume']].copy()
tbl = tbl.sort_values(['Year', 'MonthNum' if 'MonthNum' in tbl.columns else 'Month', 'Stream'],
                      na_position='last') if 'MonthNum' in fdf.columns else tbl
# Re-sort by Period safely
tbl = fdf[['Year', 'Month', 'Stream', 'Revenue', 'Cost', 'GP', 'GP Margin %', 'Volume']]\
        .sort_values(['Year', 'Month', 'Stream'])
tbl_disp = tbl.copy()
tbl_disp['Revenue'] = tbl_disp['Revenue'].apply(fmt_idr)
tbl_disp['Cost']    = tbl_disp['Cost'].apply(fmt_idr)
tbl_disp['GP']      = tbl_disp['GP'].apply(fmt_idr)
tbl_disp['GP Margin %'] = tbl_disp['GP Margin %'].apply(lambda v: fmt_pct(v))
tbl_disp['Volume']  = tbl_disp['Volume'].apply(fmt_vol)
st.dataframe(tbl_disp, use_container_width=True, hide_index=True)
