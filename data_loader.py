import pandas as pd
import numpy as np
import streamlit as st
import io
from datetime import datetime

MONTH_ORDER = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]

# Core financial columns (present in all file versions)
REVENUE_COLS = [
    'Selling Price (Regular Rate)', 'Additional Charge (KM, KG, Etc)',
    'Return/Delivery Rate', 'Lalamove Bills (Invoicing to Client)',
    'TOTAL DELIVERY REVENUE', 'EV Reduction (3PL & KSJ)', 'EV Manpower',
    'EV Revenue + Battery (Rental Client)', 'Claim/COD/Own Risk',
    'Hub, COD Fee (SBY) & Service Korlap', 'Other Revenue', 'Attribute Fee',
    'Total Revenue',
]

COST_COLS = [
    'Rider Cost', 'Manpower Cost', 'OEM Cost', 'Mid-Mile/ Linehaul Cost',
    'Add. 3PL Cost', 'DM Program', 'Claim Damaged/Loss', 'Outstanding COD',
    'Claim Ownrisk', 'Attribute Cost', 'HUB Cost', 'Other Cost', 'Total Cost',
]

COST_COMPONENTS = {
    'Rider Cost': 'Rider', 'Manpower Cost': 'Manpower', 'OEM Cost': 'OEM',
    'Mid-Mile/ Linehaul Cost': 'Mid-Mile', 'Add. 3PL Cost': '3PL',
    'DM Program': 'DM Program', 'HUB Cost': 'Hub', 'Other Cost': 'Other',
}

# SLA / operational columns (present in W12+ exports)
SLA_COLS = [
    'Deliveries', 'Distance (KM)', '#Ontime', '#Late',
    'Count of Courier Name (unique)', 'Courier Dedicated + Back Up',
    'Deliveries2', 'Distance (KM)2', '#Ontime2', '#Late2',
    'Count of Courier Name (unique)2', 'EV Deduction (from Riders)', 'Apps Using',
]

# Columns that are Excel helper/lookup data — ignore them
# Columns AM/AN/AO (indices 38–40) are internal references; explicitly listed below.
_IGNORE_SUFFIXES = ('.1',)
_IGNORE_PREFIXES = ('Unnamed:',)
_IGNORE_COLS = {
    # Internal reference columns (AM=38, AN=39, AO=40 in the Raw Data Source sheet)
    'Supporting Docs Rev', 'Supporting Docs Cost', 'Remarks',
    # Excel lookup / dropdown helper columns
    'Year.1', 'Client Names', 'Blitz Team.1', 'Client Level.1',
    'Client Location.1', 'Week by Year', 'Month.1', 'Week by Month',
    'Project Name', 'SLA Type.1', 'Project.1', 'Apps Using.1',
}


def _fix_week(w):
    """Fix 2026-style appended week numbers (e.g. 12026 → 1, 102026 → 10)."""
    if pd.isna(w):
        return np.nan
    w = int(w)
    if w > 100:
        s = str(w)
        if len(s) > 4:
            return int(s[:-4])
    return w


def _detect_sheet(file_bytes: bytes) -> str:
    """Find the data sheet: prefer Raw Data Source, then PowerQuery, then first sheet."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    for candidate in ['Raw Data Source', 'PowerQuery']:
        if candidate in xl.sheet_names:
            return candidate
    return xl.sheet_names[0]


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace, drop known helper/duplicate columns."""
    df.columns = [str(c).strip() for c in df.columns]
    drop = [c for c in df.columns if
            c in _IGNORE_COLS or
            any(c.endswith(s) for s in _IGNORE_SUFFIXES) or
            any(c.startswith(s) for s in _IGNORE_PREFIXES)]
    return df.drop(columns=drop, errors='ignore')


# ─────────────────────────────────────────────────────────────────────────────
# SharePoint integration (Microsoft Graph API, app-only auth)
# ─────────────────────────────────────────────────────────────────────────────
# Fetches Excel files directly from SharePoint so the dashboard always shows
# the latest data without manual upload/redeploy. The Azure AD app needs
# `Files.Read.All` Application permission. See SETUP.txt for credential setup.
#
# Reads from st.secrets:
#   AZURE_TENANT_ID     — Directory ID (GUID)
#   AZURE_CLIENT_ID     — Application ID (GUID)
#   AZURE_CLIENT_SECRET — Client secret value
#
# Returns raw bytes; existing load_* functions parse them unchanged.

