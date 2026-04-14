import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, sidebar_filters, fmt_pct, fmt_vol,
                   C_GP, C_COST, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_label)

st.set_page_config(page_title="SLA Check | Blitz", page_icon="🎯", layout="wide")
st.title("🎯 SLA Check")
st.caption("On-time performance (OTP), late deliveries, and courier utilisation.")

df_full = require_data()

# Check if SLA data is available
has_sla = df_full['OTP Rate %'].notna().any()
if not has_sla:
    st.info(
        "**SLA data not found in the uploaded file.**\n\n"
        "This page requires the expanded Raw Data Source export (available from W12 onwards) "
        "which includes `#Ontime`, `#Late`, and `Deliveries` columns."
    )
    st.stop()

df = sidebar_filters(df_full, page_key="sla")
df = df[df['_total_deliveries'] > 0].copy()

if df.empty:
    st.warning("No SLA data matches the current filters.")
    st.stop()

# ── Period mode selector ───────────────────────────────────────────────────────
view_mode = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="sla_view")
pop = pop_label(view_mode)

periods   = get_available_periods(df, view_mode)
curr_yr, curr_p, curr_lbl = periods[-1]
prev_info = prev_period_info(periods, curr_yr, curr_p)

curr_df = filter_period(df, view_mode, curr_yr, curr_p)
prev_df = filter_period(df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()
prev_lbl = prev_info[2] if prev_info else "—"

# ── Latest period OTP snapshot ────────────────────────────────────────────────
if view_mode == "Weekly":
    date_lbl = curr_df['Date Range'].dropna().iloc[0] if not curr_df['Date Range'].dropna().empty else ''
    st.subheader(f"Latest Week — {curr_lbl}  ·  {date_lbl}")
else:
    st.subheader(f"Latest Month — {curr_lbl}")

if prev_info:
    st.caption(f"Comparing vs {prev_lbl}")

def otp_kpis(d):
    deliveries = d['_total_deliveries'].sum()
    ontime     = d['_total_ontime'].sum()
    late       = d['_total_late'].sum()
    otp        = ontime / deliveries * 100 if deliveries > 0 else 0.0
    return deliveries, ontime, late, otp

curr_del, curr_on, curr_late, curr_otp = otp_kpis(curr_df)
prev_del, prev_on, prev_late, prev_otp = otp_kpis(prev_df) if not prev_df.empty else (0, 0, 0, 0)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Deliveries (SLA tracked)", fmt_vol(curr_del),
          f"{curr_del - prev_del:+,.0f} {pop}" if prev_del else None)
k2.metric("On-Time", fmt_vol(curr_on))
k3.metric("Late",    fmt_vol(curr_late))
otp_delta = f"{curr_otp - prev_otp:+.1f}pp {pop}" if prev_otp else None
k4.metric("OTP Rate", fmt_pct(curr_otp), otp_delta,
          delta_color="normal" if (curr_otp - prev_otp) >= 0 else "inverse")

st.divider()

# ── OTP by Client ─────────────────────────────────────────────────────────────
st.subheader("OTP Rate by Client (Period)")

client_sla = (
    df.groupby('Client Name', observed=True)
    .agg(Deliveries=('_total_deliveries', 'sum'),
         Ontime=('_total_ontime', 'sum'),
         Late=('_total_late', 'sum'))
    .reset_index()
)
client_sla = client_sla[client_sla['Deliveries'] > 0].copy()
client_sla['OTP %'] = client_sla['Ontime'] / client_sla['Deliveries'] * 100
client_sla = client_sla.sort_values('OTP %', ascending=True)

fig_otp = px.bar(
    client_sla, x='OTP %', y='Client Name', orientation='h',
    color='OTP %', color_continuous_scale=['red', 'yellow', 'green'],
    color_continuous_midpoint=90,
    template='plotly_white', height=max(400, len(client_sla) * 25),
    title="On-Time Performance by Client (%)",
    labels={'OTP %': 'OTP Rate (%)', 'Client Name': ''}
)
fig_otp.add_vline(x=90, line_dash='dash', line_color='orange',
                  annotation_text="90% target", annotation_position="top right")
fig_otp.update_coloraxes(showscale=False)
st.plotly_chart(fig_otp, use_container_width=True)

disp_sla = client_sla.copy()
disp_sla['Deliveries'] = disp_sla['Deliveries'].apply(lambda v: f"{int(v):,}")
disp_sla['Ontime']     = disp_sla['Ontime'].apply(lambda v: f"{int(v):,}")
disp_sla['Late']       = disp_sla['Late'].apply(lambda v: f"{int(v):,}")
disp_sla['OTP %']      = disp_sla['OTP %'].apply(fmt_pct)
st.dataframe(
    disp_sla[['Client Name', 'Deliveries', 'Ontime', 'Late', 'OTP %']],
    use_container_width=True, hide_index=True
)

st.divider()

# ── OTP trend ─────────────────────────────────────────────────────────────────
st.subheader("OTP Trend Over Time")

