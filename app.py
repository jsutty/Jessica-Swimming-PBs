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
# EXACT COLUMN SCRAPER (29 SWIMS ONLY)
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

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        # Look for header row to map columns dynamically
        header_row = None
        for r in rows:
            ths = r.find_all(["th", "td"])
            txts = [th.get_text(strip=True).upper() for th in ths]
            if any("EVENT" in t for t in txts) and (any("TIME" in t for t in txts) or any("LC" in t for t in txts) or any("SC" in t for t in txts)):
                header_row = txts
                break

        if not header_row:
            continue

        # Map column indices from site header
        event_col = -1
        lc_col = -1
        conv_sc_col = -1
        sc_col = -1
        conv_lc_col = -1
        date_col = -1
        meet_col = -1

        for i, h in enumerate(header_row):
            if "EVENT" in h:
                event_col = i
            elif "LC TIME" in h or h == "LC":
                lc_col = i
            elif "CONVERTED TO SC" in h or "CONV TO SC" in h:
                conv_sc_col = i
            elif "SC TIME" in h or h == "SC":
                sc_col = i
            elif "CONVERTED TO LC" in h or "CONV TO LC" in h:
                conv_lc_col = i
            elif "DATE" in h:
                date_col = i
            elif "MEET" in h:
                meet_col = i

        for r in rows:
            tds = r.find_all("td")
            if not tds or len(tds) < 2:
                continue

            vals = [td.get_text(strip=True) for td in tds]
            event_name = vals[event_col] if 0 <= event_col < len(vals) else vals[0]

            if not event_name or "EVENT" in event_name.upper():
                continue

            # Case A: Separate LC and SC columns side-by-side
            if lc_col != -1 and lc_col < len(vals):
                raw_lc = vals[lc_col]
                sec_lc = time_to_seconds(raw_lc)
                if sec_lc:
                    c_sc = vals[conv_sc_col] if 0 <= conv_sc_col < len(vals) else "--"
                    records.append({
                        "Course": "Long Course (50m)",
                        "Event": event_name,
                        "PB_Time": raw_lc,
                        "PB_Sec": sec_lc,
                        "Conv_Label": "Converted to SC",
                        "Conv_Time": c_sc,
                    })

            if sc_col != -1 and sc_col < len(vals):
                raw_sc = vals[sc_col]
                sec_sc = time_to_seconds(raw_sc)
                if sec_sc:
                    c_lc = vals[conv_lc_col] if 0 <= conv_lc_col < len(vals) else "--"
                    records.append({
                        "Course": "Short Course (25m)",
                        "Event": event_name,
                        "PB_Time": raw_sc,
                        "PB_Sec": sec_sc,
                        "Conv_Label": "Converted to LC",
                        "Conv_Time": c_lc,
                    })

            # Case B: Stacked single-course table format
            if lc_col == -1 and sc_col == -1:
                t_str = vals[1]
                sec = time_to_seconds(t_str)
                if sec:
                    table_txt = str(table).upper()
                    is_lc = "LONG COURSE" in table_txt or "50M" in table_txt
                    course_name = "Long Course (50m)" if is_lc else "Short Course (25m)"
                    conv_lbl = "Converted to SC" if is_lc else "Converted to LC"
                    conv_val = vals[2] if len(vals) > 2 and re.search(r"\d+\.\d+", vals[2]) else "--"
                    records.append({
                        "Course": course_name,
                        "Event": event_name,
                        "PB_Time": t_str,
                        "PB_Sec": sec,
                        "Conv_Label": conv_lbl,
                        "Conv_Time": conv_val,
                    })

    if not records:
        return None, "No times found."

    df = pd.DataFrame(records).drop_duplicates(subset=["Course", "Event", "PB_Time"])
    return df, None


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
    df_pbs, error = fetch_live_pbs()

if error:
    st.error(error)
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
