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


# ── Auto-load helper ─────────────────────────────────────────────────────────
def _auto_load_from_data_folder():
    """Load data files from the data/ folder into session state if not already present."""
    from pathlib import Path
    app_dir = Path(__file__).parent
    # Delivery
    if st.session_state.get('delivery_data') is None and st.session_state.get('data') is None:
        fpath = app_dir / "data" / "delivery_latest.xlsx"
        if fpath.exists():
            try:
                from data_loader import load_main_data, load_ev_data, load_action_items
                with open(fpath, 'rb') as f:
                    fb = f.read()
                df = load_main_data(fb)
                st.session_state['delivery_data'] = df
                st.session_state['data'] = df
                st.session_state['ev_data'] = load_ev_data(fb)
                st.session_state['action_items'] = load_action_items(fb)
            except Exception:
                pass
    # Mobile Sellers
    if st.session_state.get('mobile_data') is None:
        fpath = app_dir / "data" / "mobile_sellers_latest.xlsx"
        if fpath.exists():
            try:
                from data_loader import load_mobile_data
                with open(fpath, 'rb') as f:
                    fb = f.read()
                st.session_state['mobile_data'] = load_mobile_data(fb)
            except Exception:
                pass


# ── Data guard ────────────────────────────────────────────────────────────────
def require_data() -> pd.DataFrame:
    """Return the main Delivery dataframe from session state, or halt the page."""
    _auto_load_from_data_folder()
    df = st.session_state.get('delivery_data')
    if df is None:
        df = st.session_state.get('data')
    if df is None:
        st.warning("⚠️ No Delivery data available. Please ask your admin to publish data via the Updater page.")
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


def period_selector(*, page_key: str, label: str = "View by") -> str:
    """Render the Weekly/Monthly radio with cross-page persistence.

    The selected value lives in `st.session_state['_period_view']`, so
    navigating between pages preserves the user's preferred granularity.
    Each page must still pass a unique `page_key` because Streamlit widgets
    on different pages need distinct widget keys; only the *value* is shared.
    """
    options = ["Weekly", "Monthly"]
    current = st.session_state.get("_period_view", options[0])
    if current not in options:
        current = options[0]
    chosen = st.radio(
        label, options,
        index=options.index(current),
        horizontal=True,
        key=f"_period_radio_{page_key}",
    )
    st.session_state["_period_view"] = chosen
    return chosen


def selected_period_df(df: pd.DataFrame, view_mode: str, page_key: str) -> pd.DataFrame:
    """Return the slice of df for the user's currently-selected period.

    Centralises the latest-period plumbing repeated across delivery / mobile
    pages so KPI strips can simply call:

        curr_df = selected_period_df(df, view_mode, page_key="overview")

    Reads the picked label from `st.session_state[f"_period_pick_{page_key}_{view_mode}"]`
    so per-page period pickers can write to that slot. Falls back to the
    latest available period when nothing has been recorded yet. Returns an
    empty frame if no periods exist.
    """
    periods = get_available_periods(df, view_mode)
    if not periods:
        return df.iloc[0:0]
    sel_lbl = st.session_state.get(f"_period_pick_{page_key}_{view_mode}")
    match = next((t for t in periods if t[2] == sel_lbl), None) or periods[-1]
    yr, p, _ = match
    return filter_period(df, view_mode, yr, p)


def selected_period_info(df: pd.DataFrame, view_mode: str, page_key: str) -> tuple:
    """Companion to `selected_period_df` that returns the picked period's
    `(year, period_value, period_label)` triple instead of the dataframe slice.

    Pages use this to keep subheaders ("Latest Month — X"), PoP comparisons,
    and `prev_period_info` lookups aligned with whatever period the user
    picked. Falls back to the latest period when nothing's been picked.
    """
    periods = get_available_periods(df, view_mode)
    if not periods:
        return None, None, None
    sel_lbl = st.session_state.get(f"_period_pick_{page_key}_{view_mode}")
    return next((t for t in periods if t[2] == sel_lbl), None) or periods[-1]


