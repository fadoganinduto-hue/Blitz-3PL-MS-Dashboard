"""EV Leasing — P&L isolated from Blitz Delivery (Test EV Rental sheet)
and Blitz Mobile Sellers (EV-related columns).
Two views: Summary (combined) and Detailed (per source / unit / month).
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils import (
    fmt_idr, fmt_pct, fmt_vol, MONTH_ORDER,
    C_REVENUE, C_COST, C_GP, C_VOLUME,
    get_blitz_mobile_optional,
)

def _get_ev_data():
    """Get EV data from session state (loaded from Test EV Rental sheet)."""
    from utils import _auto_load_from_data_folder  # noqa: may not exist in older deploy
    try:
        _auto_load_from_data_folder()
    except Exception:
        pass
    df = st.session_state.get('ev_data')
    if df is None or (hasattr(df, 'empty') and df.empty):
        return None
    return df.copy()

st.set_page_config(page_title="EV Leasing | Blitz", page_icon="⚡", layout="wide")
st.title("⚡ EV Leasing")
st.caption(
    "Isolated EV Leasing P&L. "
    "**Delivery side** = `Test EV Rental` sheet (unit-level). "
    "**Mobile side** = EV-related columns from Mobile Sellers. "
    "Revenue / Cost / GP normalized across both sources."
)

# ── Load sources ──────────────────────────────────────────────────────────────
ev_del   = _get_ev_data()             # from Test EV Rental sheet
mob_raw  = get_blitz_mobile_optional() # from Mobile Sellers

if ev_del is None and mob_raw is None:
    st.warning("⚠️ No EV data loaded. Ask your admin to publish data via the Updater page.")
    st.stop()

# ── Prep Delivery EV ──────────────────────────────────────────────────────────
def prep_delivery_ev(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise the Test EV Rental sheet into [Year, Month, MonthNum, Revenue, Cost, GP, Unit]."""
    df = df.copy()
    # Ensure Year exists
    if 'Year' not in df.columns:
        df['Year'] = pd.NA
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
    df = df[df['Year'].notna()].copy()
    df['Year'] = df['Year'].astype(int)

    # Revenue: prefer dedicated EV rev column, fall back to Total Revenue
    rev_col = 'EV Revenue + Battery (Rental Client)' if 'EV Revenue + Battery (Rental Client)' in df.columns else 'Total Revenue'
    df['Revenue'] = pd.to_numeric(df.get(rev_col, 0), errors='coerce').fillna(0)
    # Add "Others" into Revenue if present
    if 'Others' in df.columns:
        df['Revenue'] = df['Revenue'] + pd.to_numeric(df['Others'], errors='coerce').fillna(0)

    df['Cost']    = pd.to_numeric(df.get('Total Cost',    0), errors='coerce').fillna(0)
    df['GP']      = pd.to_numeric(df.get('GP',            0), errors='coerce').fillna(0)
    if df['GP'].sum() == 0:
        df['GP'] = df['Revenue'] - df['Cost']

    df['OEM Cost']       = pd.to_numeric(df.get('OEM Cost',       0), errors='coerce').fillna(0)
    df['Insurance Cost'] = pd.to_numeric(df.get('Insurance Cost', 0), errors='coerce').fillna(0)
    df['IOT Cost']       = pd.to_numeric(df.get('IOT Cost',       0), errors='coerce').fillna(0)
    df['Unit']           = df.get('Unit', pd.Series(['Unknown'] * len(df), index=df.index)).fillna('Unknown')

    df['Month'] = pd.Categorical(df['Month'], categories=MONTH_ORDER, ordered=True)
    df['MonthNum'] = df['Month'].cat.codes + 1
    df['Source'] = 'Delivery EV'
    return df[['Year', 'Month', 'MonthNum', 'Revenue', 'Cost', 'GP',
               'OEM Cost', 'Insurance Cost', 'IOT Cost', 'Unit', 'Source']]


