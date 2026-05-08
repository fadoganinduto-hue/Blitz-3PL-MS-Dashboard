"""EV Overview — combined view of B2B EV Rentals (delivery) and EV Leasing (mobile).

Two streams shown side-by-side at the top, with detailed drill-downs in tabs.
Pulls EV-related rows from the delivery file (B2B EV Rentals) and the
EV-specific columns (EV Related PV / EV Related Only PnL) from the mobile file.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from utils import (require_data, fmt_idr, fmt_pct, fmt_vol,
                   C_REVENUE, C_COST, C_GP, MONTH_ORDER,
                   get_available_periods, filter_period, prev_period_info,
                   pop_pct, pop_label, period_selector, apply_chart_theme, dataframe_with_freeze)
from data_loader import COST_COMPONENTS

st.set_page_config(page_title="EV Overview | Blitz", page_icon="⚡", layout="wide")
st.title("⚡ EV Overview — B2B Rentals + Mobile Leasing")
st.caption("Two-stream view: B2B EV Rentals (from delivery data) and EV Leasing (from mobile data).")

# ─────────────────────────────────────────────────────────────────────────────
# Data prep
# ─────────────────────────────────────────────────────────────────────────────

df_full = require_data()

# B2B EV Rentals: rows with "EV Rental" in client name OR with EV-related cost/revenue
ev_rental_mask = df_full['Client Name'].str.contains('EV Rental', na=False)


def _col_nonzero(df: pd.DataFrame, col: str) -> pd.Series:
    """Return boolean mask where column values are non-zero, or False if column missing."""
    if col in df.columns:
        return df[col].abs() > 0
    return pd.Series(False, index=df.index)


ev_leasing_mask = (
    _col_nonzero(df_full, 'EV Reduction (3PL & KSJ)')
    | _col_nonzero(df_full, 'EV Manpower')
    | _col_nonzero(df_full, 'EV Revenue + Battery (Rental Client)')
)
b2b_ev_df = df_full[ev_rental_mask | ev_leasing_mask].copy()

# Mobile EV: from session state if available
mobile_df = st.session_state.get('mobile_data')
mobile_has_data = (
    mobile_df is not None
    and not mobile_df.empty
    and 'EV Related PV' in mobile_df.columns
    and 'EV Related Only PnL' in mobile_df.columns
)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar filters
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("🔍 Filters")
    # Build year list from both streams
    years_b2b = set(b2b_ev_df['Year'].dropna().unique().tolist()) if not b2b_ev_df.empty else set()
    years_mob = set(mobile_df['Year'].dropna().unique().tolist()) if mobile_has_data else set()
    all_years = sorted(years_b2b | years_mob)
    sel_years = st.multiselect(
        "Year", all_years,
        default=[max(all_years)] if all_years else [],
        key="ev_year",
    )

# Apply filters
if sel_years:
    b2b_ev_df = b2b_ev_df[b2b_ev_df['Year'].isin(sel_years)]
    if mobile_has_data:
        mobile_df = mobile_df[mobile_df['Year'].isin(sel_years)]

# ─────────────────────────────────────────────────────────────────────────────
# Compute B2B EV totals + Mobile EV totals
# ─────────────────────────────────────────────────────────────────────────────

# B2B EV Rentals numbers
if not b2b_ev_df.empty:
    b2b_rev = b2b_ev_df['Total Revenue'].sum()
    b2b_cost = b2b_ev_df['Total Cost'].sum()
    b2b_gp = b2b_rev - b2b_cost
    b2b_margin = (b2b_gp / b2b_rev * 100) if b2b_rev else 0
    b2b_vol = b2b_ev_df['Delivery Volume'].sum() if 'Delivery Volume' in b2b_ev_df.columns else 0
else:
    b2b_rev = b2b_cost = b2b_gp = b2b_vol = 0
    b2b_margin = 0

# Mobile EV (Leasing) numbers
if mobile_has_data:
    mob_rev = mobile_df['EV Related PV'].sum()
    mob_gp = mobile_df['EV Related Only PnL'].sum()
    mob_cost = mob_rev - mob_gp  # Cost = PV - PnL by definition
    mob_margin = (mob_gp / mob_rev * 100) if mob_rev else 0
else:
    mob_rev = mob_cost = mob_gp = 0
    mob_margin = 0

# Combined totals
total_rev = b2b_rev + mob_rev
total_cost = b2b_cost + mob_cost
total_gp = b2b_gp + mob_gp
total_margin = (total_gp / total_rev * 100) if total_rev else 0

# ─────────────────────────────────────────────────────────────────────────────
# Top-level combined KPIs
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("Combined EV Totals")
year_lbl = ", ".join(str(y) for y in sel_years) if sel_years else "All Years"
st.caption(f"Across both streams · {year_lbl}")

k1, k2, k3, k4 = st.columns(4)
k1.metric("EV Revenue", fmt_idr(total_rev))
k2.metric("EV Cost", fmt_idr(total_cost))
k3.metric("EV Gross Profit", fmt_idr(total_gp))
k4.metric("EV Margin", fmt_pct(total_margin))

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Side-by-side stream summaries
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("Streams Side-by-Side")
col_b2b, col_lease = st.columns(2)

with col_b2b:
    st.markdown("### 🚚 B2B EV Rentals")
    st.caption("Source: delivery file · clients with EV Rental designation or EV-related lines")
    if b2b_ev_df.empty:
        st.info("No B2B EV data for the selected year(s).")
    else:
        kk1, kk2 = st.columns(2)
        kk1.metric("Revenue", fmt_idr(b2b_rev))
        kk2.metric("Cost", fmt_idr(b2b_cost))
        kk3, kk4 = st.columns(2)
        kk3.metric("Gross Profit", fmt_idr(b2b_gp))
        kk4.metric("Margin", fmt_pct(b2b_margin))

        # Mini trend
        b2b_monthly = (
            b2b_ev_df.groupby(['Year', 'Month'], observed=True)
            .agg(Revenue=('Total Revenue', 'sum'),
                 GP=('GP', 'sum') if 'GP' in b2b_ev_df.columns else ('Total Revenue', lambda x: 0))
            .reset_index()
        )
        b2b_monthly['Month'] = pd.Categorical(b2b_monthly['Month'], categories=MONTH_ORDER, ordered=True)
        b2b_monthly = b2b_monthly.sort_values(['Year', 'Month'])
        b2b_monthly['Label'] = (
            b2b_monthly['Year'].astype(str)
            + ' '
            + b2b_monthly['Month'].astype(str)
        )
        fig_b2b = go.Figure()
        fig_b2b.add_bar(x=b2b_monthly['Label'], y=b2b_monthly['Revenue'],
                        name='Revenue', marker_color=C_REVENUE)
        fig_b2b.add_scatter(x=b2b_monthly['Label'], y=b2b_monthly['GP'],
                            name='GP', mode='lines+markers', line=dict(color=C_GP, width=2))
        fig_b2b.update_layout(height=260, xaxis_tickangle=-45, showlegend=True)
        apply_chart_theme(fig_b2b)
        st.plotly_chart(fig_b2b, width="stretch")

with col_lease:
    st.markdown("### 📱 EV Leasing (Mobile)")
    st.caption("Source: mobile file · EV Related PV (revenue) and EV Related Only PnL (GP)")
    if not mobile_has_data:
        st.info("Mobile data not loaded — connect the Mobile Selling SharePoint file to enable this stream.")
    else:
        kk1, kk2 = st.columns(2)
        kk1.metric("Revenue", fmt_idr(mob_rev))
        kk2.metric("Cost", fmt_idr(mob_cost))
        kk3, kk4 = st.columns(2)
        kk3.metric("Gross Profit", fmt_idr(mob_gp))
        kk4.metric("Margin", fmt_pct(mob_margin))

        # Mini trend
        mob_monthly = (
            mobile_df.groupby(['Year', 'Month'], observed=True)
            .agg(Revenue=('EV Related PV', 'sum'), GP=('EV Related Only PnL', 'sum'))
            .reset_index()
        )
        mob_monthly['Month'] = pd.Categorical(mob_monthly['Month'], categories=MONTH_ORDER, ordered=True)
        mob_monthly = mob_monthly.sort_values(['Year', 'Month'])
        mob_monthly['Label'] = (
            mob_monthly['Year'].astype(str)
            + ' '
            + mob_monthly['Month'].astype(str)
        )
        fig_mob = go.Figure()
        fig_mob.add_bar(x=mob_monthly['Label'], y=mob_monthly['Revenue'],
                        name='Revenue', marker_color=C_REVENUE)
        fig_mob.add_scatter(x=mob_monthly['Label'], y=mob_monthly['GP'],
                            name='GP', mode='lines+markers', line=dict(color=C_GP, width=2))
        fig_mob.update_layout(height=260, xaxis_tickangle=-45, showlegend=True)
        apply_chart_theme(fig_mob)
        st.plotly_chart(fig_mob, width="stretch")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Detailed drill-down in tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_b2b, tab_lease = st.tabs(["🚚 B2B EV Rentals — Detail", "📱 EV Leasing (Mobile) — Detail"])

# ── B2B EV Rentals detail ────────────────────────────────────────────────────
with tab_b2b:
    if b2b_ev_df.empty:
        st.info("No B2B EV data for the selected year(s).")
    else:
        # Period selector
        view_mode = period_selector(page_key="b2b")
        pop = pop_label(view_mode)

        periods = get_available_periods(b2b_ev_df, view_mode)
        if periods:
            curr_yr, curr_p, curr_lbl = periods[-1]
            prev_info = prev_period_info(periods, curr_yr, curr_p)
            curr_df = filter_period(b2b_ev_df, view_mode, curr_yr, curr_p)
            prev_df_period = filter_period(b2b_ev_df, view_mode, prev_info[0], prev_info[1]) if prev_info else pd.DataFrame()

            ev_rev_col = 'EV Revenue + Battery (Rental Client)'
            ev_red_col = 'EV Reduction (3PL & KSJ)'
            ev_man_col = 'EV Manpower'

            curr_ev_rev = curr_df[ev_rev_col].sum() if ev_rev_col in curr_df.columns else 0
            curr_ev_red = curr_df[ev_red_col].sum() if ev_red_col in curr_df.columns else 0
            curr_ev_man = curr_df[ev_man_col].sum() if ev_man_col in curr_df.columns else 0
            curr_total_rev = curr_df['Total Revenue'].sum()
            curr_total_cost = curr_df['Total Cost'].sum()
            curr_gp = curr_total_rev - curr_total_cost

            if not prev_df_period.empty:
                prev_gp = prev_df_period['Total Revenue'].sum() - prev_df_period['Total Cost'].sum()
                gp_pop = pop_pct(curr_gp, prev_gp)
            else:
                gp_pop = None

            st.markdown(f"**Latest period — {curr_lbl}**")
            mk1, mk2, mk3, mk4, mk5, mk6 = st.columns(6)
            mk1.metric("EV Revenue Line", fmt_idr(curr_ev_rev))
            mk2.metric("EV Reduction", fmt_idr(curr_ev_red))
            mk3.metric("EV Manpower", fmt_idr(curr_ev_man))
            mk4.metric("Total Revenue", fmt_idr(curr_total_rev))
            mk5.metric("Gross Profit", fmt_idr(curr_gp),
                       f"{gp_pop:+.1f}% {pop}" if gp_pop is not None else None)
            mk6.metric("GP Margin", fmt_pct(curr_gp / curr_total_rev * 100 if curr_total_rev else 0))

        st.markdown("#### Per-Client EV Metrics")
        ev_metrics = [c for c in [ev_rev_col, ev_red_col, ev_man_col] if c in b2b_ev_df.columns]
        client_agg = (
            b2b_ev_df.groupby('Client Name', observed=True)
            .agg(
                **{c: (c, 'sum') for c in ev_metrics},
                Total_Revenue=('Total Revenue', 'sum'),
                Total_Cost=('Total Cost', 'sum'),
                GP=('GP', 'sum') if 'GP' in b2b_ev_df.columns else ('Total Revenue', lambda x: 0),
                Volume=('Delivery Volume', 'sum') if 'Delivery Volume' in b2b_ev_df.columns else ('Total Revenue', lambda x: 0),
            )
            .reset_index()
            .sort_values('GP', ascending=False)
        )
        client_agg['GP Margin %'] = np.where(
            client_agg['Total_Revenue'] != 0,
            client_agg['GP'] / client_agg['Total_Revenue'] * 100, 0
        )
        client_agg['Type'] = client_agg['Client Name'].apply(
            lambda x: 'EV Rental' if 'EV Rental' in str(x) else 'EV Leasing'
        )

        disp = client_agg.copy()
        for c in ev_metrics:
            disp[c] = disp[c].apply(fmt_idr)
        disp['Revenue'] = disp['Total_Revenue'].apply(fmt_idr)
        disp['Cost'] = disp['Total_Cost'].apply(fmt_idr)
        disp['GP_fmt'] = disp['GP'].apply(fmt_idr)
        disp['Volume'] = disp['Volume'].apply(fmt_vol)
        disp['Margin'] = disp['GP Margin %'].apply(fmt_pct)

        show_cols = ['Client Name', 'Type'] + ev_metrics + ['Revenue', 'Cost', 'GP_fmt', 'Volume', 'Margin']
        show_cols = [c for c in show_cols if c in disp.columns]
        dataframe_with_freeze(
            disp[show_cols],
            key="ev_b2b_per_client",
            default_freeze=['Client Name'],
            width="stretch", hide_index=True,
        )

        # Per-client Revenue + GP bars
        fig_cl = px.bar(
            client_agg, x='Client Name', y=['Total_Revenue', 'GP'],
            barmode='group',
            color_discrete_map={'Total_Revenue': C_REVENUE, 'GP': C_GP},
            height=380, title="Revenue & GP by Client",
            labels={'value': 'IDR', 'variable': 'Metric'},
        )
        fig_cl.update_layout(xaxis_tickangle=-20)
        apply_chart_theme(fig_cl)
        st.plotly_chart(fig_cl, width="stretch")

        # Cost structure
        st.markdown("#### Cost Structure by Client")
        cost_cols = [c for c in COST_COMPONENTS.keys() if c in b2b_ev_df.columns]
        cost_agg = b2b_ev_df.groupby('Client Name', observed=True)[cost_cols].sum().reset_index()
        cost_long = cost_agg.melt(id_vars='Client Name', var_name='Component', value_name='Amount')
        cost_long['Label'] = cost_long['Component'].map(COST_COMPONENTS).fillna(cost_long['Component'])
        cost_long = cost_long[cost_long['Amount'] > 0]

        if not cost_long.empty:
            fig_cost = px.bar(
                cost_long, x='Client Name', y='Amount', color='Label',
                barmode='stack', height=360, title="Cost Breakdown",
                labels={'Amount': 'IDR', 'Label': 'Component'},
            )
            fig_cost.update_layout(xaxis_tickangle=-20)
            apply_chart_theme(fig_cost)
            st.plotly_chart(fig_cost, width="stretch")

        # Trend stacked by client
        st.markdown(f"#### {view_mode} Trend by Client")
        if view_mode == "Weekly":
            trend = (
                b2b_ev_df.groupby(['Year', 'Week (by Year)', 'Client Name'], observed=True)
                .agg(
                    Revenue=('Total Revenue', 'sum'),
                    GP=('GP', 'sum') if 'GP' in b2b_ev_df.columns else ('Total Revenue', lambda x: 0),
                )
                .reset_index()
                .sort_values(['Year', 'Week (by Year)'])
            )
            trend['Label'] = (
                trend['Year'].astype(str)
                + ' W'
                + trend['Week (by Year)'].astype(int).astype(str)
            )
        else:
            trend = (
                b2b_ev_df.groupby(['Year', 'Month', 'Client Name'], observed=True)
                .agg(
                    Revenue=('Total Revenue', 'sum'),
                    GP=('GP', 'sum') if 'GP' in b2b_ev_df.columns else ('Total Revenue', lambda x: 0),
                )
                .reset_index()
            )
            trend['Month'] = pd.Categorical(trend['Month'], categories=MONTH_ORDER, ordered=True)
            trend = trend.sort_values(['Year', 'Month'])
            trend['Label'] = (
                trend['Year'].astype(str)
                + ' '
                + trend['Month'].astype(str)
            )

        sub1, sub2 = st.tabs(["Revenue", "GP"])
        with sub1:
            fig_rev = px.bar(trend, x='Label', y='Revenue', color='Client Name',
                             barmode='stack', height=340)
            fig_rev.update_layout(xaxis_tickangle=-45)
            apply_chart_theme(fig_rev)
            st.plotly_chart(fig_rev, width="stretch")
        with sub2:
            fig_gp_t = px.bar(trend, x='Label', y='GP', color='Client Name',
                              barmode='stack', height=340)
            fig_gp_t.update_layout(xaxis_tickangle=-45)
            fig_gp_t.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.5)
            apply_chart_theme(fig_gp_t)
            st.plotly_chart(fig_gp_t, width="stretch")

# ── Mobile EV Leasing detail ─────────────────────────────────────────────────
with tab_lease:
    if not mobile_has_data:
        st.info(
            "Mobile data not loaded — once the Mobile Selling file is connected via SharePoint, "
            "this tab will show per-client EV Leasing breakdowns."
        )
    else:
        # Per-Client breakdown using EV Related PV (revenue) and EV Related Only PnL (GP)
        st.markdown("#### Per-Client EV Leasing Metrics")
        mob_client_agg = (
            mobile_df.groupby('Client Name', observed=True)
            .agg(EV_PV=('EV Related PV', 'sum'),
                 EV_PnL=('EV Related Only PnL', 'sum'))
            .reset_index()
        )
        mob_client_agg['Cost'] = mob_client_agg['EV_PV'] - mob_client_agg['EV_PnL']
        mob_client_agg['Margin %'] = np.where(
            mob_client_agg['EV_PV'] != 0,
            mob_client_agg['EV_PnL'] / mob_client_agg['EV_PV'] * 100, 0
        )
        # Only show clients with meaningful EV activity
        mob_client_agg = mob_client_agg[mob_client_agg['EV_PV'].abs() > 0]
        mob_client_agg = mob_client_agg.sort_values('EV_PnL', ascending=False)

        if mob_client_agg.empty:
            st.info("No mobile EV revenue recorded for the selected year(s).")
        else:
            disp_m = mob_client_agg.copy()
            disp_m['Revenue'] = disp_m['EV_PV'].apply(fmt_idr)
            disp_m['Cost_fmt'] = disp_m['Cost'].apply(fmt_idr)
            disp_m['GP'] = disp_m['EV_PnL'].apply(fmt_idr)
            disp_m['Margin'] = disp_m['Margin %'].apply(fmt_pct)
            st.dataframe(
                disp_m[['Client Name', 'Revenue', 'Cost_fmt', 'GP', 'Margin']]
                .rename(columns={'Cost_fmt': 'Cost'}),
                width="stretch", hide_index=True,
            )

            fig_mc = px.bar(
                mob_client_agg, x='Client Name', y=['EV_PV', 'EV_PnL'],
                barmode='group',
                color_discrete_map={'EV_PV': C_REVENUE, 'EV_PnL': C_GP},
                height=380, title="EV Revenue & GP by Mobile Client",
                labels={'value': 'IDR', 'variable': 'Metric'},
            )
            fig_mc.update_layout(xaxis_tickangle=-20)
            apply_chart_theme(fig_mc)
            st.plotly_chart(fig_mc, width="stretch")

        # Weekly/Monthly trend
        st.markdown("#### Trend")
        view_mode_m = st.radio("View by", ["Weekly", "Monthly"], horizontal=True, key="mob_ev_view")

        if view_mode_m == "Weekly":
            mob_trend = (
                mobile_df.groupby(['Year', 'Week (by Year)'], observed=True)
                .agg(Revenue=('EV Related PV', 'sum'),
                     GP=('EV Related Only PnL', 'sum'))
                .reset_index()
                .sort_values(['Year', 'Week (by Year)'])
            )
            mob_trend['Label'] = (
                mob_trend['Year'].astype(str)
                + ' W'
                + mob_trend['Week (by Year)'].astype(int).astype(str)
            )
        else:
            mob_trend = (
                mobile_df.groupby(['Year', 'Month'], observed=True)
                .agg(Revenue=('EV Related PV', 'sum'),
                     GP=('EV Related Only PnL', 'sum'))
                .reset_index()
            )
            mob_trend['Month'] = pd.Categorical(mob_trend['Month'], categories=MONTH_ORDER, ordered=True)
            mob_trend = mob_trend.sort_values(['Year', 'Month'])
            mob_trend['Label'] = (
                mob_trend['Year'].astype(str)
                + ' '
                + mob_trend['Month'].astype(str)
            )

        fig_t = go.Figure()
        fig_t.add_bar(x=mob_trend['Label'], y=mob_trend['Revenue'],
                      name='Revenue', marker_color=C_REVENUE)
        fig_t.add_scatter(x=mob_trend['Label'], y=mob_trend['GP'],
                          name='GP', mode='lines+markers', line=dict(color=C_GP, width=2))
        fig_t.update_layout(height=380, xaxis_tickangle=-45)
        apply_chart_theme(fig_t)
        st.plotly_chart(fig_t, width="stretch")
