import re
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ==========================================
# SWIMMER & CLUB PROFILE CONFIG
# ==========================================
SWIMMER_NAME = "Jessica Sutcliffe"
SWIMMER_TIREF = "1749292"
SWIMMER_URL = f"https://www.swimmingresults.org/individualbest/personal_best.php?back=individualbestname&mode=A&name=Sutcliffe&tiref={SWIMMER_TIREF}"
CLUB_LOGO_URL = "https://www.swimleeds.org.uk/wp-content/uploads/2021/04/City-of-Leeds-Swimming-Club-Logo.png"

st.set_page_config(
    page_title=f"{SWIMMER_NAME} - City of Leeds SC Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
)

# ==========================================
# CITY OF LEEDS SC THEME STYLING
# ==========================================
st.markdown(
    f"""
    <style>
        /* Global & background styling */
        .main {{
            background-color: #f4f6fa;
        }}
        
        /* Header Banner */
        .leeds-header {{
            background: linear-gradient(135deg, #001a4d 0%, #003399 70%, #0055d4 100%);
            border-radius: 12px;
            padding: 24px 28px;
            color: #ffffff;
            margin-bottom: 25px;
            box-shadow: 0 4px 14px rgba(0, 32, 91, 0.15);
            border-left: 6px solid #FFC72C;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .leeds-title {{
            font-size: 2.1rem;
            font-weight: 800;
            color: #ffffff;
            margin: 0;
            letter-spacing: -0.5px;
        }}
        .leeds-sub {{
            font-size: 1.0rem;
            color: #FFC72C;
            font-weight: 600;
            margin-top: 4px;
        }}
        
        /* Unified Event Card */
        .event-card {{
            background: #ffffff;
            border-radius: 10px;
            padding: 18px 22px;
            margin-bottom: 18px;
            border: 1px solid #e1e6f0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            border-top: 4px solid #003399;
        }}
        .event-header {{
            font-size: 1.35rem;
            font-weight: 700;
            color: #00205B;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        /* Course Visual Badges */
        .pill-lc {{
            background-color: #003399;
            color: #ffffff;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 6px;
            display: inline-block;
            margin-right: 8px;
        }}
        .pill-sc {{
            background-color: #008080;
            color: #ffffff;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 6px;
            display: inline-block;
            margin-right: 8px;
        }}
        
        /* Status Badges */
        .badge-green {{
            background-color: #d1e7dd;
            color: #0f5132;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-orange {{
            background-color: #ffe5d0;
            color: #b25e00;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-red {{
            background-color: #f8d7da;
            color: #842029;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-gray {{
            background-color: #e9ecef;
            color: #6c757d;
            padding: 3px 8px;
            border-radius: 5px;
            font-weight: 500;
            display: inline-block;
        }}
        
        /* Metric block styling */
        div[data-testid="stMetric"] {{
            background-color: #ffffff;
            border: 1px solid #e1e6f0;
            padding: 12px 16px;
            border-radius: 10px;
            border-bottom: 3px solid #FFC72C;
            box-shadow: 0 2px 6px rgba(0,0,0,0.02);
        }}
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
# PARSER ENGINE
# ==========================================
def parse_swim_content(content_str: str):
    if not content_str or not content_str.strip():
        return None

    records = []
    event_pattern = re.compile(
        r"\b(freestyle|breaststroke|backstroke|butterfly|individual medley|im|free|breast|back|fly)\b", re.I
    )
    time_regex = re.compile(r"(?:\d+:)?\d{1,2}\.\d{2}")

    # Approach A: HTML table extraction
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

    # Approach B: Plain text line-by-line fallback
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
# SESSION STATE
# ==========================================
if "jessica_pbs_df" not in st.session_state:
    st.session_state.jessica_pbs_df = None

if "targets" not in st.session_state:
    st.session_state.targets = {}

# ==========================================
# CITY OF LEEDS CLUB HEADER
# ==========================================
st.markdown(
    f"""
    <div class="leeds-header">
        <div>
            <div class="leeds-title">🏊‍♀️ {SWIMMER_NAME}</div>
            <div class="leeds-sub">CITY OF LEEDS SWIMMING CLUB &bull; RANKINGS TRACKER</div>
            <div style="font-size: 0.85rem; color: #d0e0ff; margin-top: 4px;">
                Swim England Number: <b>{SWIMMER_TIREF}</b> &bull; 
                <a href="{SWIMMER_URL}" target="_blank" style="color: #FFC72C; text-decoration: underline;">View Live Swim England Profile</a>
            </div>
        </div>
        <div>
            <img src="{CLUB_LOGO_URL}" style="max-height: 85px; background: rgba(255,255,255,0.9); padding: 5px; border-radius: 8px;" alt="City of Leeds SC" onerror="this.style.display='none'">
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# SYNC MODAL
# ==========================================
with st.expander("📥 Sync / Update Jessica's Times", expanded=(st.session_state.jessica_pbs_df is None)):
    st.markdown(
        f"""
        **Update times from Swim England:**
        1. Open: **[Jessica's Swim England Rankings Page]({SWIMMER_URL})**
        2. Tap anywhere on the table, tap **Select All** &rarr; **Copy**.
        3. Paste below and tap **Parse & Save Times**.
        """
    )
    pasted_data = st.text_area(
        "Paste page content or table rows here:",
        height=130,
        placeholder="Paste copied text or HTML from swimmingresults.org..."
    )
    if st.button("🚀 Parse & Save Times", use_container_width=True):
        parsed = parse_swim_content(pasted_data)
        if parsed is not None and not parsed.empty:
            st.session_state.jessica_pbs_df = parsed
            st.success(f"Successfully loaded {len(parsed)} swim times!")
            st.rerun()
        else:
            st.error("No valid swim times found. Ensure you copy the table containing events and times.")

df_pbs = st.session_state.jessica_pbs_df

if df_pbs is None or df_pbs.empty:
    st.info("👆 Tap the box above to paste Jessica's table. Once pasted, all consolidated event cards will display.")
    st.stop()

# ==========================================
# TARGET TIMES INPUT (YORKSHIRES & NERS)
# ==========================================
with st.expander("🎯 Set Championship Standards (Yorkshires & NERs)", expanded=False):
    st.markdown("Set target qualifying times for any event:")
    
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

# Attach targets
def get_target_info(row, field):
    key = f"{row['Course']}_{row['Event']}"
    if key in st.session_state.targets:
        return st.session_state.targets[key].get(field, None)
    return None

df_pbs["Yorkshires_Target"] = df_pbs.apply(lambda r: get_target_info(r, "Yorkshires"), axis=1)
df_pbs["Yorkshires_Sec"] = df_pbs.apply(lambda r: get_target_info(r, "Yorkshires_Sec"), axis=1)
df_pbs["NERs_Target"] = df_pbs.apply(lambda r: get_target_info(r, "NERs"), axis=1)
df_pbs["NERs_Sec"] = df_pbs.apply(lambda r: get_target_info(r, "NERs"), axis=1)

# Evaluate
y_eval = df_pbs.apply(lambda r: evaluate_cut(r["PB_Sec"], r["Yorkshires_Sec"]), axis=1)
df_pbs["Y_Status"] = [e[0] for e in y_eval]
df_pbs["Y_Gap"] = [e[1] for e in y_eval]
df_pbs["Y_Badge"] = [e[2] for e in y_eval]
df_pbs["Y_Pct"] = [e[3] for e in y_eval]

n_eval = df_pbs.apply(lambda r: evaluate_cut(r["PB_Sec"], r["NERs_Sec"]), axis=1)
df_pbs["N_Status"] = [e[0] for e in n_eval]
df_pbs["N_Gap"] = [e[1] for e in n_eval]
df_pbs["N_Badge"] = [e[2] for e in n_eval]
df_pbs["N_Pct"] = [e[3] for e in n_eval]

# ==========================================
# UNIQUE EVENTS QUALIFIED (BEST OF LC VS CONV LC)
# ==========================================
unique_yorkshires_qualified = 0
unique_events_list = sorted(df_pbs["Event"].unique().tolist())

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

# ==========================================
# KPI METRIC CARDS
# ==========================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Unique Yorkshires Cuts", unique_yorkshires_qualified, help="Unique strokes qualified using LC PB or Converted LC equivalent.")
c2.metric("Total Events Logged", len(unique_events_list))
c3.metric("Total PBs Recorded", len(df_pbs))
c4.metric("Championship Standards Set", len(st.session_state.targets))

st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

# Stroke category filter
stroke_filter = st.radio(
    "Filter by Stroke",
    ["All Events", "Freestyle", "Backstroke", "Breaststroke", "Butterfly", "Individual Medley"],
    horizontal=True,
)

# ==========================================
# CONSOLIDATED EVENT DISPLAY (ONE CARD PER EVENT)
# ==========================================
for ev in unique_events_list:
    if stroke_filter != "All Events" and stroke_filter.lower() not in ev.lower():
        continue

    ev_df = df_pbs[df_pbs["Event"] == ev]
    lc_rows = ev_df[ev_df["Course"] == "Long Course (50m)"]
    sc_rows = ev_df[ev_df["Course"] == "Short Course (25m)"]

    st.markdown(
        f"""
        <div class="event-card">
            <div class="event-header">
                <span>🏊 {ev}</span>
            </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. LONG COURSE ROW (If available)
    if not lc_rows.empty:
        r_lc = lc_rows.iloc[0]
        col_meta, col_bar = st.columns([1, 1])
        with col_meta:
            st.markdown(
                f"""
                <span class="pill-lc">🏊‍♂️ LC PB</span> <b><code>{r_lc['PB_Time']}</code></b> &nbsp;|&nbsp; 
                <span style="color: #666; font-size: 0.9rem;">Conv SC: <b>{r_lc['Conv_Time']}</b></span>  \n
                <span style="font-size: 0.92rem;">
                    Yorkshires Cut: <code>{r_lc['Yorkshires_Target'] or '--'}</code> &rarr; <span class="{r_lc['Y_Badge']}">{r_lc['Y_Gap']} ({r_lc['Y_Status']})</span>  \n
                    NERs Cut: <code>{r_lc['NERs_Target'] or '--'}</code> &rarr; <span class="{r_lc['N_Badge']}">{r_lc['N_Gap']} ({r_lc['N_Status']})</span>
                </span>
                """,
                unsafe_allow_html=True,
            )
        with col_bar:
            if r_lc["Yorkshires_Sec"] is not None and not pd.isna(r_lc["Yorkshires_Sec"]):
                st.caption(f"LC Yorkshires Progress: {r_lc['Y_Pct']:.1f}%")
                st.progress(r_lc["Y_Pct"] / 100.0)
            if r_lc["NERs_Sec"] is not None and not pd.isna(r_lc["NERs_Sec"]):
                st.caption(f"LC NERs Progress: {r_lc['N_Pct']:.1f}%")
                st.progress(r_lc["N_Pct"] / 100.0)
    else:
        st.caption("No official Long Course (50m) PB recorded for this event.")

    st.markdown("<div style='height: 10px; border-top: 1px dashed #e1e6f0; margin: 10px 0;'></div>", unsafe_allow_html=True)

    # 2. SHORT COURSE ROW (If available)
    if not sc_rows.empty:
        r_sc = sc_rows.iloc[0]
        col_meta_sc, col_bar_sc = st.columns([1, 1])
        with col_meta_sc:
            st.markdown(
                f"""
                <span class="pill-sc">🏊‍♀️ SC PB</span> <b><code>{r_sc['PB_Time']}</code></b> &nbsp;|&nbsp; 
                <span style="color: #666; font-size: 0.9rem;">Conv LC: <b>{r_sc['Conv_Time']}</b></span>  \n
                <span style="font-size: 0.92rem;">
                    Yorkshires Cut: <code>{r_sc['Yorkshires_Target'] or '--'}</code> &rarr; <span class="{r_sc['Y_Badge']}">{r_sc['Y_Gap']} ({r_sc['Y_Status']})</span>  \n
                    NERs Cut: <code>{r_sc['NERs_Target'] or '--'}</code> &rarr; <span class="{r_sc['N_Badge']}">{r_sc['N_Gap']} ({r_sc['N_Status']})</span>
                </span>
                """,
                unsafe_allow_html=True,
            )
        with col_bar_sc:
            if r_sc["Yorkshires_Sec"] is not None and not pd.isna(r_sc["Yorkshires_Sec"]):
                st.caption(f"SC Yorkshires Progress: {r_sc['Y_Pct']:.1f}%")
                st.progress(r_sc["Y_Pct"] / 100.0)
            if r_sc["NERs_Sec"] is not None and not pd.isna(r_sc["NERs_Sec"]):
                st.caption(f"SC NERs Progress: {r_sc['N_Pct']:.1f}%")
                st.progress(r_sc["N_Pct"] / 100.0)
    else:
        st.caption("No official Short Course (25m) PB recorded for this event.")

    st.markdown("</div>", unsafe_allow_html=True)

# Table summary expander
with st.expander("📋 View All Swims in Tabular Format"):
    view_table = df_pbs[
        ["Course", "Event", "PB_Time", "Conv_Label", "Conv_Time", "Yorkshires_Target", "Y_Gap", "Y_Status", "NERs_Target", "N_Gap", "N_Status"]
    ].rename(columns={
        "Y_Gap": "Yorkshires Gap",
        "Y_Status": "Yorkshires Status",
        "N_Gap": "NERs Gap",
        "N_Status": "NERs Status"
    })
    st.dataframe(view_table, use_container_width=True, hide_index=True)