def is_sharepoint_configured() -> bool:
    """True if Azure AD credentials are present in st.secrets."""
    try:
        for key in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):
            if not st.secrets.get(key):
                return False
        return True
    except (FileNotFoundError, KeyError, AttributeError):
        return False


def _get_graph_access_token() -> str:
    """Get an app-only Microsoft Graph access token via MSAL.

    Tokens last ~60 minutes; MSAL caches them in-process and refreshes
    automatically on expiry, so calling this repeatedly is cheap.
    """
    import msal

    tenant = st.secrets["AZURE_TENANT_ID"]
    client_id = st.secrets["AZURE_CLIENT_ID"]
    client_secret = st.secrets["AZURE_CLIENT_SECRET"]

    authority = f"https://login.microsoftonline.com/{tenant}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        raise RuntimeError(
            "Azure AD auth failed: "
            f"{result.get('error_description') or result.get('error') or result}"
        )
    return result["access_token"]


@st.cache_data(ttl=300, show_spinner="Fetching from SharePoint…")
def fetch_from_sharepoint(file_url: str) -> tuple[bytes, datetime]:
    """Download an Excel file from SharePoint via Microsoft Graph API.

    Args:
        file_url: Full SharePoint URL of the file. Either the browser URL
            ("https://rideblitz.sharepoint.com/sites/.../file.xlsx") or a
            shared link ("https://rideblitz.sharepoint.com/:x:/s/.../...")
            both work — Graph's /shares endpoint accepts either.

    Returns:
        Tuple of (raw .xlsx bytes, fetched_at). The timestamp is captured at
        actual fetch time and survives cache hits, so callers can display
        "last refreshed N minutes ago" without confusing cached reads with
        fresh fetches.

    Cache: 5-minute TTL. Multiple page navigations within that window
    reuse the cached bytes; only the first call after expiry hits Graph.
    Use st.cache_data.clear() to force a fresh fetch.
    """
    import base64
    import requests

    token = _get_graph_access_token()

    # Microsoft Graph's /shares endpoint accepts a "sharing token" derived
    # from any SharePoint URL via base64url encoding.
    encoded = base64.urlsafe_b64encode(file_url.encode()).decode().rstrip("=")
    sharing_token = f"u!{encoded}"

    response = requests.get(
        f"https://graph.microsoft.com/v1.0/shares/{sharing_token}/driveItem/content",
        headers={"Authorization": f"Bearer {token}"},
        allow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    return response.content, datetime.now()


@st.cache_data(show_spinner="Loading data...")
def load_main_data(file_bytes: bytes) -> pd.DataFrame:
    sheet = _detect_sheet(file_bytes)
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=0)
    df = _clean_columns(df)

    # Numeric: core financial columns
    for col in REVENUE_COLS + COST_COLS + ['Delivery Volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Numeric: SLA columns (fill missing with 0)
    for col in SLA_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Fix week numbers
    df['Week (by Year)'] = df['Week (by Year)'].apply(_fix_week)

    # Year as int — drop rows with no valid year, then convert
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
    df = df[df['Year'].notna()].copy()
    df['Year'] = df['Year'].astype(int)

    # Month as ordered category
    df['Month'] = pd.Categorical(df['Month'], categories=MONTH_ORDER, ordered=True)

    # ── Derived financial metrics ─────────────────────────────────────────────
    df['GP'] = df['Total Revenue'] - df['Total Cost']
    df['GP Margin %'] = np.where(
        df['Total Revenue'] != 0, df['GP'] / df['Total Revenue'] * 100, 0
    )
    vol = df['Delivery Volume'].replace(0, np.nan)
    df['SRPO'] = (df['Selling Price (Regular Rate)'] / vol).fillna(0)
    df['RCPO'] = (df['Rider Cost'] / vol).fillna(0)
    df['TCPO'] = (df['Total Cost'] / vol).fillna(0)
    df['TRPO'] = (df['Total Revenue'] / vol).fillna(0)

    # ── Derived SLA metrics (if columns present) ──────────────────────────────
    if '#Ontime' in df.columns and 'Deliveries' in df.columns:
        # Combine dedicated + backup courier data
        df['_total_deliveries'] = df['Deliveries'] + (df['Deliveries2'] if 'Deliveries2' in df.columns else 0)
        df['_total_ontime']     = df['#Ontime']    + (df['#Ontime2']    if '#Ontime2'    in df.columns else 0)
        df['_total_late']       = df['#Late']      + (df['#Late2']      if '#Late2'      in df.columns else 0)
        raw_otp = np.where(
            df['_total_deliveries'] > 0,
            df['_total_ontime'] / df['_total_deliveries'] * 100,
            np.nan
        )
        # Cap at 100% — data entry anomalies can cause #Ontime > Deliveries
        df['OTP Rate %'] = np.minimum(raw_otp, 100.0)
    else:
        df['_total_deliveries'] = df['Delivery Volume'] if 'Delivery Volume' in df.columns else 0
        df['_total_ontime']     = np.nan
        df['_total_late']       = np.nan
        df['OTP Rate %']        = np.nan

    return df


@st.cache_data(show_spinner=False)
def load_ev_data(file_bytes: bytes) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name='Test EV Rental ', header=0)
        df.columns = [str(c).strip() for c in df.columns]
        for col in ['Unit', 'EV Revenue + Battery (Rental Client)', 'Others',
                    'Total Revenue', 'OEM Cost', 'Insurance Cost', 'IOT Cost', 'Total Cost']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df['GP'] = df['Total Revenue'] - df['Total Cost']
        df['Month'] = pd.Categorical(df['Month'], categories=MONTH_ORDER, ordered=True)
        return df
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_action_items(file_bytes: bytes) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name='Action Items',
                           header=1, usecols=range(10))
        df.columns = [str(c).strip() for c in df.columns]
        return df.dropna(how='all')
    except Exception:
        return None


