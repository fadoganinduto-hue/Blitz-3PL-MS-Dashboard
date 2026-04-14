import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# ── Colour palette ──────────────────────────────────────────────────────────
C_REVENUE = '#2196F3'
C_COST    = '#F44336'
C_GP      = '#4CAF50'
C_VOLUME  = '#FF9800'
C_NEUTRAL = '#9E9E9E'

MONTH_ORDER = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


# ── Formatting helpers ───────────────────────────────────────────────────────
def fmt_idr(val: float, decimals: int = 1) -> str:
    """Format a rupiah value as B (billion) or M (million)."""
    if pd.isna(val):
        return "Rp -"
    if abs(val) >= 1e9:
        return f"Rp {val/1e9:,.{decimals}f}B"
    if abs(val) >= 1e6:
        return f"Rp {val/1e6:,.{decimals}f}M"
    return f"Rp {val:,.0f}"


def fmt_pct(val: float, decimals: int = 1) -> str:
    if pd.isna(val):
        return "-"
    return f"{val:.{decimals}f}%"


def fmt_vol(val: float) -> str:
    if pd.isna(val):
        return "-"
    return f"{int(val):,}"


# ── KPI card ─────────────────────────────────────────────────────────────────
def kpi_card(col, label: str, value: str, delta: str | None = None, delta_color: str = "normal"):
    with col:
        st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


# ── Data guard ────────────────────────────────────────────────────────────────
def require_data() -> pd.DataFrame:
    """Return the main Delivery dataframe from session state, or halt the page."""
    # Support both legacy key ('data') and new key ('delivery_data')
    df = st.session_state.get('delivery_data') or st.session_state.get('data')
    if df is None:
        st.warning("⚠️ Please upload your data file on the **Home** page first.")
        st.stop()
    return df.copy()


# ── Period helpers ────────────────────────────────────────────────────────────
def get_available_periods(df: pd.DataFrame, mode: str) -> list[tuple]:
    """Return sorted list of (year, period_val, label) tuples.

    For Weekly: period_val is int week number.
    For Monthly: period_val is str month name.
    """
    if mode == "Weekly":
        groups = (
            df.groupby(['Year', 'Week (by Year)'], observed=True)
            .size().reset_index()
            .sort_values(['Year', 'Week (by Year)'])
        )
        return [
            (int(r['Year']), int(r['Week (by Year)']),
             f"{int(r['Year'])} W{int(r['Week (by Year)'])}")
            for _, r in groups.iterrows()
        ]
    else:
        groups = (
            df.groupby(['Year', 'Month'], observed=True)
            .size().reset_index()
        )
        groups['Month'] = pd.Categorical(groups['Month'], categories=MONTH_ORDER, ordered=True)
        groups = groups.sort_values(['Year', 'Month'])
        return [
            (int(r['Year']), str(r['Month']), f"{int(r['Year'])} {r['Month']}")
            for _, r in groups.iterrows()
        ]


def filter_period(df: pd.DataFrame, mode: str, year: int, period_val) -> pd.DataFrame:
    """Filter df to a specific period."""
    if mode == "Weekly":
        return df[(df['Year'] == year) & (df['Week (by Year)'] == int(period_val))]
    else:
        return df[(df['Year'] == year) & (df['Month'] == str(period_val))]


def prev_period_info(periods: list[tuple], year: int, period_val) -> tuple | None:
    """Given a sorted periods list, return the period immediately before (year, period_val)."""
    keys = [(p[0], p[1]) for p in periods]
    try:
        idx = keys.index((year, period_val))
        if idx > 0:
            return periods[idx - 1]
    except ValueError:
        pass
    return None


def pop_pct(curr_val: float, prev_val: float) -> float | None:
    """Period-over-period % change. Returns None if no meaningful prior value."""
    if pd.isna(prev_val) or prev_val == 0:
        return None
    return (curr_val - prev_val) / abs(prev_val) * 100


