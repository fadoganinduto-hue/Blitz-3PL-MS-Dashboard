# CC5 — Per-dataset Data Freshness card in Home.py

In Home.py, AFTER the existing render_data_source_status() definition
and BEFORE render_data_source_status() is called, add this function:

def render_data_freshness_card() -> None:
    """Show per-dataset max period + row count in sidebar."""
    delivery = st.session_state.get("delivery_data")
    mobile   = st.session_state.get("mobile_data")
    borzo    = st.session_state.get("borzo_monthly_data")

    rows = []
    if delivery is not None and not delivery.empty and "Year" in delivery.columns:
        try:
            max_y = int(delivery["Year"].max())
            max_w = int(delivery[delivery["Year"] == max_y]["Week (by Year)"].max())
            rows.append(("Delivery", f"{max_y} W{max_w}", len(delivery)))
        except Exception:
            pass
    if mobile is not None and not mobile.empty and "Year" in mobile.columns:
        try:
            max_y = int(mobile["Year"].max())
            max_w = int(mobile[mobile["Year"] == max_y]["Week (by Year)"].max())
            rows.append(("Mobile", f"{max_y} W{max_w}", len(mobile)))
        except Exception:
            pass
    if borzo is not None and not borzo.empty and "Year" in borzo.columns:
        try:
            max_y = int(borzo["Year"].max())
            max_m = borzo[borzo["Year"] == max_y]["Month"].iloc[-1]
            rows.append(("Borzo", f"{max_y} {max_m}", len(borzo)))
        except Exception:
            pass

    if not rows:
        return

    with st.sidebar.expander("📅 Data freshness", expanded=False):
        for name, period, n in rows:
            st.markdown(
                f"<div style='display:flex; justify-content:space-between; "
                f"font-size:0.85rem; opacity:0.85;'>"
                f"<span>{name}</span>"
                f"<span>{period} · {n:,} rows</span></div>",
                unsafe_allow_html=True,
            )

Then call it right AFTER render_data_source_status():
    render_data_source_status()
    render_data_freshness_card()    # ← add this line