def prep_mobile_ev(df: pd.DataFrame) -> pd.DataFrame:
    """Extract EV-related columns from Mobile Sellers into [Year, Month, MonthNum, Revenue, Cost, GP]."""
    df = df.copy()
    ev_pv  = 'EV Related PV'
    ev_pnl = 'EV Related Only PnL'
    if ev_pv not in df.columns and ev_pnl not in df.columns:
        return pd.DataFrame()

    df['Revenue'] = pd.to_numeric(df.get(ev_pv,  0), errors='coerce').fillna(0)
    df['GP']      = pd.to_numeric(df.get(ev_pnl, 0), errors='coerce').fillna(0)
    df['Cost']    = df['Revenue'] - df['GP']

    # Filter to rows with any EV activity
    df = df[(df['Revenue'] != 0) | (df['GP'] != 0)].copy()
    if df.empty:
        return pd.DataFrame()

    df['Month'] = pd.Categorical(df['Month'], categories=MONTH_ORDER, ordered=True)
    df['MonthNum'] = df['Month'].cat.codes + 1
    df['Unit']   = 'Mobile EV'
    df['Source'] = 'Mobile EV'
    df['OEM Cost'] = 0.0; df['Insurance Cost'] = 0.0; df['IOT Cost'] = 0.0
    return df[['Year', 'Month', 'MonthNum', 'Revenue', 'Cost', 'GP',
               'OEM Cost', 'Insurance Cost', 'IOT Cost', 'Unit', 'Source']]


del_df  = prep_delivery_ev(ev_del)    if ev_del   is not None else pd.DataFrame()
mob_df  = prep_mobile_ev(mob_raw)     if mob_raw  is not None else pd.DataFrame()

has_del = not del_df.empty
has_mob = not mob_df.empty

all_ev = pd.concat([del_df, mob_df], ignore_index=True)
if all_ev.empty:
    st.warning("⚠️ EV data loaded but no rows found. Check that the source sheets contain data.")
    st.stop()

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    years = sorted(all_ev['Year'].dropna().astype(int).unique().tolist())
    sel_years = st.multiselect("Year", years, default=years, key="ev_year")

    sources_avail = sorted(all_ev['Source'].unique().tolist())
    sel_sources = st.multiselect("Source", sources_avail, default=sources_avail, key="ev_source")

fdf = all_ev.copy()
if sel_years:
    fdf = fdf[fdf['Year'].isin(sel_years)]
if sel_sources:
    fdf = fdf[fdf['Source'].isin(sel_sources)]

