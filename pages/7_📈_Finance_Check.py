import streamlit as st
import pandas as pd
import plotly.express as px
from utils import (require_data, sidebar_filters, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER)

st.set_page_config(page_title="Finance Check | Blitz", page_icon="📈", layout="wide")
st.title("📈 Finance Check")
st.caption("Year-over-year comparison and anomaly detection.")

df_full = require_data()
df = sidebar_filters(df_full, page_key="finance")

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# ── YoY summary ────────────────────────────────────────────────────────────────
st.subheader("Year-over-Year Summary")

yoy = (
    df.groupby('Year', observed=True)
    .agg(
        Volume=('Delivery Volume', 'sum'),
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Rider=('Rider Cost', 'sum'),
        OEM=('OEM Cost', 'sum'),
        MidMile=('Mid-Mile/ Linehaul Cost', 'sum'),
        ThreePL=('Add. 3PL Cost', 'sum'),
        EV_Rev=('EV Revenue + Battery (Rental Client)', 'sum'),
        EV_Red=('EV Reduction (3PL & KSJ)', 'sum'),
    )
    .reset_index()
)
yoy['GP Margin %'] = yoy.apply(lambda r: r['GP'] / r['Revenue'] * 100 if r['Revenue'] else 0, axis=1)
yoy['Rider %']     = yoy.apply(lambda r: r['Rider'] / r['Revenue'] * 100 if r['Revenue'] else 0, axis=1)

# Display formatted
disp = yoy.copy()
for col in ['Revenue', 'Cost', 'GP', 'Rider', 'OEM', 'MidMile', 'ThreePL', 'EV_Rev', 'EV_Red']:
    disp[col] = disp[col].apply(fmt_idr)
disp['GP Margin %'] = disp['GP Margin %'].apply(fmt_pct)
disp['Rider %']     = disp['Rider %'].apply(fmt_pct)
disp['Volume']      = disp['Volume'].apply(fmt_vol)

st.dataframe(disp.rename(columns={
    'EV_Rev': 'EV Revenue',
    'EV_Red': 'EV Reduction',
    'MidMile': 'Mid-Mile',
    'ThreePL': '3PL',
    'Rider': 'Rider Cost',
    'OEM': 'OEM Cost',
}), use_container_width=True, hide_index=True)

st.divider()

# ── YoY GP waterfall chart ────────────────────────────────────────────────────
st.subheader("GP by Year")

fig_yoy = px.bar(
    yoy, x='Year', y='GP',
    color='GP', color_continuous_scale=['red', 'yellow', 'green'],
    template='plotly_white', height=350,
    title="Gross Profit by Year",
    labels={'GP': 'Gross Profit (IDR)'}
)
fig_yoy.update_coloraxes(showscale=False)
st.plotly_chart(fig_yoy, use_container_width=True)

st.divider()

# ── By Team × Year ────────────────────────────────────────────────────────────
st.subheader("Team × Year Comparison")

team_year = (
    df.groupby(['Blitz Team', 'Year'], observed=True)
    .agg(Revenue=('Total Revenue', 'sum'),
         Cost=('Total Cost', 'sum'),
         GP=('GP', 'sum'),
         Volume=('Delivery Volume', 'sum'))
    .reset_index()
)
team_year['GP Margin %'] = team_year.apply(
    lambda r: r['GP'] / r['Revenue'] * 100 if r['Revenue'] else 0, axis=1
)

fig_ty = px.bar(
    team_year, x='Year', y='GP', color='Blitz Team', barmode='group',
    color_discrete_map={'Jakarta': C_REVENUE, 'Surabaya': C_GP},
    template='plotly_white', height=380,
    title="GP by Team & Year",
    labels={'GP': 'Gross Profit (IDR)'}
)
fig_ty.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.05))
st.plotly_chart(fig_ty, use_container_width=True)

st.divider()

# ── Monthly YoY ───────────────────────────────────────────────────────────────
st.subheader("Monthly YoY — GP Comparison")

monthly_yoy = (
    df.groupby(['Year', 'Month'], observed=True)
    .agg(GP=('GP', 'sum'), Revenue=('Total Revenue', 'sum'), Volume=('Delivery Volume', 'sum'))
    .reset_index()
)
monthly_yoy['Month'] = pd.Categorical(monthly_yoy['Month'], categories=MONTH_ORDER, ordered=True)
monthly_yoy = monthly_yoy.sort_values(['Year', 'Month'])

fig_myoy = px.line(
    monthly_yoy, x='Month', y='GP', color='Year',
    markers=True, template='plotly_white', height=380,
    title="Monthly GP — Year over Year",
    labels={'GP': 'Gross Profit (IDR)'}
)
fig_myoy.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.05))
fig_myoy.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.4)
st.plotly_chart(fig_myoy, use_container_width=True)

st.divider()

# ── Anomaly flagging ──────────────────────────────────────────────────────────
st.subheader("🚨 Anomaly Detection")
st.caption("Clients with a GP swing of more than 50% between their best and worst weeks.")

client_weekly = (
    df.groupby(['Client Name', 'Year', 'Week (by Year)'], observed=True)
    .agg(GP=('GP', 'sum'), Revenue=('Total Revenue', 'sum'))
    .reset_index()
)

anomalies = []
for client, cdf in client_weekly.groupby('Client Name', observed=True):
    if len(cdf) < 2:
        continue
    gp_std = cdf['GP'].std()
    gp_mean = cdf['GP'].mean()
    if gp_mean != 0:
        cv = abs(gp_std / gp_mean) * 100
        if cv > 50:
            anomalies.append({
                'Client': client,
                'Avg GP': fmt_idr(gp_mean),
                'GP Std Dev': fmt_idr(gp_std),
                'Coefficient of Variation': f"{cv:.0f}%",
                'Min GP': fmt_idr(cdf['GP'].min()),
                'Max GP': fmt_idr(cdf['GP'].max()),
            })

if anomalies:
    anom_df = pd.DataFrame(anomalies).sort_values('Coefficient of Variation', ascending=False)
    st.warning(f"⚠️ {len(anom_df)} clients show high GP variability (CoV > 50%)")
    st.dataframe(anom_df, use_container_width=True, hide_index=True)
else:
    st.success("✅ No anomalous GP variability detected.")
