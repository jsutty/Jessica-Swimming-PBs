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
    page_title=f"{SWIMMER_NAME} - PB Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
)

# ==========================================
# TIME HELPERS & CONVERSIONS
# ==========================================
def time_to_seconds(time_str: str) -> float | None:
    if not time_str or not isinstance(time_str, str):
        return None
    time_str = str(time_str).strip()
    match = re.search(r"(?:(\d+):)?(\d+\.\d+)", time_str)
    if not match:
        return None
    mins, secs = match.groups()
    return (float(mins) * 60 if mins else 0.0) + float(secs)


def seconds_to_time(seconds: float | None) -> str:
    if seconds is None or pd.isna(seconds):
        return "--"
    mins = int(seconds // 60)
    rem_sec = seconds % 60
    if mins > 0:
        return f"{mins}:{rem_sec:05.2f}"
    return f"{rem_sec:05.2f}"


def convert_time(event_name: str, sec: float, from_course: str) -> float | None:
    """Standard ASA/Swim England approximate conversion factors."""
    if sec is None or pd.isna(sec):
        return None

    name = str(event_name).lower()
    dist = 50
    if "100" in name:
        dist = 100
    elif "200" in name:
        dist = 200
    elif "400" in name:
        dist = 400
    elif "800" in name:
        dist = 800

    is_breast = "breast" in name

    if dist == 50:
        diff = 0.65 if not is_breast else 0.80
    elif dist == 100:
        diff = 1.40 if not is_breast else 1.70
    elif dist == 200:
        diff = 3.10 if not is_breast else 3.60
    elif dist == 400:
        diff = 6.40
    else:
        diff = 12.80

    if from_course == "Long Course (50m)":
        return max(sec - diff, 0.0)  # LC -> SC (faster)
    else:
        return sec + diff  # SC -> LC (slower)


# ==========================================
# SCRAPER FOR SWIMMINGRESULTS.ORG
# ==========================================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_pbs():
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

    # Find the main data tables
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        for row in rows:
            tds = row.find_all("td")
            if len(tds) < 2:
                continue

            event_name = tds[0].get_text(strip=True)
            if not event_name or "EVENT" in event_name.upper():
                continue

            # Check if row is split into: [Event, LC Time, LC Date, LC Meet, SC Time, SC Date, SC Meet]
            # or a single-course table format
            row_texts = [td.get_text(strip=True) for td in tds]

            # Case A: Combined table with 6+ columns (both courses)
            if len(row_texts) >= 5:
                # Find all time patterns in row
                time_indices = [i for i, text in enumerate(row_texts) if re.match(r"^(?:\d+:)?\d+\.\d+$", text)]

                if len(time_indices) >= 2:
                    # First time is typically LC, second is SC on standard Swim England profiles
                    lc_idx = time_indices[0]
                    sc_idx = time_indices[1]

                    lc_raw = row_texts[lc_idx]
                    sc_raw = row_texts[sc_idx]

                    lc_sec = time_to_seconds(lc_raw)
                    sc_sec = time_to_seconds(sc_raw)

                    if lc_sec:
                        conv_sc = convert_time(event_name, lc_sec, "Long Course (50m)")
                        records.append({
                            "Course": "Long Course (50m)",
                            "Event": event_name,
                            "PB_Time": lc_raw,
                            "PB_Sec": lc_sec,
                            "Converted_Course": "SC",
                            "Converted_Time": seconds_to_time(conv_sc),
                        })

                    if sc_sec:
                        conv_lc = convert_time(event_name, sc_sec, "Short Course (25m)")
                        records.append({
                            "Course": "Short Course (25m)",
                            "Event": event_name,
                            "PB_Time": sc_raw,
                            "PB_Sec": sc_sec,
                            "Converted_Course": "LC",
                            "Converted_Time": seconds_to_time(conv_lc),
                        })
                    continue

            # Case B: Standard row (Event, Time, ...)
            raw_time = row_texts[1]
            sec = time_to_seconds(raw_time)
            if sec:
                course = "Long Course (50m)" if ("LC" in str(table) or "50m" in str(table).lower()) else "Short Course (25m)"
                target_course = "SC" if course == "Long Course (50m)" else "LC"
                conv = convert_time(event_name, sec, course)
                records.append({
                    "Course": course,
                    "Event": event_name,
                    "PB_Time": raw_time,
                    "PB_Sec": sec,
                    "Converted_Course": target_course,
                    "Converted_Time": seconds_to_time(conv),
                })

    if not records:
        return None, "No times were found on the rankings page."

    return pd.DataFrame(records), None


# ==========================================
# APP SETUP & REFRESH
# ==========================================
st.title(f"🏊‍♀️ {SWIMMER_NAME}'s Performance Tracker")
st.caption(f"Swim England Number: **{SWIMMER_TIREF}** &bull; [Official Rankings Profile]({SWIMMER_URL})")

col_head1, col_head2 = st.columns([3, 1])
with col_head2:
    if st.button("🔄 Sync Live Times", use_container_width=True):
        fetch_live_pbs.clear()
        st.rerun()

with st.spinner("Fetching latest rankings..."):
    df_pbs, error = fetch_live_pbs()

if error:
    st.error(error)
    st.stop()

# Initialize session state dictionary for qualifying targets
if "targets" not in st.session_state:
    st.session_state.targets = {}

# ==========================================
# IPAD-STABLE INPUT CONTROLS (NO CRASH)
# ==========================================
with st.expander("🎯 Set Championship Qualifying Targets", expanded=False):
    st.markdown("Select an event and enter target times (e.g. `32.50` or `1:08.20`):")
    
    unique_events = sorted(df_pbs["Event"].unique().tolist())
    
    c_in1, c_in2, c_in3 = st.columns(3)
    with c_in1:
        sel_ev = st.selectbox("Event", unique_events)
        sel_course = st.selectbox("Course", ["Short Course (25m)", "Long Course (50m)"])
    with c_in2:
        county_val = st.text_input("County Target Time", placeholder="e.g. 32.50")
    with c_in3:
        regional_val = st.text_input("Regional Target Time", placeholder="e.g. 31.00")
        
    if st.button("💾 Save Target Time"):
        key = f"{sel_course}_{sel_ev}"
        st.session_state.targets[key] = {
            "County": county_val.strip(),
            "Regional": regional_val.strip(),
            "County_Sec": time_to_seconds(county_val),
            "Regional_Sec": time_to_seconds(regional_val),
        }
        st.success(f"Saved targets for {sel_ev} ({sel_course})!")

# Attach targets to dataframe
def get_target_info(row, field):
    key = f"{row['Course']}_{row['Event']}"
    if key in st.session_state.targets:
        return st.session_state.targets[key].get(field, None)
    return None

df_pbs["County_Target"] = df_pbs.apply(lambda r: get_target_info(r, "County"), axis=1)
df_pbs["County_Sec"] = df_pbs.apply(lambda r: get_target_info(r, "County_Sec"), axis=1)
df_pbs["Regional_Target"] = df_pbs.apply(lambda r: get_target_info(r, "Regional"), axis=1)

# Status calculation
def calc_status(row):
    target = row["County_Sec"]
    if pd.isna(target) or target is None:
        return "No Standard", "--"
    diff = row["PB_Sec"] - target
    if diff <= 0:
        return "Qualified 🎯", f"-{abs(diff):.2f}s"
    elif diff <= 1.0:
        return "Within 1.0s ⚡", f"+{diff:.2f}s"
    else:
        return "Chasing ⏱️", f"+{diff:.2f}s"

status_tuples = df_pbs.apply(calc_status, axis=1)
df_pbs["County_Status"] = [s[0] for s in status_tuples]
df_pbs["County_Gap"] = [s[1] for s in status_tuples]

# Course filter
selected_course = st.selectbox(
    "Filter Course", ["All Courses", "Short Course (25m)", "Long Course (50m)"]
)
if selected_course != "All Courses":
    display_df = df_pbs[df_pbs["Course"] == selected_course].copy()
else:
    display_df = df_pbs.copy()

# Metric summary cards
c1, c2, c3, c4 = st.columns(4)
c1.metric("Events Logged", len(display_df))
c2.metric("County Qualified", len(display_df[display_df["County_Status"] == "Qualified 🎯"]))
c3.metric("Within 1.0s", len(display_df[display_df["County_Status"] == "Within 1.0s ⚡"]))
c4.metric("Targets Set", len(st.session_state.targets))

st.markdown("---")
st.subheader("📊 Times & Championship Standards")

for _, r in display_df.iterrows():
    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.markdown(
            f"**{r['Event']}** ({r['Course']})  \n"
            f"Official PB: **`{r['PB_Time']}`** &nbsp;|&nbsp; Conv {r['Converted_Course']}: **`{r['Converted_Time']}`**  \n"
            f"County Cut: `{r['County_Target'] or '--'}` ({r['County_Gap']}) &bull; "
            f"Regional Cut: `{r['Regional_Target'] or '--'}`"
        )
    with col_r:
        if pd.notna(r["County_Sec"]) and r["County_Sec"] is not None:
            pct = min(max((r["County_Sec"] / r["PB_Sec"]) * 100.0 if r["PB_Sec"] > 0 else 0, 0), 100)
            st.progress(pct / 100.0, text=f"{r['County_Status']} ({pct:.1f}% pace)")
        else:
            st.caption("No target set for this event.")
    st.markdown("<hr style='margin: 0.2rem 0;'>", unsafe_allow_html=True)

with st.expander("📋 Full Results Table"):
    view_table = display_df[
        ["Course", "Event", "PB_Time", "Converted_Time", "County_Target", "County_Gap", "Regional_Target"]
    ].rename(columns={"Converted_Time": "Equivalent Conv Time"})
    st.dataframe(view_table, use_container_width=True, hide_index=True)