def get_latest_week(df: pd.DataFrame) -> tuple[int, int]:
    """Return (year, week) of the most recent week in the data."""
    max_year = int(df['Year'].max())
    max_week = int(df[df['Year'] == max_year]['Week (by Year)'].max())
    return max_year, max_week


def generate_weekly_insights(df: pd.DataFrame) -> dict | None:
    """Compare the latest week to the prior week and surface key insights."""
    max_year, max_week = get_latest_week(df)
    prev_week = max_week - 1
    year_df = df[df['Year'] == max_year]
    curr = year_df[year_df['Week (by Year)'] == max_week]
    prev = year_df[year_df['Week (by Year)'] == prev_week]

    if curr.empty or prev.empty:
        return None

    def pct(c, p):
        return (c - p) / abs(p) * 100 if p != 0 else None

    summary = {}
    for m in ['Total Revenue', 'Total Cost', 'GP', 'Delivery Volume']:
        cv = (curr['Total Revenue'] - curr['Total Cost']).sum() if m == 'GP' else curr[m].sum()
        pv = (prev['Total Revenue'] - prev['Total Cost']).sum() if m == 'GP' else prev[m].sum()
        summary[m] = {'current': cv, 'previous': pv, 'pct_change': pct(cv, pv)}

    def client_gp(d):
        return (d.groupby('Client Name')[['Total Revenue', 'Total Cost']].sum()
                .eval('GP = `Total Revenue` - `Total Cost`')[['GP']].reset_index())

    curr_gp = client_gp(curr)
    prev_gp = client_gp(prev)
    merged = curr_gp.merge(prev_gp, on='Client Name', how='outer', suffixes=('', '_prev')).fillna(0)
    merged['GP_change'] = merged['GP'] - merged['GP_prev']
    merged['GP_pct'] = merged.apply(lambda r: pct(r['GP'], r['GP_prev']), axis=1)

    summary['week']            = max_week
    summary['year']            = max_year
    summary['date_range']      = curr['Date Range'].dropna().iloc[0] if not curr['Date Range'].dropna().empty else ''
    summary['top_clients']     = curr_gp.nlargest(5, 'GP')
    summary['biggest_improvers'] = merged[merged['GP_pct'].notna() & (merged['GP_pct'] > 0)].nlargest(3, 'GP_pct')
    summary['biggest_decliners'] = merged[merged['GP_pct'].notna() & (merged['GP_pct'] < 0)].nsmallest(3, 'GP_pct')
    summary['negative_gp']     = curr_gp[curr_gp['GP'] < 0]
    return summary


