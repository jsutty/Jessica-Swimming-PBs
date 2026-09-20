import re
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests
import streamlit as st

# ==========================================
# SWIMMER PROFILE CONFIG
# ==========================================
SWIMMER_NAME = "Jessica Sutcliffe"
SWIMMER_TIREF = "1749292"
SWIMMER_URL = f"https://www.swimmingresults.org/individualbest/personal_best.php?back=individualbestname&mode=A&name=Sutcliffe&tiref={SWIMMER_TIREF}#"

st.set_page_config(
    page_title=f"{SWIMMER_NAME} - PB & Championship Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# TIME CONVERSION HELPERS
# ==========================================
def time_to_seconds(time_str: str) -> float | None:
    """Converts MM:SS.ss or SS.ss into float seconds."""
    if not time_str or not isinstance(time_str, str):
        return None
    time_str = time_str.strip()
    match = re.search(r"(?:(\d+):)?(\d+\.\d+)", time_str)
    if not match:
        return None
    mins, secs = match.groups()
    return (float(mins) * 60 if mins else 0.0) + float(secs)


def seconds_to_time(seconds: float | None) -> str:
    """Converts float seconds back into display format."""
    if seconds is None or pd.isna(seconds):
        return "--"
    mins = int(seconds // 60)
    rem_sec = seconds % 60
    if mins > 0:
        return f"{mins}:{rem_sec:05.2f}"
    return f"{rem_sec:05.2f}"


# ==========================================
# SCRAPER (Automated Fetch from Swim England)
# ==========================================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_pbs():
    """Scrapes live PB data for Jessica from swimmingresults.org."""
    try:
        response = requests.get(
            SWIMMER_URL,
            impersonate="chrome120",
            timeout=15,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        response.raise_for_status()
    except Exception as e:
        return None, f"Could not connect to Swim England: {str(e)}"

    soup = BeautifulSoup(response.text, "html.parser")
    records = []
    current_course = "Short Course (25m)"

    for elem in soup.find_all(["h3", "h4", "table"]):
        if elem.name in ["h3", "h4"]:
            title = elem.get_text().lower()
            if "long course" in title or "50m" in title:
                current_course = "Long Course (50m)"
            elif "short course" in title or "25m" in title:
                current_course = "Short Course (25m)"
            continue

        if elem.name == "table":
            rows = elem.find_all("tr")
            for row in rows:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 2:
                    event_raw = cols[0]
                    time_raw = cols[1]

                    if "event" in event_raw.lower() or "time" in time_raw.lower():
                        continue

                    sec = time_to_seconds(time_raw)
                    if sec is not None:
                        records.append(
                            {
                                "Course": current_course,
                                "Event": event_raw,
                                "PB_Time": time_raw,
                                "PB_Sec": sec,
                                "Date": cols[2] if len(cols) > 2 else "",
                                "Meet": cols[3] if len(cols) > 3 else "",
                            }
                        )

    if not records:
        return None, "No times were found on the rankings page."

    return pd.DataFrame(records), None


# ==========================================
# SESSION STATE (Stores Qualifying Targets)
# ==========================================
# We store county and regional target dictionaries in session memory
if "target_times" not in st.session_state:
    st.session_state.target_times = {}

# ==========================================
# SIDEBAR: FILTERS & TARGET INPUT FORM
# ==========================================
st.sidebar.title("⚙️ Controls")

# Manual re-fetch button
if st.sidebar.button("🔄 Check for New Meet Results", use_container_width=True):
    fetch_live_pbs.clear()
    st.sidebar.success("Refreshed from Swim England!")

selected_course = st.sidebar.selectbox(
    "Course Filter", ["All Courses", "Short Course (25m)", "Long Course (50m)"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 Championship Target Times")
st.sidebar.caption(
    "Paste your County or Regional targets below when ready. Format each row as:\n`Event, Time` (e.g. `50 Free, 32.50`)"
)

with st.sidebar.form(key="target_form", clear_on_submit=False):
    target_tier = st.selectbox("Target Standard Level", ["County Championship", "Regional Championship"])
    target_course_input = st.selectbox("Target Course", ["Short Course (25m)", "Long Course (50m)"])
    raw_targets = st.text_area(
        "Paste target times (one per line):",
        placeholder="50 Freestyle, 31.50\n100 Freestyle, 1:08.00\n50 Backstroke, 36.20",
        height=140,
    )
    submit_targets = st.form_submit_button("💾 Save Target Times", use_container_width=True)

if submit_targets and raw_targets.strip():
    count_saved = 0
    for line in raw_targets.strip().split("\n"):
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if len(parts) >= 2:
            event_name = parts[0].lower()
            target_str = parts[1]
            sec_val = time_to_seconds(target_str)
            if sec_val:
                key = (target_tier, target_course_input, event_name)
                st.session_state.target_times[key] = {
                    "time_str": target_str,
                    "seconds": sec_val,
                }
                count_saved += 1
    if count_saved:
        st.sidebar.success(f"Saved {count_saved} target times!")

# ==========================================
# MAIN DASHBOARD
# ==========================================
st.title(f"🏊‍♀️ {SWIMMER_NAME}'s Performance Tracker")
st.markdown(
    f"Swim England Number: **{SWIMMER_TIREF}** &bull; [Official Rankings Profile]({SWIMMER_URL})"
)

with st.spinner("Fetching latest rankings from Swim England..."):
    df_pbs, error = fetch_live_pbs()

if error:
    st.error(error)
    st.stop()

# Helper to normalize event names for clean matching
def clean_event(t):
    t = str(t).lower()
    t = re.sub(r"freestyle", "free", t)
    t = re.sub(r"breaststroke", "breast", t)
    t = re.sub(r"backstroke", "back", t)
    t = re.sub(r"butterfly", "fly", t)
    return re.sub(r"[^a-z0-9]", "", t)

df_pbs["norm_event"] = df_pbs["Event"].apply(clean_event)

# Attach County & Regional target times from session state
def get_target(row, tier):
    for (t_tier, t_course, t_event), data in st.session_state.target_times.items():
        if t_tier == tier and t_course == row["Course"] and clean_event(t_event) == row["norm_event"]:
            return data["time_str"], data["seconds"]
    return None, None

df_pbs["County_Target"] = df_pbs.apply(lambda r: get_target(r, "County Championship")[0], axis=1)
df_pbs["County_Sec"] = df_pbs.apply(lambda r: get_target(r, "County Championship")[1], axis=1)

df_pbs["Regional_Target"] = df_pbs.apply(lambda r: get_target(r, "Regional Championship")[0], axis=1)
df_pbs["Regional_Sec"] = df_pbs.apply(lambda r: get_target(r, "Regional Championship")[1], axis=1)

# Primary evaluation against County targets (if entered)
def evaluate_cut(pb_sec, target_sec):
    if pd.isna(target_sec) or target_sec is None:
        return "No Standard Set", "--"
    diff = pb_sec - target_sec
    if diff <= 0:
        return "Qualified 🎯", f"-{abs(diff):.2f}s"
    elif diff <= 1.0:
        return "Within 1.0s ⚡", f"+{diff:.2f}s"
    else:
        return "Chasing ⏱️", f"+{diff:.2f}s"

eval_county = df_pbs.apply(lambda r: evaluate_cut(r["PB_Sec"], r["County_Sec"]), axis=1)
df_pbs["County_Status"] = [e[0] for e in eval_county]
df_pbs["County_Gap"] = [e[1] for e in eval_county]

# Course filter
if selected_course != "All Courses":
    filtered_df = df_pbs[df_pbs["Course"] == selected_course].copy()
else:
    filtered_df = df_pbs.copy()

# Summary KPI Cards
c1, c2, c3, c4 = st.columns(4)
c1.metric("Recorded PBs", len(filtered_df))
c2.metric("County Qualified", len(filtered_df[filtered_df["County_Status"] == "Qualified 🎯"]))
c3.metric("Within 1.0s", len(filtered_df[filtered_df["County_Status"] == "Within 1.0s ⚡"]))
c4.metric("Targets Configured", len(st.session_state.target_times))

st.markdown("---")

# Visual Display Rows
st.subheader("📊 Times & Championship Standards")

for _, row in filtered_df.iterrows():
    c_meta, c_prog = st.columns([2, 3])

    with c_meta:
        st.markdown(
            f"**{row['Event']}** ({row['Course']})  \n"
            f"Current PB: **`{row['PB_Time']}`**  \n"
            f"County Cut: `{row['County_Target'] if row['County_Target'] else '--'}` ({row['County_Gap']})  \n"
            f"Regional Cut: `{row['Regional_Target'] if row['Regional_Target'] else '--'}`"
        )

    with c_prog:
        if pd.notna(row["County_Sec"]):
            pct = min(max((row["County_Sec"] / row["PB_Sec"]) * 100.0 if row["PB_Sec"] > 0 else 0, 0), 100)
            st.progress(pct / 100.0, text=f"{row['County_Status']} ({pct:.1f}% pace)")
        else:
            st.caption("No County target entered yet. Use the sidebar form when you have them.")
    st.markdown("<hr style='margin: 0.25rem 0;'>", unsafe_allow_html=True)

with st.expander("📋 Full Results & Table View"):
    display_cols = ["Course", "Event", "PB_Time", "County_Target", "County_Gap", "Regional_Target", "Date", "Meet"]
    st.dataframe(filtered_df[display_cols], use_container_width=True, hide_index=True)