def period_picker(df: pd.DataFrame, view_mode: str, page_key: str,
                  *, label: str = "Period") -> str | None:
    """Render a period-selection dropdown alongside `period_selector`.

    Lists every available period for the current `view_mode` in reverse-
    chronological order (latest first) so the default selection sits at
    index 0 and the user doesn't have to scroll for the typical case.
    Writes the chosen label to `_period_pick_<page_key>_<view_mode>`,
    which `selected_period_df` / `selected_period_info` already read.

    Returns the chosen label, or None if no periods are available.
    """
    periods = get_available_periods(df, view_mode)
    if not periods:
        return None
    options = [t[2] for t in periods][::-1]   # latest first
    slot = f"_period_pick_{page_key}_{view_mode}"
    current = st.session_state.get(slot, options[0])
    if current not in options:
        current = options[0]
    chosen = st.selectbox(
        label, options,
        index=options.index(current),
        key=f"_period_picker_{page_key}_{view_mode}",
    )
    st.session_state[slot] = chosen
    return chosen


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
    _auto_load_from_data_folder()
    if 'mobile_data' not in st.session_state or st.session_state.mobile_data is None:
        st.warning("⚠️ No Mobile Sellers data available. Please ask your admin to publish data via the Updater page.")
        st.stop()
    return st.session_state.mobile_data.copy()


def build_mobile_trend(df: pd.DataFrame, group_cols: list[str], mode: str) -> pd.DataFrame:
    """Aggregate df by period for Mobile Sellers trend charts.
    Weekly: SUM riders across locations (data already de-duped per week).
    Monthly: average of weekly rider totals for the month."""
    if mode == "Weekly":
        trend = (
            df.groupby(['Year', 'Week (by Year)'] + group_cols, observed=True)
            .agg(Cups=('Total Cups Sold', 'sum'),
                 BlitzRevenue=('Blitz Revenue', 'sum'),
                 GrossRevenue=('Gross Revenue', 'sum'),
                 Profit=('Profit Calc', 'sum'),
                 Riders=('Total Active Riders', 'sum'),
                 COGS=('COGS', 'sum'),
                 OpCost=('Total Operational Cost', 'sum'))
            .reset_index().sort_values(['Year', 'Week (by Year)'])
        )
        trend['Label'] = (trend['Year'].astype(str) + ' W' +
                          trend['Week (by Year)'].astype(int).astype(str))
    else:
        # For monthly: first get weekly rider totals, then average them per month
        weekly_riders = (
            df.groupby(['Year', 'Month', 'Week (by Year)'] + group_cols, observed=True)
            ['Total Active Riders'].sum().reset_index()
        )
        monthly_riders = (
            weekly_riders.groupby(['Year', 'Month'] + group_cols, observed=True)
            ['Total Active Riders'].mean().reset_index()
            .rename(columns={'Total Active Riders': 'Riders'})
        )
        trend = (
            df.groupby(['Year', 'Month'] + group_cols, observed=True)
            .agg(Cups=('Total Cups Sold', 'sum'),
                 BlitzRevenue=('Blitz Revenue', 'sum'),
                 GrossRevenue=('Gross Revenue', 'sum'),
                 Profit=('Profit Calc', 'sum'),
                 COGS=('COGS', 'sum'),
                 OpCost=('Total Operational Cost', 'sum'))
            .reset_index()
        )
        trend = trend.merge(monthly_riders, on=['Year', 'Month'] + group_cols, how='left')
        trend['Riders'] = trend['Riders'].fillna(0)
        trend['Month'] = pd.Categorical(trend['Month'], categories=MONTH_ORDER, ordered=True)
        trend = trend.sort_values(['Year', 'Month'])
        trend['Label'] = trend['Year'].astype(str) + ' ' + trend['Month'].astype(str)
    # Per-driver derived metrics
    trend['Cups per Driver'] = trend.apply(lambda r: r['Cups'] / r['Riders'] if r['Riders'] > 0 else 0, axis=1)
    trend['Revenue per Driver'] = trend.apply(lambda r: r['GrossRevenue'] / r['Riders'] if r['Riders'] > 0 else 0, axis=1)
    return trend


# ─────────────────────────────────────────────────────────────────────────────
# Lane 2A — Global theme & visual helpers
# ─────────────────────────────────────────────────────────────────────────────
# These additions polish the default Streamlit chrome without requiring any
# page changes. CSS targets Streamlit's stable test IDs (data-testid="...")
# so it survives Streamlit version bumps.
#
# Pages already using `st.metric` automatically get the upgraded card look.
# Pages building Plotly figures can opt in to the consistent chart shell by
# wrapping their figure with `apply_chart_theme(fig)` before st.plotly_chart.