if fdf.empty:
    st.info("No data for selected filters.")
    st.stop()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_sum, tab_det = st.tabs(["📊 Summary", "🔬 Detailed"])

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_sum:
    # KPI row
    tot_rev  = fdf['Revenue'].sum()
    tot_cost = fdf['Cost'].sum()
    tot_gp   = fdf['GP'].sum()
    margin   = tot_gp / tot_rev * 100 if tot_rev else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("EV Revenue",   fmt_idr(tot_rev))
    k2.metric("EV Cost",      fmt_idr(tot_cost))
    k3.metric("EV GP",        fmt_idr(tot_gp))
    k4.metric("GP Margin %",  fmt_pct(margin))

    st.divider()

    # ── Monthly Revenue + GP trend ────────────────────────────────────────────
    st.subheader("📈 Monthly Revenue, Cost & GP")
    monthly = (fdf.groupby(['Year', 'Month', 'MonthNum', 'Source'], observed=True)
               .agg(Revenue=('Revenue', 'sum'), Cost=('Cost', 'sum'), GP=('GP', 'sum'))
               .reset_index())
    monthly['Month'] = pd.Categorical(monthly['Month'], categories=MONTH_ORDER, ordered=True)
    monthly = monthly.sort_values(['Year', 'MonthNum'])
    monthly['Period'] = monthly['Year'].astype(int).astype(str) + '-' + \
                        monthly['MonthNum'].astype(int).astype(str).str.zfill(2)

    # Combined (all sources) monthly
    monthly_tot = (fdf.groupby(['Year', 'MonthNum'], observed=True)
                   .agg(Revenue=('Revenue', 'sum'), Cost=('Cost', 'sum'), GP=('GP', 'sum'))
                   .reset_index().sort_values(['Year', 'MonthNum']))
    monthly_tot['Period'] = monthly_tot['Year'].astype(int).astype(str) + '-' + \
                            monthly_tot['MonthNum'].astype(int).astype(str).str.zfill(2)
    monthly_tot['GP Margin %'] = monthly_tot.apply(
        lambda r: r['GP'] / r['Revenue'] * 100 if r['Revenue'] else 0, axis=1)

    fig_main = go.Figure()
    fig_main.add_bar(x=monthly_tot['Period'], y=monthly_tot['Revenue'],
                     name='Revenue', marker_color=C_REVENUE)
    fig_main.add_bar(x=monthly_tot['Period'], y=monthly_tot['Cost'],
                     name='Cost', marker_color=C_COST)
    fig_main.add_bar(x=monthly_tot['Period'], y=monthly_tot['GP'],
                     name='GP', marker_color=C_GP)
    fig_main.update_layout(
        template='plotly_white', height=400, barmode='group',
        yaxis_title='IDR', hovermode='x unified',
        legend=dict(orientation='h', y=1.08)
    )
    st.plotly_chart(fig_main, use_container_width=True)

    # ── Source contribution (if both) ─────────────────────────────────────────
    if has_del and has_mob:
        st.subheader("🥧 Source Contribution")
        src_agg = (fdf.groupby('Source', observed=True)
                   .agg(Revenue=('Revenue', 'sum'), GP=('GP', 'sum'))
                   .reset_index())
        c1, c2 = st.columns(2)
        with c1:
            fig_p1 = px.pie(src_agg, names='Source', values='Revenue', hole=0.5,
                            title='Revenue Share by Source',
                            color_discrete_map={'Delivery EV': C_REVENUE, 'Mobile EV': '#F57C00'})
            fig_p1.update_layout(template='plotly_white', height=300,
                                 legend=dict(orientation='h', y=-0.1))
            st.plotly_chart(fig_p1, use_container_width=True)
        with c2:
            fig_p2 = px.pie(src_agg, names='Source', values='GP', hole=0.5,
                            title='GP Share by Source',
                            color_discrete_map={'Delivery EV': C_GP, 'Mobile EV': '#F57C00'})
            fig_p2.update_layout(template='plotly_white', height=300,
                                 legend=dict(orientation='h', y=-0.1))
            st.plotly_chart(fig_p2, use_container_width=True)

    # ── GP Margin trend ───────────────────────────────────────────────────────
    st.subheader("📈 GP Margin % — Monthly")
    fig_mg = go.Figure()
    fig_mg.add_scatter(x=monthly_tot['Period'], y=monthly_tot['GP Margin %'],
                       mode='lines+markers', name='GP Margin %',
                       line=dict(color=C_GP, width=2))
    fig_mg.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.4)
    fig_mg.update_layout(template='plotly_white', height=320, yaxis_title='%',
                         hovermode='x unified')
    st.plotly_chart(fig_mg, use_container_width=True)

    # ── Monthly summary table ─────────────────────────────────────────────────
    st.subheader("📋 Monthly Summary")
    tbl = monthly_tot.copy()
    for c in ['Revenue', 'Cost', 'GP']:
        tbl[c] = tbl[c].apply(fmt_idr)
    tbl['GP Margin %'] = tbl['GP Margin %'].apply(fmt_pct)
    tbl = tbl.drop(columns=['MonthNum'])
    st.dataframe(tbl.sort_values(['Year', 'Period'], ascending=[False, False]),
                 use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# DETAILED TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_det:

    # ── Delivery EV section ───────────────────────────────────────────────────
    if has_del:
        st.subheader("🚚 Delivery EV — Unit-Level Detail")

        del_fdf = fdf[fdf['Source'] == 'Delivery EV'].copy()

        if del_fdf.empty:
            st.info("No Delivery EV rows for the selected filters.")
        else:
            # Per-unit aggregation
            unit_agg = (del_fdf.groupby('Unit', observed=True)
                        .agg(Revenue=('Revenue', 'sum'),
                             Cost=('Cost', 'sum'),
                             GP=('GP', 'sum'),
                             OEM=('OEM Cost', 'sum'),
                             Insurance=('Insurance Cost', 'sum'),
                             IOT=('IOT Cost', 'sum'))
                        .reset_index().sort_values('Revenue', ascending=False))
            unit_agg['GP Margin %'] = unit_agg.apply(
                lambda r: r['GP'] / r['Revenue'] * 100 if r['Revenue'] else 0, axis=1)

            # Bar chart: Revenue vs Cost vs GP per unit
            fig_unit = go.Figure()
            fig_unit.add_bar(x=unit_agg['Unit'], y=unit_agg['Revenue'],
                             name='Revenue', marker_color=C_REVENUE)
            fig_unit.add_bar(x=unit_agg['Unit'], y=unit_agg['Cost'],
                             name='Cost', marker_color=C_COST)
            fig_unit.add_bar(x=unit_agg['Unit'], y=unit_agg['GP'],
                             name='GP', marker_color=C_GP)
            fig_unit.update_layout(
                template='plotly_white', height=380, barmode='group',
                xaxis_title='Unit', yaxis_title='IDR', hovermode='x unified',
                legend=dict(orientation='h', y=1.08)
            )
            st.plotly_chart(fig_unit, use_container_width=True)

            # Cost breakdown per unit
            cost_cols_present = [c for c in ['OEM', 'Insurance', 'IOT'] if unit_agg[c].sum() > 0]
            if cost_cols_present:
                st.markdown("**Cost Breakdown by Unit**")
                cost_long = unit_agg[['Unit'] + cost_cols_present].melt(
                    id_vars='Unit', var_name='Component', value_name='Amount')
                cost_long = cost_long[cost_long['Amount'] > 0]
                fig_cost = px.bar(cost_long, x='Unit', y='Amount', color='Component',
                                  barmode='stack', template='plotly_white', height=320,
                                  color_discrete_map={'OEM': '#EF5350', 'Insurance': '#FF7043',
                                                      'IOT': '#FFA726'},
                                  labels={'Amount': 'IDR'})
                fig_cost.update_layout(hovermode='x unified', legend=dict(orientation='h', y=1.08))
                st.plotly_chart(fig_cost, use_container_width=True)

            # Monthly trend per unit
            st.markdown("**Monthly Revenue by Unit**")
            del_monthly = (del_fdf.groupby(['Year', 'Month', 'MonthNum', 'Unit'], observed=True)
                           .agg(Revenue=('Revenue', 'sum'), GP=('GP', 'sum'))
                           .reset_index().sort_values(['Year', 'MonthNum']))
            del_monthly['Period'] = del_monthly['Year'].astype(int).astype(str) + '-' + \
                                    del_monthly['MonthNum'].astype(int).astype(str).str.zfill(2)

            fig_um = px.bar(del_monthly, x='Period', y='Revenue', color='Unit',
                            barmode='group', template='plotly_white', height=360,
                            labels={'Revenue': 'IDR'})
            fig_um.update_layout(hovermode='x unified', xaxis_tickangle=-45,
                                 legend=dict(orientation='h', y=1.08))
            st.plotly_chart(fig_um, use_container_width=True)

            # Unit detail table
            disp = unit_agg.copy()
            for c in ['Revenue', 'Cost', 'GP', 'OEM', 'Insurance', 'IOT']:
                disp[c] = disp[c].apply(fmt_idr)
            disp['GP Margin %'] = disp['GP Margin %'].apply(fmt_pct)
            st.dataframe(disp.rename(columns={'OEM': 'OEM Cost',
                                              'Insurance': 'Insurance Cost',
                                              'IOT': 'IOT Cost'}),
                         use_container_width=True, hide_index=True)

    # ── Mobile EV section ─────────────────────────────────────────────────────
    if has_mob:
        st.divider()
        st.subheader("📱 Mobile EV — Monthly P&L")

        mob_fdf = fdf[fdf['Source'] == 'Mobile EV'].copy()

        if mob_fdf.empty:
            st.info("No Mobile EV rows for the selected filters.")
        else:
            mob_monthly = (mob_fdf.groupby(['Year', 'Month', 'MonthNum'], observed=True)
                           .agg(Revenue=('Revenue', 'sum'),
                                Cost=('Cost', 'sum'),
                                GP=('GP', 'sum'))
                           .reset_index().sort_values(['Year', 'MonthNum']))
            mob_monthly['Period'] = mob_monthly['Year'].astype(int).astype(str) + '-' + \
                                    mob_monthly['MonthNum'].astype(int).astype(str).str.zfill(2)
            mob_monthly['GP Margin %'] = mob_monthly.apply(
                lambda r: r['GP'] / r['Revenue'] * 100 if r['Revenue'] else 0, axis=1)

            fig_mob = go.Figure()
            fig_mob.add_bar(x=mob_monthly['Period'], y=mob_monthly['Revenue'],
                            name='EV Revenue (PV)', marker_color=C_REVENUE)
            fig_mob.add_bar(x=mob_monthly['Period'], y=mob_monthly['Cost'],
                            name='EV Cost', marker_color=C_COST)
            fig_mob.add_bar(x=mob_monthly['Period'], y=mob_monthly['GP'],
                            name='EV PnL', marker_color=C_GP)
            fig_mob.update_layout(
                template='plotly_white', height=360, barmode='group',
                yaxis_title='IDR', hovermode='x unified',
                legend=dict(orientation='h', y=1.08)
            )
            fig_mob.add_hline(y=0, line_dash='dash', line_color='red', opacity=0.4)
            st.plotly_chart(fig_mob, use_container_width=True)

            # Mobile EV table
            mdisp = mob_monthly.copy()
            for c in ['Revenue', 'Cost', 'GP']:
                mdisp[c] = mdisp[c].apply(fmt_idr)
            mdisp['GP Margin %'] = mdisp['GP Margin %'].apply(fmt_pct)
            mdisp = mdisp.drop(columns=['MonthNum'])
            st.dataframe(mdisp.rename(columns={'Revenue': 'EV Revenue (PV)',
                                               'GP': 'EV PnL'}),
                         use_container_width=True, hide_index=True)
