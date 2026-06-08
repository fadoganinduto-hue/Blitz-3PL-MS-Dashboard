# Quick UI polish (UI1 + UI3 + UI5 + UI6)

## UI1 — "Latest" → "Selected" header in pages/1_📊_Overview.py

Find:
    st.subheader(f"Latest Week — {curr_lbl}  ·  {date_lbl}")
    st.subheader(f"Latest Month — {curr_lbl}")

Replace with logic that detects whether the user picked manually:
    is_latest = (curr_yr, curr_p) == periods[-1][:2]
    week_or_month = "Week" if view_mode == "Weekly" else "Month"
    prefix = "Latest" if is_latest else "Selected"
    if view_mode == "Weekly":
        st.subheader(f"{prefix} {week_or_month} — {curr_lbl}  ·  {date_lbl}")
    else:
        st.subheader(f"{prefix} {week_or_month} — {curr_lbl}")

## UI3 — pages/7_📈_Finance_Check.py year axis

Find the px.bar / px.line that uses x='Year' (around line 63).
Before the chart call, add:
    yoy = yoy.copy()
    yoy['Year'] = yoy['Year'].astype(int).astype(str)

After the chart call, add:
    fig.update_xaxes(type='category')

Apply same pattern to any other chart in this file plotting Year on an axis.

## UI5 — pages/5_⚡_EV_Overview.py and pages/30_⚡_EV_Leasing.py
                              labels + caption

In pages/30_⚡_EV_Leasing.py, find:
    k1.metric("EV Revenue", fmt_idr(tot_rev))

Replace with:
    k1.metric(
        "EV Revenue (PV)",
        fmt_idr(tot_rev),
        help="Production Value: positive when EV revenue exceeds EV cost; "
             "negative values reflect refunded/reversed EV charges."
    )

Just below the KPI strip, add:
    st.caption(
        "ℹ️ EV PV is a net production-value metric. Negative values are "
        "expected when refunds/reversals dominate; they reconcile to the "
        "source file's EV Related PV column."
    )

## UI6 — pages/99_🔐_Updater.py friendlier disabled state

Find:
    if st.secrets.get("admin_password") is None:
        st.error("Admin password not configured in st.secrets. See SETUP.txt.")
        st.stop()

Replace with:
    if st.secrets.get("admin_password") is None:
        st.info(
            "**Updater is unavailable in this environment.**\n\n"
            "Data now refreshes automatically from SharePoint — the "
            "Updater is only kept as a fallback for admins. To enable, "
            "add `admin_password` to Streamlit secrets."
        )
        st.stop()        