_GLOBAL_CSS = """
<style>
/* ─── Sidebar polish ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] {
    margin: 0.4rem 0 0.2rem 0;
}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {
    font-size: 0.85rem;
}

/* Section headings inside the sidebar nav */
[data-testid="stSidebarNav"] h2,
[data-testid="stSidebarNav"] h3 {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    opacity: 0.65;
    margin-top: 0.9rem !important;
    margin-bottom: 0.25rem !important;
    padding-left: 0.5rem;
}

/* ─── Card-style metrics (replaces flat st.metric look) ──────────────────── */
[data-testid="stMetric"] {
    background-color: var(--secondary-background-color, rgba(120,120,120,0.04));
    border: 1px solid rgba(120, 120, 120, 0.16);
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.06);
    transition: box-shadow 0.15s ease, transform 0.15s ease;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06), 0 4px 12px rgba(0, 0, 0, 0.08);
}
[data-testid="stMetricLabel"] {
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
    opacity: 0.7;
}
[data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
    line-height: 1.15;
    margin-top: 4px;
}
[data-testid="stMetricDelta"] {
    display: inline-flex !important;
    align-items: center;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    padding: 2px 8px !important;
    border-radius: 999px !important;
    margin-top: 6px !important;
    background: rgba(120, 120, 120, 0.10);
}

/* ─── Page typography ────────────────────────────────────────────────────── */
.block-container {
    padding-top: 1.4rem !important;
    padding-bottom: 3rem !important;
}
h1 { font-size: 1.55rem !important; letter-spacing: -0.01em; }
h2 { font-size: 1.15rem !important; }
h3 { font-size: 1rem !important; }

/* ─── Dataframes & tables ────────────────────────────────────────────────── */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border: 1px solid rgba(120, 120, 120, 0.16);
    border-radius: 8px;
    overflow: hidden;
}

/* ─── Tabs ───────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button[role="tab"] {
    font-size: 0.85rem;
    font-weight: 500;
}

/* ─── Multiselect / select chips ─────────────────────────────────────────── */
[data-baseweb="tag"] {
    border-radius: 999px !important;
}
</style>
"""


# Dark theme override — applied on top of base styles when toggle = Dark.
_DARK_OVERRIDE_CSS = """
<style>
/* App background + default text */
.stApp { background-color: #0f172a !important; color: #e2e8f0 !important; }

/* Sidebar */
[data-testid="stSidebar"] {
    background-color: #1e293b !important;
}
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
[data-testid="stSidebarNav"] h2,
[data-testid="stSidebarNav"] h3 {
    color: rgba(226, 232, 240, 0.55) !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"] {
    background-color: rgba(21, 112, 239, 0.18) !important;
}

/* Headings + body text */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {
    color: #f1f5f9 !important;
}
.stApp p, .stApp label, .stApp .stMarkdown {
    color: #e2e8f0 !important;
}

/* KPI metric cards */
[data-testid="stMetric"] {
    background-color: #1e293b !important;
    border-color: rgba(148, 163, 184, 0.18) !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4) !important;
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {
    color: rgba(226, 232, 240, 0.65) !important;
}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
    color: #f1f5f9 !important;
}
[data-testid="stMetricDelta"] {
    background: rgba(148, 163, 184, 0.18) !important;
}

/* Dataframes + tables */
[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border-color: rgba(148, 163, 184, 0.18) !important;
}

/* Inputs / selects */
.stTextInput input,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div,
.stDateInput input,
.stNumberInput input {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: rgba(148, 163, 184, 0.18) !important;
}

/* Filter chips (multiselect tags) */
[data-baseweb="tag"] {
    background-color: rgba(21, 112, 239, 0.85) !important;
    color: #ffffff !important;
}

/* Radio + tab labels */
.stRadio label, [data-testid="stTabs"] button[role="tab"] {
    color: #e2e8f0 !important;
}
</style>
"""


