import re
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests
import streamlit as st

# ==========================================
# SWIMMER CONFIG
# ==========================================
SWIMMER_NAME = "Jessica Sutcliffe"
SWIMMER_TIREF = "1749292"
SWIMMER_URL = f"https://www.swimmingresults.org/individualbest/personal_best.php?back=individualbestname&mode=A&name=Sutcliffe&tiref={SWIMMER_TIREF}#"

st.set_page_config(
    page_title=f"{SWIMMER_NAME} - Yorkshires & NERs Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
)

# ==========================================
# TIME HELPERS
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


# ==========================================
# RESILIENT SCRAPER
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
        html_text = response.text
    except Exception as e:
        return None, f"Could not connect to Swim England: {str(e)}", ""

    soup = BeautifulSoup(html_text, "html.parser")
    records = []

    # Valid swim strokes to detect real event rows
    event_keywords = ["freestyle", "breaststroke", "backstroke", "butterfly", "individual medley", "im", "free", "breast", "back", "fly"]

    # Iterate through all tables and preceding headings
    for table in soup.find_all("table"):
        # Check nearby headers or table text to determine primary course
        table_context = ""
        prev_node = table.find_previous(["h2", "h3", "h4", "caption", "p"])
        if prev_node:
            table_context = prev_node.get_text(strip=True).upper()
        table_context += " " + table.get_text()[:200].upper()

        is_lc_section = "LONG COURSE" in table_context or "50M" in table_context
        course_label = "Long Course (50m)" if is_lc_section else "Short Course (25m)"
        conv_label = "Converted to SC" if is_lc_section else "Converted to LC"

        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            first_cell = cells[0].strip()
            # Must contain a recognized stroke and distance
            if not any(k in first_cell.lower() for k in event_keywords) or not re.search(r"\d+", first_cell):
                continue

            # Look for swim times formatted as MM:SS.ss or SS.ss in remaining cells
            time_matches = []
            for c_idx, cell_str in enumerate(cells[1:], start=1):
                if re.match(r"^(?:\d+:)?\d{2}\.\d{2}$", cell_str):
                    time_matches.append((c_idx, cell_str))

            if not time_matches:
                continue

            # The first time is the actual recorded PB
            actual_time_raw = time_matches[0][1]
            actual_sec = time_to_seconds(actual_time_raw)

            # If there's a second time, it represents the converted time column
            conv_time_raw = time_matches[1][1] if len(time_matches) > 1 else "--"

            records.append({
                "Course": course_label,
                "Event": first_cell,
                "PB_Time": actual_time_raw,
                "PB_Sec": actual_sec,
                "Conv_Label": conv_label,
                "Conv_Time": conv_time_raw,
            })

    if not records:
        # Pass preview of raw HTML back if nothing was parsed
        snippet = re.sub(r"\s+", " ", soup.get_text()[:400])
        return None, "No times found.", snippet

    df = pd.DataFrame(records).drop_duplicates(subset=["Course", "Event", "PB_Time"])
    return df, None, ""


# ==========================================
# APP SETUP
# ==========================================
st.title(f"🏊‍♀️ {SWIMMER_NAME}'s Performance Tracker")
st.caption(f"Swim England Number: **{SWIMMER_TIREF}** &bull; [Rankings Profile]({SWIMMER_URL})")

col_head1, col_head2 = st.columns([3, 1])
with col_head2:
    if st.button("🔄 Sync Live Times", use_container_width=True):
        fetch_live_pbs.clear()
        st.rerun()

with st.spinner("Fetching latest rankings..."):
    df_pbs, error, debug_snippet = fetch_live_pbs()

if error:
    st.error(error)
    if debug_snippet:
        with st.expander("Show Diagnostics"):
            st.write("Page text preview:", debug_snippet)
    st.stop()

# Initialize session targets
if "targets" not in st.session_state:
    st.session_state.targets = {}

