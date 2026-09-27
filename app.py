import re
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ==========================================
# SWIMMER PROFILE
# ==========================================
SWIMMER_NAME = "Jessica Sutcliffe"
SWIMMER_TIREF = "1749292"
SWIMMER_URL = f"https://www.swimmingresults.org/individualbest/personal_best.php?back=individualbestname&mode=A&name=Sutcliffe&tiref={SWIMMER_TIREF}"

st.set_page_config(
    page_title=f"{SWIMMER_NAME} - Yorkshires & NERs Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
)

# Custom badge pill styling
st.markdown(
    """
    <style>
        .badge-green {
            background-color: #d1e7dd;
            color: #0f5132;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 600;
            display: inline-block;
        }
        .badge-orange {
            background-color: #ffe5d0;
            color: #b25e00;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 600;
            display: inline-block;
        }
        .badge-red {
            background-color: #f8d7da;
            color: #842029;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 600;
            display: inline-block;
        }
        .badge-gray {
            background-color: #e9ecef;
            color: #6c757d;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 500;
            display: inline-block;
        }
    </style>
    """,
    unsafe_allow_html=True,
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
    try:
        return (float(mins) * 60 if mins else 0.0) + float(secs)
    except (ValueError, TypeError):
        return None


def seconds_to_time(seconds: float | None) -> str:
    if seconds is None or pd.isna(seconds):
        return "--"
    mins = int(seconds // 60)
    rem_sec = seconds % 60
    if mins > 0:
        return f"{mins}:{rem_sec:05.2f}"
    return f"{rem_sec:05.2f}"


# ==========================================
# ROBUST HTML & TEXT PARSER
# ==========================================
def parse_swim_content(content_str: str):
    if not content_str or not content_str.strip():
        return None

    records = []
    event_pattern = re.compile(
        r"\b(freestyle|breaststroke|backstroke|butterfly|individual medley|im|free|breast|back|fly)\b", re.I
    )
    time_regex = re.compile(r"(?:\d+:)?\d{1,2}\.\d{2}")

    # Approach A: HTML parsing
    if "<table" in content_str.lower() or "<tr" in content_str.lower():
        soup = BeautifulSoup(content_str, "html.parser")
        for table in soup.find_all("table"):
            table_txt = str(table).upper()
            prev_node = table.find_previous(["h2", "h3", "h4", "h5", "caption", "p"])
            prev_heading = prev_node.get_text(strip=True).upper() if prev_node else ""
            full_context = prev_heading + " " + table_txt[:300]

            is_lc = ("LONG COURSE" in full_context) or ("50M" in full_context)
            course_lbl = "Long Course (50m)" if is_lc else "Short Course (25m)"
            conv_lbl = "Converted to SC" if is_lc else "Converted to LC"

            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                cell_texts = [c.get_text(" ", strip=True) for c in cells]
                first_cell = cell_texts[0]

                if not (re.search(r"\d+", first_cell) and event_pattern.search(first_cell)):
                    continue

                times_found = []
                for ct in cell_texts[1:]:
                    match = time_regex.search(ct)
                    if match:
                        times_found.append(match.group(0))

                if not times_found:
                    continue

                actual_time = times_found[0]
                actual_sec = time_to_seconds(actual_time)
                conv_time = times_found[1] if len(times_found) > 1 else "--"
                conv_sec = time_to_seconds(conv_time)

                records.append({
                    "Course": course_lbl,
                    "Event": first_cell,
                    "PB_Time": actual_time,
                    "PB_Sec": actual_sec,
                    "Conv_Label": conv_lbl,
                    "Conv_Time": conv_time,
                    "Conv_Sec": conv_sec,
                })

    # Approach B: Plain Text row fallback (when copied without HTML tags)
    if not records:
        current_course = "Short Course (25m)"
        for line in content_str.split("\n"):
            line_str = line.strip()
            if "LONG COURSE" in line_str.upper() or "50M" in line_str.upper():
                current_course = "Long Course (50m)"
                continue
            elif "SHORT COURSE" in line_str.upper() or "25M" in line_str.upper():
                current_course = "Short Course (25m)"
                continue

            if event_pattern.search(line_str) and re.search(r"\d+", line_str):
                times = time_regex.findall(line_str)
                if times:
                    # Extract event name (text up to first time)
                    idx = line_str.find(times[0])
                    event_part = line_str[:idx].strip(" \t-:,")
                    actual_time = times[0]
                    actual_sec = time_to_seconds(actual_time)
                    conv_time = times[1] if len(times) > 1 else "--"
                    conv_sec = time_to_seconds(conv_time)
                    conv_lbl = "Converted to SC" if current_course == "Long Course (50m)" else "Converted to LC"

                    records.append({
                        "Course": current_course,
                        "Event": event_part if event_part else "Swim Event",
                        "PB_Time": actual_time,
                        "PB_Sec": actual_sec,
                        "Conv_Label": conv_lbl,
                        "Conv_Time": conv_time,
                        "Conv_Sec": conv_sec,
                    })

    if not records:
        return None

    df = pd.DataFrame(records).drop_duplicates(subset=["Course", "Event", "PB_Time"])
    return df


# ==========================================
# STATUS EVALUATOR
# ==========================================
def evaluate_cut(pb_sec, target_sec):
    if target_sec is None or pb_sec is None or pd.isna(target_sec) or pd.isna(pb_sec):
        return "No Standard", "--", "badge-gray", 0.0

    try:
        t_sec = float(target_sec)
        p_sec = float(pb_sec)
    except (ValueError, TypeError):
        return "No Standard", "--", "badge-gray", 0.0

    diff = p_sec - t_sec
    pct = min(max((t_sec / p_sec) * 100.0 if p_sec > 0 else 0, 0), 100)

    if diff <= 0:
        return "Qualified 🎯", f"-{abs(diff):.2f}s", "badge-green", pct
    elif diff <= 1.0:
        return "Within 1s ⚡", f"+{diff:.2f}s", "badge-orange", pct
    else:
        return "Chasing ⏱️", f"+{diff:.2f}s", "badge-red", pct


# ==========================================
# APP STATE INITIALIZATION
# ==========================================
if "jessica_pbs_df" not in st.session_state:
    st.session_state.jessica_pbs_df = None

if "targets" not in st.session_state:
    st.session_state.targets = {}

# ==========================================
# HEADER
# ==========================================
st.title(f"🏊‍♀️ {SWIMMER_NAME}'s Performance Tracker")
st.caption(f"Swim England Ref: **{SWIMMER_TIREF}** &bull; [Open Official Rankings Page]({SWIMMER_URL})")

# ==========================================
# SYNC / UPDATE EXPANDER (BYPASSES CLOUD 403 BLOCKS)
# ==========================================
with st.expander("📥 Sync / Update Jessica's Times (Tap here)", expanded=(st.session_state.jessica_pbs_df is None)):
    st.markdown(
        f"""
        **How to load / refresh her times on iPad:**
        1. Tap here to open Jessica's profile: **[Swim England Rankings Profile]({SWIMMER_URL})**
        2. On that page, tap anywhere on the table, tap **Select All** &rarr; **Copy**.
        3. Paste directly into the box below and tap **Parse & Save Times**.
        """
    )
    pasted_data = st.text_area(
        "Paste page content or table text here:",
        height=140,
        placeholder="Paste copied text or HTML from swimmingresults.org..."
    )
    if st.button("🚀 Parse & Save Times", use_container_width=True):
        parsed = parse_swim_content(pasted_data)
        if parsed is not None and not parsed.empty:
            st.session_state.jessica_pbs_df = parsed
            st.success(f"Successfully loaded {len(parsed)} swim times!")
            st.rerun()
        else:
            st.error("Could not find swim times in the pasted text. Please make sure the table rows are included.")

df_pbs = st.session_state.jessica_pbs_df

if df_pbs is None or df_pbs.empty:
    st.info("👆 Tap the expander above to paste Jessica's table. Once pasted, all 29 times and championship calculations will display.")
    st.stop()

# ==========================================
# TARGET TIMES INPUT (YORKSHIRES & NERS)
# ==========================================
with st.expander("🎯 Set Championship Standards (Yorkshires & NERs)", expanded=False):
    st.markdown("Set qualifying target times for an event:")
    
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
        st.success(f"Saved targets for {sel_ev} ({sel_course})!")

# Attach saved targets safely
def get_target_info(row, field):
    key = f"{row['Course']}_{row['Event']}"
    if key in st.session_state.targets:
        return st.session_state.targets[key].get(field, None)
    return None

df_pbs["Yorkshires_Target"] = df_pbs.apply(lambda r: get_target_info(r, "Yorkshires"), axis=1)
df_pbs["Yorkshires_Sec"] = df_pbs.apply(lambda r: get_target_info(r, "Yorkshires_Sec"), axis=1)
df_pbs["NERs_Target"] = df_pbs.apply(lambda r: get_target_info(r, "NERs"), axis=1)
df_pbs["NERs_Sec"] = df_pbs.apply(lambda r: get_target_info(r, "NERs"), axis=1)

# Evaluate Yorkshires
y_eval = df_pbs.apply(lambda r: evaluate_cut(r["PB_Sec"], r["Yorkshires_Sec"]), axis=1)
df_pbs["Y_Status"] = [e[0] for e in y_eval]
df_pbs["Y_Gap"] = [e[1] for e in y_eval]
df_pbs["Y_Badge"] = [e[2] for e in y_eval]
df_pbs["Y_Pct"] = [e[3] for e in y_eval]

# Evaluate NERs
n_eval = df_pbs.apply(lambda r: evaluate_cut(r["PB_Sec"], r["NERs_Sec"]), axis=1)
df_pbs["N_Status"] = [e[0] for e in n_eval]
df_pbs["N_Gap"] = [e[1] for e in n_eval]
df_pbs["N_Badge"] = [e[2] for e in n_eval]
df_pbs["N_Pct"] = [e[3] for e in n_eval]

# ==========================================
# UNIQUE EVENTS QUALIFIED LOGIC
# ==========================================
unique_yorkshires_qualified = 0
unique_events_list = df_pbs["Event"].unique().tolist()

for ev in unique_events_list:
    ev_df = df_pbs[df_pbs["Event"] == ev]
    is_qualified = False

    for _, row in ev_df.iterrows():
        y_sec = row["Yorkshires_Sec"]
        if y_sec is not None and not pd.isna(y_sec):
            pb_s = row["PB_Sec"]
            if pb_s is not None and not pd.isna(pb_s) and pb_s <= y_sec:
                is_qualified = True
                break

            c_sec = row["Conv_Sec"]
            if c_sec is not None and not pd.isna(c_sec) and c_sec <= y_sec:
                is_qualified = True
                break

    if is_qualified:
        unique_yorkshires_qualified += 1

# Course filter
selected_course = st.selectbox(
    "Filter Course", ["All Courses", "Short Course (25m)", "Long Course (50m)"]
)
if selected_course != "All Courses":
    display_df = df_pbs[df_pbs["Course"] == selected_course].copy()
else:
    display_df = df_pbs.copy()

# ==========================================
# KPI METRIC CARDS
# ==========================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Unique Yorkshires Cuts", unique_yorkshires_qualified, help="Unique events qualified using PB or Converted equivalent.")
c2.metric("Yorkshires Cuts (Rows)", len(display_df[display_df["Y_Status"] == "Qualified 🎯"]))
c3.metric("NERs Cuts (Rows)", len(display_df[display_df["N_Status"] == "Qualified 🎯"]))
c4.metric("Standards Configured", len(st.session_state.targets))

st.markdown("---")
st.subheader("📊 Performance vs Standards")

# ==========================================
# PERFORMANCE BREAKDOWN ROWS
# ==========================================
for _, r in display_df.iterrows():
    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.markdown(
            f"### {r['Event']}  \n"
            f"**Course:** {r['Course']} &bull; PB: **`{r['PB_Time']}`** &nbsp;|&nbsp; {r['Conv_Label']}: **`{r['Conv_Time']}`**"
        )
        
        y_cut_str = r['Yorkshires_Target'] or '--'
        n_cut_str = r['NERs_Target'] or '--'
        
        st.markdown(
            f"**Yorkshires Cut:** `{y_cut_str}` &rarr; <span class='{r['Y_Badge']}'>{r['Y_Gap']} ({r['Y_Status']})</span>  \n"
            f"**NERs Cut:** `{n_cut_str}` &rarr; <span class='{r['N_Badge']}'>{r['N_Gap']} ({r['N_Status']})</span>",
            unsafe_allow_html=True
        )

    with col_r:
        st.write("")
        if r["Yorkshires_Sec"] is not None and not pd.isna(r["Yorkshires_Sec"]):
            st.caption(f"**Yorkshires Progress:** {r['Y_Pct']:.1f}% pace attained")
            st.progress(r["Y_Pct"] / 100.0)
        else:
            st.caption("No Yorkshires target configured.")

        if r["NERs_Sec"] is not None and not pd.isna(r["NERs_Sec"]):
            st.caption(f"**NERs Progress:** {r['N_Pct']:.1f}% pace attained")
            st.progress(r["N_Pct"] / 100.0)
        else:
            st.caption("No NERs target configured.")

    st.markdown("<hr style='margin: 0.5rem 0;'>", unsafe_allow_html=True)

# Table summary
with st.expander("📋 Full Results Table"):
    view_table = display_df[
        ["Course", "Event", "PB_Time", "Conv_Label", "Conv_Time", "Yorkshires_Target", "Y_Gap", "Y_Status", "NERs_Target", "N_Gap", "N_Status"]
    ].rename(columns={
        "Y_Gap": "Yorkshires Gap",
        "Y_Status": "Yorkshires Status",
        "N_Gap": "NERs Gap",
        "N_Status": "NERs Status"
    })
    st.dataframe(view_table, use_container_width=True, hide_index=True)
