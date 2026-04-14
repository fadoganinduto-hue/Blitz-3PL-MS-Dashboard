import streamlit as st
import pandas as pd
from pathlib import Path
from data_loader import load_main_data, load_ev_data, load_action_items, load_mobile_data, generate_weekly_insights
from utils import fmt_idr, fmt_pct, fmt_vol, delta_badge, pop_pct, pop_label, build_mobile_trend

st.set_page_config(
    page_title="Blitz Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Stream selector in sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.header("📡 Data Stream")
    active_stream = st.radio(
        "Select stream",
        ["🚚 Delivery", "📱 Mobile Sellers"],
        key="stream_selector"
    )
    # Derive a simple flag for other pages to read
    st.session_state['active_stream'] = 'delivery' if '🚚' in active_stream else 'mobile'

st.title("🚀 Blitz Operations Dashboard")
st.caption("Weekly P&L and operations tracker. Upload your data files to refresh all views.")

st.divider()

# ── Auto-load from data/ folder if files exist ──────────────────────────────────
app_dir = Path(__file__).parent
for stream_type, filename, loader in [
    ('delivery', 'delivery_latest.xlsx', load_main_data),
    ('mobile', 'mobile_sellers_latest.xlsx', load_mobile_data),
]:
    fpath = app_dir / "data" / filename
    key = f"{stream_type}_data"
    if fpath.exists() and key not in st.session_state:
        try:
            with open(fpath, 'rb') as f:
                file_bytes = f.read()
            st.session_state[key] = loader(file_bytes)
            if stream_type == 'delivery':
                st.session_state['data'] = st.session_state[key]  # backward compat
                st.session_state['ev_data'] = load_ev_data(file_bytes)
                st.session_state['action_items'] = load_action_items(file_bytes)
        except Exception:
            pass

# ── File uploaders in tabs ──────────────────────────────────────────────────────
tab_deliv, tab_mobile = st.tabs(["Delivery Data", "Mobile Sellers Data"])

with tab_deliv:
    col_upload, col_status = st.columns([2, 1])
    with col_upload:
        uploaded_deliv = st.file_uploader(
            "**Upload Delivery data** — Raw Data Source export (.xlsx)",
            type=['xlsx'],
            help="Upload the Raw Data Source tab or full workbook",
            label_visibility="visible",
            key="uploader_delivery"
        )

    if uploaded_deliv:
        file_bytes = uploaded_deliv.getvalue()
        with st.spinner("Loading Delivery data..."):
            df = load_main_data(file_bytes)
            ev_df = load_ev_data(file_bytes)
            ai_df = load_action_items(file_bytes)

        st.session_state['delivery_data'] = df
        st.session_state['data'] = df  # backward compat for existing Delivery pages
        st.session_state['ev_data'] = ev_df
        st.session_state['action_items'] = ai_df

        with col_status:
            st.success(f"✅ Loaded {len(df):,} rows")
            st.caption(
                f"Years: {sorted(df['Year'].dropna().unique().tolist())} · "
                f"Clients: {df['Client Name'].nunique()} · "
                f"Locations: {df['Client Location'].nunique()}"
            )

with tab_mobile:
    col_upload, col_status = st.columns([2, 1])
    with col_upload:
        uploaded_mobile = st.file_uploader(
            "**Upload Mobile Sellers data** — NEW COLUMN TEMPLATE export (.xlsx)",
            type=['xlsx'],
            help="Upload the NEW COLUMN TEMPLATE sheet",
            label_visibility="visible",
            key="uploader_mobile"
        )

    if uploaded_mobile:
        file_bytes = uploaded_mobile.getvalue()
        with st.spinner("Loading Mobile Sellers data..."):
            df_mobile = load_mobile_data(file_bytes)

        st.session_state['mobile_data'] = df_mobile

        with col_status:
            st.success(f"✅ Loaded {len(df_mobile):,} rows")
            st.caption(
                f"Years: {sorted(df_mobile['Year'].dropna().unique().tolist())} · "
                f"Clients: {df_mobile['Client Name'].nunique()} · "
                f"Locations: {df_mobile['Client Location'].nunique()}"
            )

st.divider()

# ── Home page: show both streams' headline KPIs if loaded ────────────────────────
if st.session_state.get('delivery_data') is not None or st.session_state.get('mobile_data') is not None:
    st.subheader("📊 Latest Period KPIs")

    cols_kpi = st.columns([1, 1] if (st.session_state.get('delivery_data') is not None and st.session_state.get('mobile_data') is not None) else [1])

    # ── Delivery stream ─────────────────────────────────────────────────────────
    if st.session_state.get('delivery_data') is not None:
        df = st.session_state['delivery_data']
        from data_loader import get_latest_week
        yr, wk = get_latest_week(df)
        curr = df[(df['Year'] == yr) & (df['Week (by Year)'] == wk)]
        prev = df[(df['Year'] == yr) & (df['Week (by Year)'] == wk - 1)]

        if not curr.empty:
            curr_rev = curr['Total Revenue'].sum()
            curr_cost = curr['Total Cost'].sum()
            curr_gp = (curr['Total Revenue'] - curr['Total Cost']).sum()
            curr_vol = curr['Delivery Volume'].sum()

            prev_rev = prev['Total Revenue'].sum() if not prev.empty else 0
            prev_cost = prev['Total Cost'].sum() if not prev.empty else 0
            prev_gp = (prev['Total Revenue'] - prev['Total Cost']).sum() if not prev.empty else 0
            prev_vol = prev['Delivery Volume'].sum() if not prev.empty else 0

            with cols_kpi[0]:
                st.markdown("### 🚚 Delivery")
                k1, k2 = st.columns(2)
                k3, k4 = st.columns(2)

                rev_p = pop_pct(curr_rev, prev_rev)
                k1.metric("Revenue", fmt_idr(curr_rev),
                          f"{rev_p:+.1f}% WoW" if rev_p is not None else None)
                cost_p = pop_pct(curr_cost, prev_cost)
                k2.metric("Cost", fmt_idr(curr_cost),
                          f"{cost_p:+.1f}% WoW" if cost_p is not None else None,
                          delta_color="inverse")
                gp_p = pop_pct(curr_gp, prev_gp)
                k3.metric("Profit", fmt_idr(curr_gp),
                          f"{gp_p:+.1f}% WoW" if gp_p is not None else None)
                vol_p = pop_pct(curr_vol, prev_vol)
                k4.metric("Volume", fmt_vol(curr_vol),
                          f"{vol_p:+.1f}% WoW" if vol_p is not None else None)

    # ── Mobile Sellers stream ───────────────────────────────────────────────────
    if st.session_state.get('mobile_data') is not None:
        df_m = st.session_state['mobile_data']
        yr_m = int(df_m['Year'].max())
        wk_m = int(df_m[df_m['Year'] == yr_m]['Week (by Year)'].max())
        curr_m = df_m[(df_m['Year'] == yr_m) & (df_m['Week (by Year)'] == wk_m)]
        prev_m = df_m[(df_m['Year'] == yr_m) & (df_m['Week (by Year)'] == wk_m - 1)]

        if not curr_m.empty:
            curr_grev = curr_m['Gross Revenue'].sum()
            curr_brev = curr_m['Blitz Revenue'].sum()
            curr_cost = curr_m['Total Cost (Mobile)'].sum()
            curr_profit = curr_m['Profit Calc'].sum()
            curr_cups = curr_m['Total Cups Sold'].sum()
            curr_riders = curr_m['Total Active Riders'].max()

            prev_grev = prev_m['Gross Revenue'].sum() if not prev_m.empty else 0
            prev_brev = prev_m['Blitz Revenue'].sum() if not prev_m.empty else 0
            prev_cost = prev_m['Total Cost (Mobile)'].sum() if not prev_m.empty else 0
            prev_profit = prev_m['Profit Calc'].sum() if not prev_m.empty else 0
            prev_cups = prev_m['Total Cups Sold'].sum() if not prev_m.empty else 0
            prev_riders = prev_m['Total Active Riders'].max() if not prev_m.empty else 0

            with cols_kpi[1 if st.session_state.get('delivery_data') is not None else 0]:
                st.markdown("### 📱 Mobile Sellers")
                k1, k2 = st.columns(2)
                k3, k4 = st.columns(2)
                k5, k6 = st.columns(2)

                grev_p = pop_pct(curr_grev, prev_grev)
                k1.metric("Gross Revenue", fmt_idr(curr_grev),
                          f"{grev_p:+.1f}% WoW" if grev_p is not None else None)
                cost_p = pop_pct(curr_cost, prev_cost)
                k2.metric("Total Cost", fmt_idr(curr_cost),
                          f"{cost_p:+.1f}% WoW" if cost_p is not None else None,
                          delta_color="inverse")
                profit_p = pop_pct(curr_profit, prev_profit)
                k3.metric("Profit", fmt_idr(curr_profit),
                          f"{profit_p:+.1f}% WoW" if profit_p is not None else None)
                cups_p = pop_pct(curr_cups, prev_cups)
                k4.metric("Cups Sold", fmt_vol(curr_cups),
                          f"{cups_p:+.1f}% WoW" if cups_p is not None else None)
                k5.metric("Active Riders", fmt_vol(curr_riders),
                          f"{curr_riders - prev_riders:+.0f} WoW" if prev_riders > 0 else None)
                margin_curr = curr_profit / curr_grev * 100 if curr_grev > 0 else 0
                margin_prev = prev_profit / prev_grev * 100 if prev_grev > 0 else 0
                margin_p = margin_curr - margin_prev if prev_grev > 0 else None
                k6.metric("Profit Margin %", fmt_pct(margin_curr),
                          f"{margin_p:+.1f}pp WoW" if margin_p is not None else None)

    st.divider()

# ── Delivery-specific: Weekly Insights ──────────────────────────────────────────
if st.session_state.get('delivery_data') is not None:
    df = st.session_state['delivery_data']
    insights = generate_weekly_insights(df)

    if insights:
        yr = insights['year']
        wk = insights['week']
        dr = insights['date_range']
        st.subheader(f"📋 Delivery Weekly Insights — Week {wk} of {yr}  ·  {dr}")

        k1, k2, k3, k4 = st.columns(4)
        for col, metric, label, formatter in [
            (k1, 'Total Revenue', '💰 Revenue', fmt_idr),
            (k2, 'Total Cost', '💸 Total Cost', fmt_idr),
            (k3, 'GP', '📈 Gross Profit', fmt_idr),
            (k4, 'Delivery Volume', '📦 Volume', fmt_vol),
        ]:
            d = insights[metric]
            pct = d['pct_change']
            delta_str = f"{pct:+.1f}% WoW" if pct is not None else None
            delta_c = "normal" if (pct or 0) >= 0 else "inverse"
            if metric == 'Total Cost':
                delta_c = "inverse" if (pct or 0) >= 0 else "normal"
            col.metric(label, formatter(d['current']), delta_str, delta_color=delta_c)

        left, right = st.columns(2)

        with left:
            st.markdown("#### 🏆 Top 5 Clients by GP this week")
            top = insights['top_clients'].copy()
            top['GP'] = top['GP'].apply(fmt_idr)
            st.dataframe(top.rename(columns={'GP': 'Gross Profit'}),
                         use_container_width=True, hide_index=True)

        with right:
            neg = insights['negative_gp']
            if not neg.empty:
                st.markdown("#### 🔴 Clients with Negative GP")
                neg_disp = neg.copy()
                neg_disp['GP'] = neg_disp['GP'].apply(fmt_idr)
                st.dataframe(neg_disp.rename(columns={'GP': 'Gross Profit'}),
                             use_container_width=True, hide_index=True)
            else:
                st.markdown("#### ✅ No clients with negative GP this week")
                st.success("All clients are profitable this week.")

        m_left, m_right = st.columns(2)
        with m_left:
            imp = insights['biggest_improvers']
            if not imp.empty:
                st.markdown("#### ⬆️ Biggest Improvers (GP % WoW)")
                for _, r in imp.iterrows():
                    st.markdown(
                        f"**{r['Client Name']}** — GP {fmt_idr(r['GP'])}  "
                        f"{delta_badge(r['GP_pct'])}"
                    )

        with m_right:
            dec = insights['biggest_decliners']
            if not dec.empty:
                st.markdown("#### ⬇️ Biggest Decliners (GP % WoW)")
                for _, r in dec.iterrows():
                    st.markdown(
                        f"**{r['Client Name']}** — GP {fmt_idr(r['GP'])}  "
                        f"{delta_badge(r['GP_pct'])}"
                    )
    else:
        st.info("Insights will appear here once there are at least two weeks of Delivery data loaded.")

else:
    st.markdown("""
    ### Getting started

    **Delivery workflow (every Thursday):**
    1. In your Excel file, right-click the **Raw Data Source** tab → **Move or Copy** → tick **Create a copy** → **New book** → Save as `.xlsx`
    2. Upload that file using the **Delivery Data** tab above
    3. All Delivery pages refresh instantly

    **Mobile Sellers workflow:**
    1. Export the **NEW COLUMN TEMPLATE** sheet from your Mobile Sellers file
    2. Upload using the **Mobile Sellers Data** tab above
    3. All Mobile pages refresh instantly

    #### Pages by stream
    **Delivery:**
    - 📊 Overview, 👥 By Client, 🗺️ By Location, 🏙️ By Team
    - ⚡ EV Rental, 📈 Finance Check, 📋 Action Items, 🎯 SLA Check, 🔬 Deep Dive

    **Mobile Sellers:**
    - 📱 Mobile Overview, 📅 Mobile Period Performance, 👥 Mobile By Client
    - 🗺️ Mobile By Location, 🏙️ Mobile By Team, 🔬 Mobile Deep Dive
    """)