def apply_global_styles(theme_mode: str = "Light") -> None:
    """Inject global CSS. Idempotent across reruns.

    Lane 2A: turns the default Streamlit chrome into the redesigned look —
    card-style metrics, tighter typography, polished sidebar sections,
    panel-styled dataframes. Pages don't need to change; CSS targets
    Streamlit's stable test IDs (`data-testid="..."`).

    Lane 2A.1: when `theme_mode="Dark"`, layers a dark override on top.

    Call once from Home.py after `st.set_page_config()`, passing the value
    returned by `render_theme_toggle()`.
    """
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    if theme_mode == "Dark":
        st.markdown(_DARK_OVERRIDE_CSS, unsafe_allow_html=True)


def render_theme_toggle() -> str:
    """Render a Light/Dark radio at the bottom of the sidebar.

    Persists choice in `st.session_state["theme_mode"]`. Returns the
    chosen mode string ("Light" or "Dark") so caller can pass it to
    apply_global_styles.

    Streamlit removed the in-app Settings → Theme picker in v1.40+, so
    this gives users a runtime toggle without touching config.toml.
    """
    if "theme_mode" not in st.session_state:
        st.session_state["theme_mode"] = "Light"

    with st.sidebar:
        st.markdown(
            "<div style='margin-top:1rem; margin-bottom:0.25rem; "
            "font-size:0.7rem; font-weight:600; text-transform:uppercase; "
            "letter-spacing:0.04em; opacity:0.65;'>Appearance</div>",
            unsafe_allow_html=True,
        )
        chosen = st.radio(
            "Theme",
            options=["☀️ Light", "🌙 Dark"],
            index=0 if st.session_state["theme_mode"] == "Light" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="_blitz_theme_radio",
        )

    mode = "Dark" if "Dark" in chosen else "Light"
    st.session_state["theme_mode"] = mode
    return mode


# ─────────────────────────────────────────────────────────────────────────────
# Reusable column_config helpers — fix sortable formatted columns
# ─────────────────────────────────────────────────────────────────────────────
# Pattern: pass numeric values to st.dataframe and use column_config to
# format the display. Streamlit then sorts numerically (correct), instead of
# alphabetically on pre-formatted strings (broken — "5,827" sorts before "641"
# because '5' < '6').

def idr_col(label: str = "Amount"):
    """Column config for an IDR column.

    Renders full digits with locale-aware thousand separators (e.g.
    "136,123,456") instead of the abbreviated "compact" form ("136M").
    Auto-tags the column header with "(Rp)" so the currency unit stays
    visible without losing sort behaviour — pre-formatting strings would
    have broken numeric sort.
    """
    if "(Rp)" not in label:
        label = f"{label} (Rp)"
    return st.column_config.NumberColumn(label, format="localized")


def vol_col(label: str = "Volume"):
    """Column config for a volume/count column. Localized integer, sortable."""
    return st.column_config.NumberColumn(label, format="localized")


def pct_col(label: str = "Margin", signed: bool = False):
    """Column config for a percentage column (value already on a 0–100 scale).

    Set signed=True to always show + or - for delta-style columns.
    """
    fmt = "%+.1f%%" if signed else "%.1f%%"
    return st.column_config.NumberColumn(label, format=fmt)


def dataframe_with_freeze(
    df: pd.DataFrame,
    *,
    key: str,
    column_config: dict | None = None,
    default_freeze: list[str] | None = None,
    freeze_label: str = "🔒 Freeze columns",
    **dataframe_kwargs,
) -> None:
    """Render a small 'Freeze columns' picker + an `st.dataframe` with pinning applied.

    The picker is collapsed inside an expander so narrow tables stay tidy. Pinned
    columns stay visible while the user scrolls horizontally — same effect as
    Excel's freeze pane, on the column axis.

    Parameters mirror `st.dataframe` — pass `column_config`, `width`, `height`,
    `hide_index`, etc. as you normally would. `key` must be unique per table on
    a page (used to namespace the multiselect's session state).

    Streamlit column_config objects are plain dicts internally, so we apply
    `pinned=True` by mutating a clone — preserving the caller's existing
    formatting (NumberColumn format, alignment, etc.).
    """
    # df may be a pandas DataFrame or a Styler (used by Detailed pages for
    # color-coded PoP%). Stylers expose the underlying frame as `.data`.
    data_obj = df.data if hasattr(df, "data") and hasattr(df.data, "columns") else df
    columns = list(data_obj.columns)
    default = [c for c in (default_freeze or []) if c in columns]
    with st.expander(freeze_label, expanded=False):
        frozen = st.multiselect(
            "Pinned columns stay visible while you scroll horizontally.",
            options=columns,
            default=default,
            key=f"freeze_{key}",
            label_visibility="collapsed",
        )
    cfg = {}
    for k, v in (column_config or {}).items():
        cfg[k] = dict(v) if isinstance(v, dict) else v
    for col in frozen:
        if col in cfg:
            cfg[col]["pinned"] = True
        else:
            cfg[col] = st.column_config.Column(col, pinned=True)
    st.dataframe(df, column_config=cfg, **dataframe_kwargs)