# ==========================================
# TARGET TIMES INPUT (YORKSHIRES & NERS)
# ==========================================
with st.expander("🎯 Set Championship Standards (Yorkshires & NERs)", expanded=False):
    st.markdown("Set target times for an event:")
    
    unique_events = sorted(df_pbs["Event"].unique().tolist())
    
    c_in1, c_in2, c_in3 = st.columns(3)
    with c_in1:
        sel_ev = st.selectbox("Event", unique_events)
        sel_course = st.selectbox("Course", ["Short Course (25m)", "Long Course (50m)"])
    with c_in2:
        yorkshires_val = st.text_input("Yorkshires Qualifying Time", placeholder="e.g. 32.50")
    with c_in3:
        ners_val = st.text_input("NERs Qualifying Time", placeholder="e.g. 31.00")
        
    if st.button("💾 Save Target Times"):
        key = f"{sel_course}_{sel_ev}"
        st.session_state.targets[key] = {
            "Yorkshires": yorkshires_val.strip(),
            "NERs": ners_val.strip(),
            "Yorkshires_Sec": time_to_seconds(yorkshires_val),
            "NERs_Sec": time_to_seconds(ners_val),
        }
        st.success(f"Saved Yorkshires & NERs targets for {sel_ev} ({sel_course})!")

# Attach saved targets to DataFrame
def get_target_info(row, field):
    key = f"{row['Course']}_{row['Event']}"
    if key in st.session_state.targets:
        return st.session_state.targets[key].get(field, None)
    return None

df_pbs["Yorkshires_Target"] = df_pbs.apply(lambda r: get_target_info(r, "Yorkshires"), axis=1)
df_pbs["Yorkshires_Sec"] = df_pbs.apply(lambda r: get_target_info(r, "Yorkshires_Sec"), axis=1)
df_pbs["NERs_Target"] = df_pbs.apply(lambda r: get_target_info(r, "NERs"), axis=1)

# Status calculation based on Yorkshires
def calc_status(row):
    target = row["Yorkshires_Sec"]
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
df_pbs["Yorkshires_Status"] = [s[0] for s in status_tuples]
df_pbs["Yorkshires_Gap"] = [s[1] for s in status_tuples]

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
c1.metric("Recorded PBs", len(display_df))
c2.metric("Yorkshires Qualified", len(display_df[display_df["Yorkshires_Status"] == "Qualified 🎯"]))
c3.metric("Within 1.0s", len(display_df[display_df["Yorkshires_Status"] == "Within 1.0s ⚡"]))
c4.metric("Targets Configured", len(st.session_state.targets))

st.markdown("---")
st.subheader("📊 Times & Championship Standards")

for _, r in display_df.iterrows():
    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.markdown(
            f"**{r['Event']}** ({r['Course']})  \n"
            f"Official PB: **`{r['PB_Time']}`** &nbsp;|&nbsp; {r['Conv_Label']}: **`{r['Conv_Time']}`**  \n"
            f"Yorkshires Cut: `{r['Yorkshires_Target'] or '--'}` ({r['Yorkshires_Gap']}) &bull; "
            f"NERs Cut: `{r['NERs_Target'] or '--'}`"
        )
    with col_r:
        if pd.notna(r["Yorkshires_Sec"]) and r["Yorkshires_Sec"] is not None:
            pct = min(max((r["Yorkshires_Sec"] / r["PB_Sec"]) * 100.0 if r["PB_Sec"] > 0 else 0, 0), 100)
            st.progress(pct / 100.0, text=f"{r['Yorkshires_Status']} ({pct:.1f}% pace)")
        else:
            st.caption("No Yorkshires target set.")
    st.markdown("<hr style='margin: 0.2rem 0;'>", unsafe_allow_html=True)

with st.expander("📋 Full Results Table"):
    view_table = display_df[
        ["Course", "Event", "PB_Time", "Conv_Label", "Conv_Time", "Yorkshires_Target", "Yorkshires_Gap", "NERs_Target"]
    ]
    st.dataframe(view_table, use_container_width=True, hide_index=True)
