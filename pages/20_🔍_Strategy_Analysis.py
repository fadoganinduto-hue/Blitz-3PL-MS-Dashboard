import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, require_mobile_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, C_VOLUME, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, build_trend, build_mobile_trend,
                   sidebar_filters)
from data_loader import mobile_aggregate

st.set_page_config(page_title="Strategy & Analysis | Blitz", page_icon="🔍", layout="wide")
st.title("🔍 Strategy & Analysis")
st.caption("Automated anomaly detection and key ratio monitoring. Flags significant changes post-upload to expedite decision making.")

# ── Configuration ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Analysis Settings")
    wow_threshold = st.slider("WoW Change Threshold (pp)", 1, 20, 5, key="wow_thresh",
                              help="Flag when a ratio changes by more than this many percentage points week-over-week")
    rolling_window = st.slider("Rolling Average Window (weeks)", 2, 8, 4, key="roll_window",
                               help="Number of weeks for rolling average baseline")
    rolling_threshold = st.slider("Rolling Avg Deviation Threshold (pp)", 1, 20, 5, key="roll_thresh",
                                  help="Flag when current deviates from rolling average by more than this")
    st.divider()

# ── Helper functions ──────────────────────────────────────────────────────────
def compute_ratios_delivery(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """Compute key financial ratios for Delivery data aggregated by period."""
    agg = df.groupby(group_cols, observed=True).agg(
        Revenue=('Total Revenue', 'sum'),
        Cost=('Total Cost', 'sum'),
        GP=('GP', 'sum'),
        Volume=('Delivery Volume', 'sum'),
        Rider_Cost=('Rider Cost', 'sum'),
        Manpower_Cost=('Manpower Cost', 'sum'),
        OEM_Cost=('OEM Cost', 'sum'),
        Del_Rev=('TOTAL DELIVERY REVENUE', 'sum'),
    ).reset_index()

    agg['Rider Cost % of Rev'] = np.where(agg['Revenue'] > 0, agg['Rider_Cost'] / agg['Revenue'] * 100, 0)
    agg['GP Margin %'] = np.where(agg['Revenue'] > 0, agg['GP'] / agg['Revenue'] * 100, 0)
    agg['Cost per Order'] = np.where(agg['Volume'] > 0, agg['Cost'] / agg['Volume'], 0)
    agg['Revenue per Order'] = np.where(agg['Volume'] > 0, agg['Revenue'] / agg['Volume'], 0)
    agg['Rider Cost per Order'] = np.where(agg['Volume'] > 0, agg['Rider_Cost'] / agg['Volume'], 0)
    agg['Manpower Cost % of Rev'] = np.where(agg['Revenue'] > 0, agg['Manpower_Cost'] / agg['Revenue'] * 100, 0)
    agg['Delivery Rev % of Total Rev'] = np.where(agg['Revenue'] > 0, agg['Del_Rev'] / agg['Revenue'] * 100, 0)
    agg['Delivery Rev per Order'] = np.where(agg['Volume'] > 0, agg['Del_Rev'] / agg['Volume'], 0)

    return agg


def compute_ratios_mobile(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """Compute key financial ratios for Mobile Sellers data."""
    agg = df.groupby(group_cols, observed=True).agg(
        Cups=('Total Cups Sold', 'sum'),
        GrossRevenue=('Gross Revenue', 'sum'),
        BlitzRevenue=('Blitz Revenue', 'sum'),
        COGS=('COGS', 'sum'),
        OpCost=('Total Operational Cost', 'sum'),
        Profit=('Profit Calc', 'sum'),
        Riders=('Total Active Riders', 'sum'),
    ).reset_index()

    agg['Profit Margin %'] = np.where(agg['GrossRevenue'] > 0, agg['Profit'] / agg['GrossRevenue'] * 100, 0)
    agg['COGS % of Rev'] = np.where(agg['GrossRevenue'] > 0, agg['COGS'] / agg['GrossRevenue'] * 100, 0)
    agg['OpCost % of Rev'] = np.where(agg['GrossRevenue'] > 0, agg['OpCost'] / agg['GrossRevenue'] * 100, 0)
    agg['Cups per Driver'] = np.where(agg['Riders'] > 0, agg['Cups'] / agg['Riders'], 0)
    agg['Revenue per Driver'] = np.where(agg['Riders'] > 0, agg['GrossRevenue'] / agg['Riders'], 0)
    agg['Revenue per Cup'] = np.where(agg['Cups'] > 0, agg['GrossRevenue'] / agg['Cups'], 0)
    agg['Profit per Cup'] = np.where(agg['Cups'] > 0, agg['Profit'] / agg['Cups'], 0)

    return agg


def flag_anomalies(series: pd.Series, wow_thresh: float, roll_win: int, roll_thresh: float) -> pd.DataFrame:
    """Detect anomalies using WoW change and rolling average deviation."""
    flags = pd.DataFrame(index=series.index)
    flags['Value'] = series
    flags['WoW Change (pp)'] = series.diff()
    flags['Rolling Avg'] = series.rolling(roll_win, min_periods=2).mean().shift(1)
    flags['Deviation from Avg (pp)'] = series - flags['Rolling Avg']

    flags['WoW Flag'] = flags['WoW Change (pp)'].abs() > wow_thresh
    flags['Rolling Flag'] = flags['Deviation from Avg (pp)'].abs() > roll_thresh
    flags['Any Flag'] = flags['WoW Flag'] | flags['Rolling Flag']

    return flags


def render_anomaly_section(ratio_df: pd.DataFrame, period_col: str, ratio_cols: dict,
                           wow_thresh: float, roll_win: int, roll_thresh: float,
                           stream_name: str):
    """Render anomaly detection results for a set of ratios."""
    all_flags = []

    for ratio_name, col in ratio_cols.items():
        if col not in ratio_df.columns:
            continue
        flags = flag_anomalies(ratio_df[col], wow_thresh, roll_win, roll_thresh)
        flagged = flags[flags['Any Flag'] == True]

        if not flagged.empty:
            for idx in flagged.index:
                period_label = ratio_df.loc[idx, period_col] if period_col in ratio_df.columns else str(idx)
                wow_change = flags.loc[idx, 'WoW Change (pp)']
                roll_dev = flags.loc[idx, 'Deviation from Avg (pp)']
                curr_val = flags.loc[idx, 'Value']
                roll_avg = flags.loc[idx, 'Rolling Avg']

                flag_type = []
                if flags.loc[idx, 'WoW Flag']:
                    flag_type.append(f"WoW Δ: {wow_change:+.1f}pp")
                if flags.loc[idx, 'Rolling Flag']:
                    flag_type.append(f"vs Avg: {roll_dev:+.1f}pp (avg: {roll_avg:.1f}%)")

                all_flags.append({
                    'Period': period_label,
                    'Metric': ratio_name,
                    'Current': f"{curr_val:.1f}%",
                    'Flags': ' | '.join(flag_type),
                    'Direction': '📈 Up' if (wow_change or 0) > 0 else '📉 Down',
                    'Severity': abs(wow_change or 0) + abs(roll_dev or 0),
                })

    if all_flags:
        flag_df = pd.DataFrame(all_flags).sort_values('Severity', ascending=False)

        # Highlight recent (last 4 periods) flags
        recent_periods = ratio_df[period_col].tail(4).tolist() if period_col in ratio_df.columns else []
        recent_flags = flag_df[flag_df['Period'].isin(recent_periods)]
        older_flags = flag_df[~flag_df['Period'].isin(recent_periods)]

        if not recent_flags.empty:
            st.markdown(f"**🚨 Recent Flags ({len(recent_flags)})**")
            st.dataframe(
                recent_flags[['Period', 'Metric', 'Current', 'Direction', 'Flags']],
                use_container_width=True, hide_index=True
            )

        if not older_flags.empty:
            with st.expander(f"Historical Flags ({len(older_flags)})"):
                st.dataframe(
                    older_flags[['Period', 'Metric', 'Current', 'Direction', 'Flags']],
                    use_container_width=True, hide_index=True
                )
    else:
        st.success(f"No anomalies detected for {stream_name} with current thresholds.")


# ══════════════════════════════════════════════════════════════════════════════
# DELIVERY ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
st.header("🚚 Delivery — Anomaly Detection")

try:
    df_del = require_data()
except SystemExit:
    df_del = None

if df_del is not None and not df_del.empty:
    # Compute weekly ratios at company level
    del_ratios = compute_ratios_delivery(df_del, ['Year', 'Week (by Year)'])
    del_ratios = del_ratios.sort_values(['Year', 'Week (by Year)'])
    del_ratios['Label'] = del_ratios['Year'].astype(str) + ' W' + del_ratios['Week (by Year)'].astype(int).astype(str)

    # Define ratio columns to monitor
    delivery_ratio_cols = {
        'Rider Cost % of Revenue': 'Rider Cost % of Rev',
        'GP Margin %': 'GP Margin %',
        'Manpower Cost % of Revenue': 'Manpower Cost % of Rev',
        'Delivery Rev % of Total Revenue': 'Delivery Rev % of Total Rev',
    }

    render_anomaly_section(del_ratios, 'Label', delivery_ratio_cols,
                           wow_threshold, rolling_window, rolling_threshold, "Delivery")

    # ── Ratio trend charts ────────────────────────────────────────────────────
    st.subheader("Key Ratio Trends")
    recent_del = del_ratios.tail(13)

    tab_rc, tab_gp, tab_cpo = st.tabs(["Rider Cost % of Rev", "GP Margin %", "Cost & Revenue per Order"])

    with tab_rc:
        fig = go.Figure()
        fig.add_scatter(x=recent_del['Label'], y=recent_del['Rider Cost % of Rev'],
                        mode='lines+markers', name='Rider Cost %', line=dict(color=C_COST, width=2))
        # Rolling average line
        fig.add_scatter(x=recent_del['Label'],
                        y=recent_del['Rider Cost % of Rev'].rolling(rolling_window, min_periods=2).mean(),
                        mode='lines', name=f'{rolling_window}-Week Avg',
                        line=dict(color=C_NEUTRAL, dash='dash'))
        fig.update_layout(template='plotly_white', height=350, yaxis_title='%',
                          hovermode='x unified', xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with tab_gp:
        fig = go.Figure()
        fig.add_scatter(x=recent_del['Label'], y=recent_del['GP Margin %'],
                        mode='lines+markers', name='GP Margin %', line=dict(color=C_GP, width=2))
        fig.add_scatter(x=recent_del['Label'],
                        y=recent_del['GP Margin %'].rolling(rolling_window, min_periods=2).mean(),
                        mode='lines', name=f'{rolling_window}-Week Avg',
                        line=dict(color=C_NEUTRAL, dash='dash'))
        fig.update_layout(template='plotly_white', height=350, yaxis_title='%',
                          hovermode='x unified', xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with tab_cpo:
        fig = go.Figure()
        fig.add_scatter(x=recent_del['Label'], y=recent_del['Cost per Order'],
                        mode='lines+markers', name='Cost/Order', line=dict(color=C_COST, width=2))
        fig.add_scatter(x=recent_del['Label'], y=recent_del['Revenue per Order'],
                        mode='lines+markers', name='Revenue/Order', line=dict(color=C_REVENUE, width=2))
        fig.add_scatter(x=recent_del['Label'], y=recent_del['Rider Cost per Order'],
                        mode='lines+markers', name='Rider Cost/Order', line=dict(color='#FF9800', width=2))
        fig.update_layout(template='plotly_white', height=350, yaxis_title='IDR',
                          hovermode='x unified', xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Per-client anomaly scan ───────────────────────────────────────────────
    st.subheader("Per-Client Anomaly Scan")
    st.caption("Scanning each client for significant ratio changes in the latest period.")

    # Get latest 2 weeks
    latest_weeks = del_ratios[['Year', 'Week (by Year)']].drop_duplicates().tail(2)
    if len(latest_weeks) >= 2:
        curr_week = latest_weeks.iloc[-1]
        prev_week = latest_weeks.iloc[-2]

        curr_by_client = compute_ratios_delivery(
            df_del[(df_del['Year'] == curr_week['Year']) & (df_del['Week (by Year)'] == curr_week['Week (by Year)'])],
            ['Client Name']
        )
        prev_by_client = compute_ratios_delivery(
            df_del[(df_del['Year'] == prev_week['Year']) & (df_del['Week (by Year)'] == prev_week['Week (by Year)'])],
            ['Client Name']
        )

        merged = curr_by_client.merge(prev_by_client, on='Client Name', how='outer', suffixes=('', '_prev')).fillna(0)

        client_flags = []
        check_ratios = [
            ('Rider Cost % of Rev', 'Rider Cost %'),
            ('GP Margin %', 'GP Margin %'),
        ]
        for col, label in check_ratios:
            if col in merged.columns and f'{col}_prev' in merged.columns:
                merged[f'{col}_Δ'] = merged[col] - merged[f'{col}_prev']
                flagged = merged[merged[f'{col}_Δ'].abs() > wow_threshold]
                for _, row in flagged.iterrows():
                    client_flags.append({
                        'Client': row['Client Name'],
                        'Metric': label,
                        'Current': f"{row[col]:.1f}%",
                        'Previous': f"{row[f'{col}_prev']:.1f}%",
                        'Change': f"{row[f'{col}_Δ']:+.1f}pp",
                        'Direction': '📈' if row[f'{col}_Δ'] > 0 else '📉',
                        'Revenue': row.get('Revenue', 0),
                    })

        if client_flags:
            cf_df = pd.DataFrame(client_flags).sort_values('Revenue', ascending=False)
            cf_df['Revenue'] = cf_df['Revenue'].apply(fmt_idr)
            st.dataframe(
                cf_df[['Client', 'Metric', 'Previous', 'Current', 'Change', 'Direction', 'Revenue']],
                use_container_width=True, hide_index=True
            )
        else:
            st.success("No per-client anomalies detected.")
else:
    st.info("Delivery data not available.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# MOBILE SELLERS ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
st.header("📱 Mobile Sellers — Anomaly Detection")

try:
    df_mob = require_mobile_data()
except SystemExit:
    df_mob = None

if df_mob is not None and not df_mob.empty:
    mob_ratios = compute_ratios_mobile(df_mob, ['Year', 'Week (by Year)'])
    mob_ratios = mob_ratios.sort_values(['Year', 'Week (by Year)'])
    mob_ratios['Label'] = mob_ratios['Year'].astype(str) + ' W' + mob_ratios['Week (by Year)'].astype(int).astype(str)

    mobile_ratio_cols = {
        'Profit Margin %': 'Profit Margin %',
        'COGS % of Revenue': 'COGS % of Rev',
        'OpCost % of Revenue': 'OpCost % of Rev',
    }

    render_anomaly_section(mob_ratios, 'Label', mobile_ratio_cols,
                           wow_threshold, rolling_window, rolling_threshold, "Mobile Sellers")

    # ── Ratio trend charts ────────────────────────────────────────────────────
    st.subheader("Key Ratio Trends")
    recent_mob = mob_ratios.tail(13)

    tab_pm, tab_cpd, tab_rpd = st.tabs(["Profit Margin %", "Cups per Driver", "Revenue per Driver"])

    with tab_pm:
        fig = go.Figure()
        fig.add_scatter(x=recent_mob['Label'], y=recent_mob['Profit Margin %'],
                        mode='lines+markers', name='Profit Margin %', line=dict(color=C_GP, width=2))
        fig.add_scatter(x=recent_mob['Label'],
                        y=recent_mob['Profit Margin %'].rolling(rolling_window, min_periods=2).mean(),
                        mode='lines', name=f'{rolling_window}-Week Avg',
                        line=dict(color=C_NEUTRAL, dash='dash'))
        fig.update_layout(template='plotly_white', height=350, yaxis_title='%',
                          hovermode='x unified', xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with tab_cpd:
        fig = go.Figure()
        fig.add_scatter(x=recent_mob['Label'], y=recent_mob['Cups per Driver'],
                        mode='lines+markers', name='Cups/Driver', line=dict(color=C_VOLUME, width=2))
        fig.add_scatter(x=recent_mob['Label'],
                        y=recent_mob['Cups per Driver'].rolling(rolling_window, min_periods=2).mean(),
                        mode='lines', name=f'{rolling_window}-Week Avg',
                        line=dict(color=C_NEUTRAL, dash='dash'))
        fig.update_layout(template='plotly_white', height=350, yaxis_title='Cups/Driver',
                          hovermode='x unified', xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    with tab_rpd:
        fig = go.Figure()
        fig.add_scatter(x=recent_mob['Label'], y=recent_mob['Revenue per Driver'],
                        mode='lines+markers', name='Rev/Driver', line=dict(color=C_REVENUE, width=2))
        fig.add_scatter(x=recent_mob['Label'],
                        y=recent_mob['Revenue per Driver'].rolling(rolling_window, min_periods=2).mean(),
                        mode='lines', name=f'{rolling_window}-Week Avg',
                        line=dict(color=C_NEUTRAL, dash='dash'))
        fig.update_layout(template='plotly_white', height=350, yaxis_title='IDR',
                          hovermode='x unified', xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Per-client anomaly scan ───────────────────────────────────────────────
    st.subheader("Per-Client Anomaly Scan")

    latest_weeks = mob_ratios[['Year', 'Week (by Year)']].drop_duplicates().tail(2)
    if len(latest_weeks) >= 2:
        curr_week = latest_weeks.iloc[-1]
        prev_week = latest_weeks.iloc[-2]

        curr_mob_client = compute_ratios_mobile(
            df_mob[(df_mob['Year'] == curr_week['Year']) & (df_mob['Week (by Year)'] == curr_week['Week (by Year)'])],
            ['Client Name']
        )
        prev_mob_client = compute_ratios_mobile(
            df_mob[(df_mob['Year'] == prev_week['Year']) & (df_mob['Week (by Year)'] == prev_week['Week (by Year)'])],
            ['Client Name']
        )

        merged_mob = curr_mob_client.merge(prev_mob_client, on='Client Name', how='outer', suffixes=('', '_prev')).fillna(0)

        mob_client_flags = []
        check_mob_ratios = [
            ('Profit Margin %', 'Profit Margin %'),
            ('COGS % of Rev', 'COGS % of Rev'),
        ]
        for col, label in check_mob_ratios:
            if col in merged_mob.columns and f'{col}_prev' in merged_mob.columns:
                merged_mob[f'{col}_Δ'] = merged_mob[col] - merged_mob[f'{col}_prev']
                flagged = merged_mob[merged_mob[f'{col}_Δ'].abs() > wow_threshold]
                for _, row in flagged.iterrows():
                    mob_client_flags.append({
                        'Client': row['Client Name'],
                        'Metric': label,
                        'Current': f"{row[col]:.1f}%",
                        'Previous': f"{row[f'{col}_prev']:.1f}%",
                        'Change': f"{row[f'{col}_Δ']:+.1f}pp",
                        'Direction': '📈' if row[f'{col}_Δ'] > 0 else '📉',
                        'Revenue': row.get('GrossRevenue', 0),
                    })

        if mob_client_flags:
            mcf_df = pd.DataFrame(mob_client_flags).sort_values('Revenue', ascending=False)
            mcf_df['Revenue'] = mcf_df['Revenue'].apply(fmt_idr)
            st.dataframe(
                mcf_df[['Client', 'Metric', 'Previous', 'Current', 'Change', 'Direction', 'Revenue']],
                use_container_width=True, hide_index=True
            )
        else:
            st.success("No per-client anomalies detected.")
else:
    st.info("Mobile Sellers data not available.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY INTERPRETATION GUIDE
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("📖 How to Interpret Flags"):
    st.markdown("""
**What triggers a flag?**

Each key ratio is monitored two ways:

1. **Week-over-Week (WoW) Change** — if the ratio moves more than the threshold (default: 5pp) compared to the previous week
2. **Deviation from Rolling Average** — if the current value deviates from the N-week rolling average (default: 4 weeks, 5pp threshold)

**Common scenarios:**

| Flag | Likely Issue | Action |
|------|-------------|--------|
| Rider Cost % ↑ sharply | Higher rider compensation or lower revenue | Check if incentives changed or volume dropped |
| GP Margin % ↓ sharply | Cost increase or revenue decrease | Drill into cost components via Deep Dive |
| Delivery Rev % of Total ↓ | Non-delivery revenue growing or delivery revenue shrinking | Check if additional charges or other revenue changed |
| COGS % of Rev ↑ (Mobile) | Higher commission/incentive costs | Check if commission rates changed or promotions ran |
| Cups/Driver ↓ (Mobile) | Driver productivity declining | Check if new drivers are ramping up or demand decreased |

**Is it operational or data input?**

If a flag appears for only 1 client and the change is extreme (>20pp), check raw data first — it's likely a data entry error.
If the flag appears across multiple clients simultaneously, it's more likely an operational or market change.
""")