def apply_chart_theme(fig: go.Figure) -> go.Figure:
    """Apply consistent Plotly defaults to any figure.

    Transparent background (so it picks up the page theme), unified hover,
    horizontal legend at top-right, no gridlines on x, soft gridlines on y,
    tabular-num font. Pages opt in by wrapping their figure:

        fig = apply_chart_theme(my_fig)
        st.plotly_chart(fig, use_container_width=True)

    Returns the same fig (modified in place) for chaining.
    """
    fig.update_layout(
        font=dict(
            family='-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif',
            size=12,
        ),
        margin=dict(l=10, r=10, t=44, b=10),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(120,120,120,0.15)", zeroline=False)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Cross-company helpers — for Group Overview, Borzo By Client, EV Leasing
# ─────────────────────────────────────────────────────────────────────────────
# `*_optional` returns None when the source is unavailable so the calling page
# can gracefully degrade. Borzo data isn't integrated in this repo yet, so its
# helpers return None / empty.

def get_blitz_delivery_optional() -> pd.DataFrame | None:
    """Return Blitz Delivery data from session state, or None if unavailable."""
    _auto_load_from_data_folder()
    df = st.session_state.get('delivery_data')
    if df is None:
        df = st.session_state.get('data')
    if df is None or df.empty:
        return None
    return df.copy()


def get_blitz_mobile_optional() -> pd.DataFrame | None:
    """Return Blitz Mobile Sellers data from session state, or None if unavailable."""
    _auto_load_from_data_folder()
    df = st.session_state.get('mobile_data')
    if df is None or df.empty:
        return None
    return df.copy()


def get_borzo_monthly_optional() -> pd.DataFrame | None:
    """Borzo monthly data — not yet integrated in this repo."""
    return None


def require_borzo_clients() -> pd.DataFrame:
    """Borzo client-level data — not yet integrated in this repo."""
    return pd.DataFrame()


def blitz_delivery_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Delivery to monthly Group-Overview format.
    Output columns: Year, Month, Stream, Revenue, Cost, GP, Volume.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    monthly = (df.groupby(['Year', 'Month'], observed=True)
               .agg(Revenue=('Total Revenue', 'sum'),
                    Cost=('Total Cost', 'sum'),
                    GP=('GP', 'sum'),
                    Volume=('Delivery Volume', 'sum'))
               .reset_index())
    monthly['Stream'] = 'Blitz — Delivery'
    return monthly[['Year', 'Month', 'Stream', 'Revenue', 'Cost', 'GP', 'Volume']]


def blitz_mobile_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Mobile Sellers to monthly Group-Overview format.
    Output columns: Year, Month, Stream, Revenue, Cost, GP, Volume.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    monthly = (df.groupby(['Year', 'Month'], observed=True)
               .agg(Revenue=('Gross Revenue', 'sum'),
                    GP=('Profit Calc', 'sum'),
                    Volume=('Total Cups Sold', 'sum'))
               .reset_index())
    monthly['Cost'] = monthly['Revenue'] - monthly['GP']
    monthly['Stream'] = 'Blitz — Mobile Sellers'
    return monthly[['Year', 'Month', 'Stream', 'Revenue', 'Cost', 'GP', 'Volume']]


def borzo_monthly_std(df: pd.DataFrame) -> pd.DataFrame:
    """Borzo monthly normalization — pass-through stub (no Borzo data yet)."""
    if df is None or (hasattr(df, 'empty') and df.empty):
        return pd.DataFrame()
    return df.copy()