def pop_label(mode: str) -> str:
    """Short period-over-period abbreviation: WoW or MoM."""
    return "WoW" if mode == "Weekly" else "MoM"


def build_trend(df: pd.DataFrame, group_cols: list[str], mode: str) -> pd.DataFrame:
    """Aggregate df by period for trend charts. Returns df with a 'Label' column."""
    if mode == "Weekly":
        trend = (
            df.groupby(['Year', 'Week (by Year)'] + group_cols, observed=True)
            .agg(Revenue=('Total Revenue', 'sum'), Cost=('Total Cost', 'sum'),
                 GP=('GP', 'sum'), Volume=('Delivery Volume', 'sum'))
            .reset_index().sort_values(['Year', 'Week (by Year)'])
        )
        trend['Label'] = (trend['Year'].astype(str) + ' W' +
                          trend['Week (by Year)'].astype(int).astype(str))
    else:
        trend = (
            df.groupby(['Year', 'Month'] + group_cols, observed=True)
            .agg(Revenue=('Total Revenue', 'sum'), Cost=('Total Cost', 'sum'),
                 GP=('GP', 'sum'), Volume=('Delivery Volume', 'sum'))
            .reset_index()
        )
        trend['Month'] = pd.Categorical(trend['Month'], categories=MONTH_ORDER, ordered=True)
        trend = trend.sort_values(['Year', 'Month'])
        trend['Label'] = trend['Year'].astype(str) + ' ' + trend['Month'].astype(str)
    return trend


# ── Sidebar filters ───────────────────────────────────────────────────────────
def sidebar_filters(df: pd.DataFrame, page_key: str = "") -> pd.DataFrame:
    """Render sidebar filters and return the filtered dataframe."""
    with st.sidebar:
        st.header("🔍 Filters")

        years = sorted(df['Year'].dropna().unique().tolist())
        sel_years = st.multiselect(
            "Year", years, default=[max(years)], key=f"year_{page_key}"
        )

        teams = sorted(df['Blitz Team'].dropna().unique().tolist())
        sel_teams = st.multiselect(
            "Blitz Team", teams, default=teams, key=f"team_{page_key}"
        )

        if sel_years:
            month_df = df[df['Year'].isin(sel_years)]
        else:
            month_df = df
        months_avail = [m for m in MONTH_ORDER if m in month_df['Month'].cat.categories
                        and m in month_df['Month'].values]
        sel_months = st.multiselect(
            "Month", months_avail, default=months_avail, key=f"month_{page_key}"
        )

        client_lvls = sorted(df['Client Level'].dropna().unique().tolist())
        sel_levels = st.multiselect(
            "Client Level", client_lvls, default=client_lvls, key=f"level_{page_key}"
        )

        sla_types = sorted(df['SLA Type'].dropna().unique().tolist())
        sel_sla = st.multiselect(
            "SLA Type", sla_types, default=sla_types, key=f"sla_{page_key}"
        )

        st.divider()
        st.caption("Leave blank to include all.")

    # Apply filters
    mask = pd.Series(True, index=df.index)
    if sel_years:
        mask &= df['Year'].isin(sel_years)
    if sel_teams:
        mask &= df['Blitz Team'].isin(sel_teams)
    if sel_months:
        mask &= df['Month'].isin(sel_months)
    if sel_levels:
        mask &= df['Client Level'].isin(sel_levels)
    if sel_sla:
        mask &= df['SLA Type'].isin(sel_sla)

    return df[mask].copy()


# ── Chart helpers ─────────────────────────────────────────────────────────────
def revenue_cost_gp_bar(df_agg: pd.DataFrame, x_col: str, title: str = "") -> go.Figure:
    """Grouped bar: Revenue, Cost, GP for a given x dimension."""
    fig = go.Figure()
    fig.add_bar(x=df_agg[x_col], y=df_agg['Total Revenue'], name='Revenue',
                marker_color=C_REVENUE)
    fig.add_bar(x=df_agg[x_col], y=df_agg['Total Cost'], name='Cost',
                marker_color=C_COST)
    fig.add_bar(x=df_agg[x_col], y=df_agg['GP'], name='GP',
                marker_color=C_GP)
    fig.update_layout(
        title=title, barmode='group', hovermode='x unified',
        legend=dict(orientation='h', y=1.05),
        yaxis_title='IDR', template='plotly_white', height=380
    )
    return fig


