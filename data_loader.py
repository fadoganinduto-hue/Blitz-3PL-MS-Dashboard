import pandas as pd
import numpy as np
import streamlit as st
import io

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
        df['_total_deliveries'] = df['Deliveries'] + df.get('Deliveries2', pd.Series(0, index=df.index))
        df['_total_ontime']     = df['#Ontime']    + df.get('#Ontime2',    pd.Series(0, index=df.index))
        df['_total_late']       = df['#Late']      + df.get('#Late2',      pd.Series(0, index=df.index))
        raw_otp = np.where(
            df['_total_deliveries'] > 0,
            df['_total_ontime'] / df['_total_deliveries'] * 100,
            np.nan
        )
        # Cap at 100% — data entry anomalies can cause #Ontime > Deliveries
        df['OTP Rate %'] = np.minimum(raw_otp, 100.0)
    else:
        df['_total_deliveries'] = df.get('Delivery Volume', 0)
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
    return df


def mobile_aggregate(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Aggregate Mobile Sellers data. Riders are SUMMED (already de-duplicated
    for date-split weeks in load_mobile_data), all other numerics are summed."""
    if not group_cols:
        numeric = df.select_dtypes(include='number').columns.tolist()
        return pd.DataFrame([{c: df[c].sum() for c in numeric}])
    numeric = df.select_dtypes(include='number').columns.tolist()
    agg_dict = {c: 'sum' for c in numeric if c not in group_cols}
    return df.groupby(group_cols, observed=True).agg(agg_dict).reset_index()


# ── Borzo data loaders ──────────────────────────────────────────────────────────
# File 1: "Borzo Metrics Masterfile 2022 - Now.xlsx" — overall monthly time series
# File 2: "Summary Penjualan 2025.xlsx" — per-client breakdown for 2025 (12 month tabs)
#
# Naming convention to match Blitz terminology (user-confirmed):
#   GMV         → "Revenue" (group-level, comparable to Blitz Total Revenue)
#   Margin/Comm → "GP"      (group-level, comparable to Blitz GP)
#   GMV - Comm  → "Cost"    (courier cost)

BORZO_MONTH_SHEETS = {
    'Jan 25': 1, 'Feb 25': 2, 'Mar 25': 3, 'Apr 25': 4,
    'May 25': 5, 'June 25': 6, 'July 25': 7, 'Aug 25': 8,
    'Sept 25': 9, 'Okt 25': 10, 'Nov 25': 11, 'Dec 25': 12,
}


@st.cache_data(show_spinner="Loading Borzo monthly data...")
def load_borzo_monthly(file_bytes: bytes) -> pd.DataFrame | None:
    """Load the Borzo Masterfile 'Query result' sheet → one row per month.

    Returns a tidy dataframe with Blitz-comparable column names. Drops rows
    with no 'revenue' (i.e. forecast placeholders for future months).
    """
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name='Query result', header=0)
        df.columns = [str(c).strip() for c in df.columns]

        # Coerce all numeric-looking columns
        keep_numeric = [
            'revenue', 'revenue after VAT', 'margin', 'billing',
            'completed orders', 'completed deliveries', 'deliveries',
            'active clients', 'active couriers', 'new clients', 'new couriers',
            'AOV', 'AOR', 'ADV', 'ADR',
            '%margin', '%margin after VAT', '%cancelled', 'insurance fee',
            'penalties', 'additional charges',
        ]
        for c in keep_numeric:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')

        # Drop forecast / empty future rows (no revenue recorded yet)
        df = df[df['revenue'].notna() & (df['revenue'] > 0)].copy()

        # Authoritative period from 'last date'
        df['last date'] = pd.to_datetime(df['last date'], errors='coerce')
        df['Year']        = df['last date'].dt.year.astype('Int64')
        df['MonthNum']    = df['last date'].dt.month.astype('Int64')
        df['Month']       = pd.Categorical(
            df['last date'].dt.strftime('%B'),
            categories=MONTH_ORDER, ordered=True
        )
        df['PeriodLabel'] = df['last date'].dt.strftime('%Y-%m')

        # Blitz-comparable aliases
        df['GMV']        = df['billing']
        df['Commission'] = df['margin']
        df['Revenue']    = df['GMV']              # "group Revenue" (user-confirmed)
        df['GP']         = df['Commission']       # "group GP"      (user-confirmed)
        df['Cost']       = df['GMV'] - df['Commission']   # courier cost
        df['GP Margin %'] = np.where(df['GMV'] != 0, df['GP'] / df['GMV'] * 100, 0)
        df['Orders']     = df['completed orders']
        df['Deliveries'] = df['completed deliveries']
        df['Active Clients']  = df['active clients']
        df['Active Couriers'] = df['active couriers']
        df['Company']    = 'Borzo'

        return df.reset_index(drop=True)
    except Exception:
        return None


@st.cache_data(show_spinner="Loading Borzo per-client data...")
def load_borzo_clients(file_bytes: bytes) -> pd.DataFrame | None:
    """Load the 'Summary Penjualan' workbook (12 monthly tabs) → tidy per-client df.

    One row per (Year, Month, Client). Excludes the 'Grand Total' summary row.
    2025 only by design (per user) — historical per-client data will arrive later.
    """
    try:
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        frames = []
        for sheet, mo in BORZO_MONTH_SHEETS.items():
            if sheet not in xl.sheet_names:
                continue
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=2)
            df.columns = [str(c).strip().lower() for c in df.columns]

            # Normalize the "Cash For Courier" case variance
            rename = {}
            for c in df.columns:
                if 'cash for courier' in c.lower():
                    rename[c] = 'sum of cash for courier'
            if rename:
                df = df.rename(columns=rename)

            needed = ['client_id', 'client_name', 'count of order_id',
                      'sum of gmv_local', 'sum of cash for courier', 'sum of comission']
            if not all(c in df.columns for c in needed):
                continue

            # Drop Grand Total and blank rows
            df = df[df['client_id'].astype(str).str.strip().str.lower() != 'grand total']
            df = df[df['client_id'].notna()]

            for c in ['count of order_id', 'sum of gmv_local',
                      'sum of cash for courier', 'sum of comission']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

            df['Year']  = 2025
            df['MonthNum']  = mo
            df['Month'] = MONTH_ORDER[mo - 1]
            frames.append(df)

        if not frames:
            return None

        out = pd.concat(frames, ignore_index=True)
        out = out.rename(columns={
            'client_id':               'ClientID',
            'client_name':             'ClientName',
            'count of order_id':       'Orders',
            'sum of gmv_local':        'GMV',
            'sum of cash for courier': 'CourierCost',
            'sum of comission':        'Commission',
        })
        # Blitz-comparable aliases
        out['Revenue'] = out['GMV']
        out['GP']      = out['Commission']
        out['Cost']    = out['CourierCost']
        out['GP Margin %'] = np.where(out['GMV'] != 0, out['GP'] / out['GMV'] * 100, 0)
        out['Company'] = 'Borzo'
        out['ClientName'] = out['ClientName'].fillna('(unnamed)').astype(str).str.strip()
        out['ClientName'] = out['ClientName'].replace('', '(unnamed)')
        out['Month'] = pd.Categorical(out['Month'], categories=MONTH_ORDER, ordered=True)

        return out
    except Exception:
        return None


def get_borzo_latest_month(df_monthly: pd.DataFrame) -> tuple[int, int] | None:
    """Return (year, month_num) of latest month with actual data."""
    if df_monthly is None or df_monthly.empty:
        return None
    latest = df_monthly.sort_values('last date').iloc[-1]
    return int(latest['Year']), int(latest['MonthNum'])