if view_mode == "Weekly":
    trend_sla = (
        df.groupby(['Year', 'Week (by Year)'], observed=True)
        .agg(Deliveries=('_total_deliveries', 'sum'), Ontime=('_total_ontime', 'sum'))
        .reset_index().sort_values(['Year', 'Week (by Year)'])
    )
    trend_sla['Label'] = (trend_sla['Year'].astype(str) + ' W' +
                          trend_sla['Week (by Year)'].astype(int).astype(str))
else:
    trend_sla = (
        df.groupby(['Year', 'Month'], observed=True)
        .agg(Deliveries=('_total_deliveries', 'sum'), Ontime=('_total_ontime', 'sum'))
        .reset_index()
    )
    trend_sla['Month'] = pd.Categorical(trend_sla['Month'], categories=MONTH_ORDER, ordered=True)
    trend_sla = trend_sla.sort_values(['Year', 'Month'])
    trend_sla['Label'] = trend_sla['Year'].astype(str) + ' ' + trend_sla['Month'].astype(str)

trend_sla = trend_sla[trend_sla['Deliveries'] > 0].copy()
trend_sla['OTP %'] = trend_sla['Ontime'] / trend_sla['Deliveries'] * 100
# PoP % change for OTP
trend_sla['OTP PoP pp'] = trend_sla['OTP %'].diff()

fig_trend = go.Figure()
fig_trend.add_scatter(
    x=trend_sla['Label'], y=trend_sla['OTP %'],
    mode='lines+markers', name='OTP %',
    line=dict(color=C_GP, width=2), fill='tozeroy', fillcolor='rgba(76,175,80,0.1)',
    customdata=trend_sla['OTP PoP pp'],
    hovertemplate='%{x}<br>OTP: %{y:.1f}%<br>Change: %{customdata:+.1f}pp<extra></extra>'
)
fig_trend.add_hline(y=90, line_dash='dash', line_color='orange', annotation_text="90% target")
fig_trend.update_layout(
    template='plotly_white', height=380, hovermode='x unified',
    yaxis_title='OTP Rate (%)', yaxis_range=[0, 105],
    xaxis_tickangle=-45, title=f"OTP Rate — {view_mode} Trend"
)
st.plotly_chart(fig_trend, use_container_width=True)

st.divider()

# ── OTP by Team ───────────────────────────────────────────────────────────────
st.subheader("OTP by Blitz Team")

team_sla = (
    df.groupby('Blitz Team', observed=True)
    .agg(Deliveries=('_total_deliveries', 'sum'),
         Ontime=('_total_ontime', 'sum'),
         Late=('_total_late', 'sum'))
    .reset_index()
)
team_sla = team_sla[team_sla['Deliveries'] > 0].copy()
team_sla['OTP %'] = team_sla['Ontime'] / team_sla['Deliveries'] * 100

t_cols = st.columns(max(len(team_sla), 1))
for col, (_, row) in zip(t_cols, team_sla.iterrows()):
    col.metric(
        f"{row['Blitz Team']} OTP",
        fmt_pct(row['OTP %']),
        f"{int(row['Late']):,} late of {int(row['Deliveries']):,}"
    )

# OTP trend by team
if view_mode == "Weekly":
    team_trend = (
        df.groupby(['Blitz Team', 'Year', 'Week (by Year)'], observed=True)
        .agg(Deliveries=('_total_deliveries', 'sum'), Ontime=('_total_ontime', 'sum'))
        .reset_index().sort_values(['Year', 'Week (by Year)'])
    )
    team_trend['Label'] = (team_trend['Year'].astype(str) + ' W' +
                           team_trend['Week (by Year)'].astype(int).astype(str))
else:
    team_trend = (
        df.groupby(['Blitz Team', 'Year', 'Month'], observed=True)
        .agg(Deliveries=('_total_deliveries', 'sum'), Ontime=('_total_ontime', 'sum'))
        .reset_index()
    )
    team_trend['Month'] = pd.Categorical(team_trend['Month'], categories=MONTH_ORDER, ordered=True)
    team_trend = team_trend.sort_values(['Year', 'Month'])
    team_trend['Label'] = team_trend['Year'].astype(str) + ' ' + team_trend['Month'].astype(str)

team_trend = team_trend[team_trend['Deliveries'] > 0].copy()
team_trend['OTP %'] = team_trend['Ontime'] / team_trend['Deliveries'] * 100

fig_tt = px.line(
    team_trend, x='Label', y='OTP %', color='Blitz Team',
    markers=True, template='plotly_white', height=360,
    title=f"OTP Rate by Team — {view_mode}",
    color_discrete_map={'Jakarta': '#2196F3', 'Surabaya': '#4CAF50'}
)
fig_tt.add_hline(y=90, line_dash='dash', line_color='orange')
fig_tt.update_layout(hovermode='x unified', xaxis_tickangle=-45,
                     yaxis_range=[0, 105], legend=dict(orientation='h', y=1.05))
st.plotly_chart(fig_tt, use_container_width=True)