def trend_line(df_agg: pd.DataFrame, x_col: str, y_cols: list[str],
               colors: list[str], title: str = "") -> go.Figure:
    fig = go.Figure()
    for col, color in zip(y_cols, colors):
        fig.add_scatter(x=df_agg[x_col], y=df_agg[col], mode='lines+markers',
                        name=col, line=dict(color=color, width=2))
    fig.update_layout(
        title=title, hovermode='x unified',
        legend=dict(orientation='h', y=1.05),
        yaxis_title='IDR', template='plotly_white', height=360
    )
    return fig


def cost_waterfall(rev: float, costs: dict, title: str = "Cost Waterfall") -> go.Figure:
    labels = ['Revenue'] + list(costs.keys()) + ['GP']
    values = [rev] + [-v for v in costs.values()]
    gp = rev - sum(costs.values())
    values.append(gp)
    colors = [C_REVENUE] + [C_COST] * len(costs) + [C_GP if gp >= 0 else C_COST]

    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors))
    fig.update_layout(
        title=title, template='plotly_white', height=380,
        yaxis_title='IDR'
    )
    return fig


def delta_badge(pct: float | None) -> str:
    """Return a coloured arrow + pct string for display."""
    if pct is None:
        return "—"
    arrow = "▲" if pct >= 0 else "▼"
    color = "green" if pct >= 0 else "red"
    return f":{color}[{arrow} {abs(pct):.1f}%]"


# ── Mobile Sellers helpers ──────────────────────────────────────────────────────
def require_mobile_data() -> pd.DataFrame:
    if 'mobile_data' not in st.session_state or st.session_state.mobile_data is None:
        st.warning("⚠️ Please upload your Mobile Sellers data file on the **Home** page first.")
        st.stop()
    return st.session_state.mobile_data.copy()


def build_mobile_trend(df: pd.DataFrame, group_cols: list[str], mode: str) -> pd.DataFrame:
    """Aggregate df by period for Mobile Sellers trend charts. Uses MAX for riders, SUM for others."""
    if mode == "Weekly":
        trend = (
            df.groupby(['Year', 'Week (by Year)'] + group_cols, observed=True)
            .agg(Cups=('Total Cups Sold', 'sum'),
                 BlitzRevenue=('Blitz Revenue', 'sum'),
                 GrossRevenue=('Gross Revenue', 'sum'),
                 Profit=('Profit Calc', 'sum'),
                 Riders=('Total Active Riders', 'max'),
                 COGS=('COGS', 'sum'),
                 OpCost=('Total Operational Cost', 'sum'))
            .reset_index().sort_values(['Year', 'Week (by Year)'])
        )
        trend['Label'] = (trend['Year'].astype(str) + ' W' +
                          trend['Week (by Year)'].astype(int).astype(str))
    else:
        trend = (
            df.groupby(['Year', 'Month'] + group_cols, observed=True)
            .agg(Cups=('Total Cups Sold', 'sum'),
                 BlitzRevenue=('Blitz Revenue', 'sum'),
                 GrossRevenue=('Gross Revenue', 'sum'),
                 Profit=('Profit Calc', 'sum'),
                 Riders=('Total Active Riders', 'max'),
                 COGS=('COGS', 'sum'),
                 OpCost=('Total Operational Cost', 'sum'))
            .reset_index()
        )
        trend['Month'] = pd.Categorical(trend['Month'], categories=MONTH_ORDER, ordered=True)
        trend = trend.sort_values(['Year', 'Month'])
        trend['Label'] = trend['Year'].astype(str) + ' ' + trend['Month'].astype(str)
    return trend