# ── Mobile Sellers data loader ───────────────────────────────────────────────────
MOBILE_REVENUE_COLS = [
    'Total Selling (Clients Revenue)',
    'Total Revenue Sharing % (Weekly)',
    'Total Revenue',
]

MOBILE_COST_COLS = [
    'Total Selling Comission/Sales (Weekly)', 'Total Daily Incentive (Weekly)',
    'Total 26 Days Attendance Bonus (Monthly)', 'Referral',
    'Total Selling 20Mio Bonus (Monthly)', 'Bonus+Beras',
    'Total Income Sales (Weekly)',
    'Manpower (Korlap)', 'Total Cost Molis (Weekly)', 'Cost Claim', 'Storing Cost',
    'Total Operational Cost',
    'Total Potongan Molis (Weekly)',
    'Total Subsidi Molis KSJ (Monthly)', 'Biaya Registrasi',
    'Rider Penalty (Claim, Other Denda to Riders)',
]

MOBILE_OPS_COLS = ['Total Active Riders', 'Total Cups Sold']

MOBILE_PNL_COLS = [
    'Profit', 'Delivery PV', 'Delivery Only PnL',
    'EV Related PV', 'EV Related Only PnL'
]


@st.cache_data(show_spinner="Loading Mobile Sellers data...")
def load_mobile_data(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name='NEW COLUMN TEMPLATE', header=0)
    df.columns = [str(c).strip() for c in df.columns]
    drop = [c for c in df.columns if c.startswith('Unnamed:') or c == 'Supporting Docs']
    df = df.drop(columns=drop, errors='ignore')

    for col in MOBILE_REVENUE_COLS + MOBILE_COST_COLS + MOBILE_OPS_COLS + MOBILE_PNL_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['Week (by Year)'] = df['Week (by Year)'].apply(_fix_week)
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
    df = df[df['Year'].notna()].copy()
    df['Year'] = df['Year'].astype(int)
    df['Month'] = pd.Categorical(df['Month'], categories=MONTH_ORDER, ordered=True)

    # ── De-duplicate date-split rows ─────────────────────────────────────────
    # A single week sometimes spans two months (e.g. W14 = Mar 29–31 + Apr 1–4),
    # producing 2 rows for the same (Year, Week, Client, Location, Project) with
    # the SAME riders counted twice. Collapse: MAX for riders, SUM for everything
    # else. This makes downstream SUM aggregations correct across locations.
    dim_keys = [c for c in ['Year', 'Week (by Year)', 'Client Name',
                            'Client Location', 'Project'] if c in df.columns]
    if dim_keys:
        numeric = df.select_dtypes(include='number').columns.tolist()
        numeric = [c for c in numeric if c not in dim_keys]
        agg = {c: ('max' if c == 'Total Active Riders' else 'sum') for c in numeric}
        # Preserve first non-numeric dim attributes (Blitz Team, Client Level, Month, etc.)
        passthrough = [c for c in df.columns if c not in dim_keys + numeric]
        for c in passthrough:
            agg[c] = 'first'
        df = df.groupby(dim_keys, observed=True, dropna=False).agg(agg).reset_index()
        # Restore Month as ordered categorical (lost during agg)
        if 'Month' in df.columns:
            df['Month'] = pd.Categorical(df['Month'], categories=MONTH_ORDER, ordered=True)

    df['Blitz Revenue']  = df['Total Revenue Sharing % (Weekly)']
    df['Gross Revenue']  = df['Total Revenue']
    df['COGS']           = df['Total Income Sales (Weekly)']
    df['Total Cost (Mobile)'] = df['Total Income Sales (Weekly)'] + df['Total Operational Cost']
    df['Profit Calc']    = df['Total Revenue'] - df['Total Income Sales (Weekly)'] - df['Total Operational Cost']
    df['Profit Margin %'] = np.where(df['Gross Revenue'] != 0, df['Profit Calc'] / df['Gross Revenue'] * 100, 0)
    df['Blitz Margin %']  = np.where(df['Blitz Revenue'] != 0,
                                     (df['Blitz Revenue'] - df['COGS']) / df['Blitz Revenue'] * 100, 0)

    # ── Spec 4: source-first reconciled metrics ──────────────────────────────
    # AF/AG/AH/AI/AJ are loaded as MOBILE_PNL_COLS:
    #   AF Profit              → 'Mobile Profit'
    #   AG Delivery PV         → 'Delivery PV'    (kept as-is)
    #   AH Delivery Only PnL   → 'Delivery PnL %' (×100; source is decimal)
    #   AI EV Related PV       → 'EV PV'
    #   AJ EV Related Only PnL → 'EV PnL %'      (×100)
    # Prefer source values; only fall back to recomputation if a column is
    # missing or entirely zero (likely a malformed export).
    def _source_or_fallback(col: str, fallback):
        if col in df.columns and df[col].abs().sum() > 0:
            return df[col]
        return fallback

    df['Mobile Profit']  = _source_or_fallback('Profit', df['Profit Calc'])
    df['Delivery PnL %'] = _source_or_fallback('Delivery Only PnL',
                                               pd.Series(0.0, index=df.index)) * 100
    df['EV PV']          = _source_or_fallback('EV Related PV',
                                               pd.Series(0.0, index=df.index))
    df['EV PnL %']       = _source_or_fallback('EV Related Only PnL',
                                               pd.Series(0.0, index=df.index)) * 100
    if 'Delivery PV' not in df.columns:
        df['Delivery PV'] = 0.0
    df['Total PV']       = df['Delivery PV'].fillna(0) + df['EV PV'].fillna(0)

    # Implicit denominators back-calculated from per-row (PV / ratio). Stored
    # so KPI strips can compute correctly weighted aggregates as
    # `sum(PV) / sum(base) × 100`. Summing row-level % directly is wrong;
    # mobile_aggregate sums all numerics so percentages can't be trusted post-agg.
    if 'Delivery Only PnL' in df.columns:
        ratio = df['Delivery Only PnL']
        df['_delivery_pv_base'] = np.where(ratio != 0, df['Delivery PV'] / ratio, 0)
    else:
        df['_delivery_pv_base'] = 0.0
    if 'EV Related Only PnL' in df.columns:
        ratio = df['EV Related Only PnL']
        df['_ev_pv_base'] = np.where(ratio != 0, df['EV PV'] / ratio, 0)
    else:
        df['_ev_pv_base'] = 0.0

    return df


def mobile_aggregate(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Aggregate Mobile Sellers data. Riders are SUMMED across locations
    (already de-duplicated for date-split weeks in load_mobile_data).
    All other numerics are summed."""
    if not group_cols:
        numeric = df.select_dtypes(include='number').columns.tolist()
        return pd.DataFrame([{c: df[c].sum() for c in numeric}])
    numeric = df.select_dtypes(include='number').columns.tolist()
    agg_dict = {c: 'sum' for c in numeric if c not in group_cols}
    result = df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()
    # Add per-driver derived metrics
    if 'Total Active Riders' in result.columns and 'Total Cups Sold' in result.columns:
        riders = result['Total Active Riders'].replace(0, np.nan)
        result['Cups per Driver'] = (result['Total Cups Sold'] / riders).fillna(0)
    if 'Total Active Riders' in result.columns and 'Gross Revenue' in result.columns:
        riders = result['Total Active Riders'].replace(0, np.nan)
        result['Revenue per Driver'] = (result['Gross Revenue'] / riders).fillna(0)
    return result
