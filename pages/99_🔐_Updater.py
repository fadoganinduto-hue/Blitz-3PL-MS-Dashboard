import streamlit as st
import base64
import requests

st.set_page_config(page_title="Admin Updater | Blitz", page_icon="🔐", layout="wide")
st.title("🔐 Admin — Update Dashboard Data")
st.caption("Upload and commit new data files to GitHub.")

if st.secrets.get("admin_password") is None:
    st.error("Admin password not configured in st.secrets. See SETUP.txt.")
    st.stop()

pw = st.text_input("Admin password", type="password")
if pw != st.secrets["admin_password"]:
    if pw:
        st.error("Incorrect password")
    st.stop()

st.success("Authenticated")
st.divider()

def commit_to_github(path, file_bytes, message):
    repo = st.secrets['github_repo']
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {st.secrets['github_token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    branch = st.secrets.get("github_branch", "main")

    # Debug: show what we're hitting (remove later)
    st.caption(f"API target: `{repo}` → `{path}` (branch: {branch})")

    r = requests.get(url, headers=headers, params={"ref": branch})
    sha = r.json().get("sha") if r.status_code == 200 else None

    payload = {
        "message": message,
        "content": base64.b64encode(file_bytes).decode(),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload)
    if r.status_code not in (200, 201):
        st.code(f"Status: {r.status_code}\n{r.text[:500]}", language="json")
    return r.status_code in (200, 201), r.json()

st.subheader("Delivery Data")
delivery_file = st.file_uploader(
    "Upload Delivery data file (.xlsx)",
    type=['xlsx'],
    key="admin_delivery"
)

if delivery_file:
    st.write(f"**File:** {delivery_file.name}")
    st.write(f"**Size:** {delivery_file.size:,} bytes")
    if st.button("Publish Delivery Data", key="btn_deliv"):
        file_bytes = delivery_file.getvalue()
        success, result = commit_to_github(
            "data/delivery_latest.xlsx",
            file_bytes,
            f"Admin: Update delivery_latest.xlsx"
        )
        if success:
            st.success("✅ Delivery data committed to GitHub")
            st.info("Streamlit Cloud will redeploy your app within ~30 seconds.")
        else:
            st.error(f"Failed to commit: {result.get('message', 'Unknown error')}")

st.divider()

st.subheader("Mobile Sellers Data")
mobile_file = st.file_uploader(
    "Upload Mobile Sellers data file (.xlsx)",
    type=['xlsx'],
    key="admin_mobile"
)

if mobile_file:
    st.write(f"**File:** {mobile_file.name}")
    st.write(f"**Size:** {mobile_file.size:,} bytes")
    if st.button("Publish Mobile Data", key="btn_mobile"):
        file_bytes = mobile_file.getvalue()
        success, result = commit_to_github(
            "data/mobile_sellers_latest.xlsx",
            file_bytes,
            f"Admin: Update mobile_sellers_latest.xlsx"
        )
        if success:
            st.success("✅ Mobile Sellers data committed to GitHub")
            st.info("Streamlit Cloud will redeploy your app within ~30 seconds.")
        else:
            st.error(f"Failed to commit: {result.get('message', 'Unknown error')}")
