import io
import re
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st

# ==============================================================================
# 1. APPLICATION & SWIMMER PROFILE CONFIG
# ==============================================================================
SWIMMER_NAME = "Jessica Sutcliffe"
SWIMMER_TIREF = "1749292"
SWIMMER_URL = (
    "https://www.swimmingresults.org/individualbest/personal_best.php?"
    f"back=individualbestname&mode=A&name=Sutcliffe&tiref={SWIMMER_TIREF}"
)
CLUB_LOGO_URL = "https://www.swimleeds.org.uk/wp-content/uploads/2021/04/City-of-Leeds-Swimming-Club-Logo.png"

st.set_page_config(
    page_title=f"{SWIMMER_NAME} - City of Leeds SC Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
)

# ==============================================================================
# 2. STABLE CSS INJECTION (CITY OF LEEDS CLUB PALETTE)
# ==============================================================================
st.markdown(
    """
    <style>
    .main { background-color: #f6f8fb; }
    .stApp header { background-color: transparent; }
    .badge-q { background-color: #d1e7dd; color: #0f5132; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .badge-w { background-color: #ffe5d0; color: #b25e00; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .badge-c { background-color: #f8d7da; color: #842029; padding: 2px 6px; border-radius: 4px; font-weight: bold; }
    .badge-n { background-color: #e9ecef; color: #6c757d; padding: 2px 6px; border-radius: 4px; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #dce3ed;
        border-bottom: 4px solid #FFC72C;
        border-radius: 8px;
        padding: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# 3. TIME CONVERSION & MATHEMATICS
# ==============================================================================
def time_to_seconds(val):
    if not val or pd.isna(val):
        return None
    val_str = str(val).strip()
    match = re.search(r"(?:(\d+):)?(\d+\.\d+)", val_str)
    if not match:
        return None
    mins, secs = match.groups()
    try:
        return (float(mins) * 60.0 if mins else 0.0) + float(secs)
    except (ValueError, TypeError):
        return None

def seconds_to_time(sec):
    if sec is None or pd.isna(sec):
        return "--"
    mins = int(sec // 60)
    remainder = sec % 60
    if mins > 0:
        return f"{mins}:{remainder:05.2f}"
    return f"{remainder:05.2f}"

def evaluate_pace(pb_sec, target_sec):
    """Calculates status, gap text, CSS badge class, and percentage pace."""
    if pb_sec is None or target_sec is None or pd.isna(pb_sec) or pd.isna(target_sec):
        return "No Standard", "--", "badge-n", 0.0
    try:
        p = float(pb_sec)
        t = float(target_sec)
    except (ValueError, TypeError):
        return "No Standard", "--", "badge-n", 0.0

    gap = p - t
    pct = min(max((t / p) * 100.0 if p > 0 else 0, 0), 100)

    if gap <= 0:
        return "Qualified 🎯", f"-{abs(gap):.2f}s", "badge-q", pct
    elif gap <= 1.0:
        return "Within 1s ⚡", f"+{gap:.2f}s", "badge-w", pct
    else:
        return "Chasing ⏱️", f"+{gap:.2f}s", "badge-c", pct

# ==============================================================================
# 4. GALA SEQUENCE ENGINE (FREE -> BACK -> BREAST -> FLY -> IM & DISTANCE)
# ==============================================================================
def gala_order_key(event_name):
    name = str(event_name).lower()
    if "free" in name:
        stroke = 1
    elif "back" in name:
        stroke = 2
    elif "breast" in name:
        stroke = 3
    elif "fly" in name or "butterfly" in name:
        stroke = 4
    elif "medley" in name or "im" in name:
        stroke = 5
    else:
        stroke = 6

    dist_match = re.search(r"\d+", name)
    dist = int(dist_match.group(0)) if dist_match else 9999
    return (stroke, dist, name)

# ==============================================================================
# 5. DATA INGESTION & CLIPBOARD PARSERS
# ==============================================================================
def parse_swim_england_table(raw_content):
    if not raw_content or not str(raw_content).strip():
        return None

    records = []
    event_pattern = re.compile(
        r"\b(freestyle|breaststroke|backstroke|butterfly|individual medley|im|free|breast|back|fly)\b",
        re.I,
    )
    time_regex = re.compile(r"(?:\d+:)?\d{1,2}\.\d{2}")

    # Branch A: HTML structure
    if "<table" in raw_content.lower() or "<tr" in raw_content.lower():
        soup = BeautifulSoup(raw_content, "html.parser")
        for table in soup.find_all("table"):
            table_txt = str(table).upper()
            prev_node = table.find_previous(["h2", "h3", "h4", "h5", "caption", "p"])
            ctx = (prev_node.get_text(strip=True).upper() if prev_node else "") + " " + table_txt[:300]

            is_lc = ("LONG COURSE" in ctx) or ("50M" in ctx)
            c_name = "Long Course (50m)" if is_lc else "Short Course (25m)"
            conv_lbl = "Conv to SC" if is_lc else "Conv to LC"

            for tr in table.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if len(cells) < 2:
                    continue
                ev_candidate = cells[0]
                if not (re.search(r"\d+", ev_candidate) and event_pattern.search(ev_candidate)):
                    continue

                times = []
                for cell in cells[1:]:
                    m = time_regex.search(cell)
                    if m:
                        times.append(m.group(0))
                if not times:
                    continue

                pb_t = times[0]
                pb_s = time_to_seconds(pb_t)
                conv_t = times[1] if len(times) > 1 else "--"
                conv_s = time_to_seconds(conv_t)

                records.append({
                    "Course": c_name,
                    "Event": ev_candidate,
                    "PB_Time": pb_t,
                    "PB_Sec": pb_s,
                    "Conv_Label": conv_lbl,
                    "Conv_Time": conv_t,
                    "Conv_Sec": conv_s,
                })

    # Branch B: Plain Text fallback
    if not records:
        current_c = "Short Course (25m)"
        for line in raw_content.split("\n"):
            line_str = line.strip()
            u_line = line_str.upper()
            if "LONG COURSE" in u_line or "50M" in u_line:
                current_c = "Long Course (50m)"
                continue
            elif "SHORT COURSE" in u_line or "25M" in u_line:
                current_c = "Short Course (25m)"
                continue

            if event_pattern.search(line_str) and re.search(r"\d+", line_str):
                times = time_regex.findall(line_str)
                if times:
                    idx = line_str.find(times[0])
                    ev_cand = line_str[:idx].strip(" \t-:,")
                    pb_t = times[0]
                    pb_s = time_to_seconds(pb_t)
                    conv_t = times[1] if len(times) > 1 else "--"
                    conv_s = time_to_seconds(conv_t)
                    conv_lbl = "Conv to SC" if current_c == "Long Course (50m)" else "Conv to LC"

                    records.append({
                        "Course": current_c,
                        "Event": ev_cand if ev_cand else "Swim Event",
                        "PB_Time": pb_t,
                        "PB_Sec": pb_s,
                        "Conv_Label": conv_lbl,
                        "Conv_Time": conv_t,
                        "Conv_Sec": conv_s,
                    })

    if not records:
        return None
    return pd.DataFrame(records).drop_duplicates(subset=["Course", "Event", "PB_Time"])

def parse_google_sheets_tsv(tsv_data, default_course):
    if not tsv_data or not str(tsv_data).strip():
        return 0
    lines = [ln.strip() for ln in str(tsv_data).strip().split("\n") if ln.strip()]
    if not lines:
        return 0

    sep = "\t" if "\t" in lines[0] else ","
    try:
        df = pd.read_csv(io.StringIO("\n".join(lines)), sep=sep)
    except Exception:
        return 0

    if df.empty or df.shape[1] < 2:
        return 0

    ev_col = df.columns[0]
    saved_count = 0

    for _, row in df.iterrows():
        ev = str(row[ev_col]).strip()
        if not ev:
            continue
        for col in df.columns[1:]:
            col_l = str(col).lower()
            val_s = str(row[col]).strip()
            sec = time_to_seconds(val_s)
            if sec is None:
                continue

            meet = "Yorkshires"
            if "ner winter" in col_l:
                meet = "NER Winter"
            elif "ner" in col_l:
                meet = "NERs"
            elif "yorkshire winter" in col_l or "yks winter" in col_l:
                meet = "Yorkshire Winter"

            age = "12" if "12" in col_l else "11"
            course = default_course
            if "long" in col_l or "50m" in col_l or "lc" in col_l:
                course = "Long Course (50m)"
            elif "short" in col_l or "25m" in col_l or "sc" in col_l:
                course = "Short Course (25m)"

            key = (meet, age, course, ev.lower())
            st.session_state.standards_db[key] = {"time": val_s, "sec": sec}
            saved_count += 1

    return saved_count

# ==============================================================================
# 6. SESSION STATE INITIALIZATION
# ==============================================================================
if "swimmer_df" not in st.session_state:
    st.session_state.swimmer_df = None

if "standards_db" not in st.session_state:
    st.session_state.standards_db = {}

def lookup_standard(meet, age, course, event_name):
    key = (meet, age, course, str(event_name).lower())
    if key in st.session_state.standards_db:
        return st.session_state.standards_db[key]["time"], st.session_state.standards_db[key]["sec"]

    clean_ev = re.sub(r"[^a-z0-9]", "", str(event_name).lower())
    for (m, a, c, e), data in st.session_state.standards_db.items():
        if m == meet and a == age and c == course and re.sub(r"[^a-z0-9]", "", e) == clean_ev:
            return data["time"], data["sec"]

    return None, None

# ==============================================================================
# 7. CLUB HEADER INTERFACE
# ==============================================================================
head_col1, head_col2 = st.columns([4, 1])
with head_col1:
    st.title(f"🏊‍♀️ {SWIMMER_NAME}")
    st.markdown(
        f"**City of Leeds Swimming Club** &bull; Swim England: `{SWIMMER_TIREF}` &bull; "
        f"[Official Rankings Profile]({SWIMMER_URL})"
    )
with head_col2:
    st.image(CLUB_LOGO_URL, width=120)

st.markdown("---")

# ==============================================================================
# 8. DATA INGESTION WORKFLOW EXPANDERS
# ==============================================================================
with st.expander("📥 Step 1: Update Jessica's Times from Rankings", expanded=(st.session_state.swimmer_df is None)):
    st.write("1. Open Jessica's Swim England profile using the link above.")
    st.write("2. Select all content from the page table, copy it, and paste it into the box below:")
    raw_input = st.text_area("Paste table content here:", height=110, placeholder="Paste Swim England table text or HTML...")
    if st.button("🚀 Process & Store Times", use_container_width=True):
        parsed = parse_swim_england_table(raw_input)
        if parsed is not None and not parsed.empty:
            st.session_state.swimmer_df = parsed
            st.success(f"Successfully captured {len(parsed)} swim times!")
            st.rerun()
        else:
            st.error("No valid times found. Please check that table rows were included.")

if st.session_state.swimmer_df is None:
    st.info("Paste and process Jessica's table above to load the tracking dashboard.")
    st.stop()

df = st.session_state.swimmer_df

with st.expander("🎯 Step 2: Import Qualifying Standards (Google Sheets & Manual)", expanded=False):
    tab_bulk, tab_single = st.tabs(["📋 Bulk Paste from Google Sheets", "✏️ Single Event Entry"])

    with tab_bulk:
        st.write("Copy and paste cells directly from Google Sheets or Excel with headers like `Event`, `Yorkshires 11`, `NER 12`, etc.:")
        b_course = st.selectbox("Assign Course for Copied Block:", ["Short Course (25m)", "Long Course (50m)"])
        tsv_paste = st.text_area("Paste spreadsheet cells here:", height=110)
        if st.button("📥 Import Standards", use_container_width=True):
            count = parse_google_sheets_tsv(tsv_paste, b_course)
            if count > 0:
                st.success(f"Loaded and saved {count} standards!")
                st.rerun()
            else:
                st.error("Unable to parse. Ensure first column contains event names and headers include meet names.")

    with tab_single:
        all_evs = sorted(df["Event"].unique().tolist(), key=gala_order_key)
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            s_ev = st.selectbox("Event", all_evs)
            s_course = st.selectbox("Course", ["Short Course (25m)", "Long Course (50m)"])
        with col_s2:
            s_meet = st.selectbox("Meet", ["Yorkshires", "Yorkshire Winter", "NERs", "NER Winter"])
            s_age = st.selectbox("Age Band", ["11", "12"])
        with col_s3:
            s_val = st.text_input("Target Cut (e.g. 32.50)")
            if st.button("💾 Save Standard", use_container_width=True):
                sec = time_to_seconds(s_val)
                if sec:
                    st.session_state.standards_db[(s_meet, s_age, s_course, s_ev.lower())] = {"time": s_val.strip(), "sec": sec}
                    st.success(f"Saved {s_meet} Age {s_age} target for {s_ev}!")
                    st.rerun()

# ==============================================================================
# 9. DASHBOARD CONTROLS & FILTERING
# ==============================================================================
f_col1, f_col2 = st.columns([1, 2])
with f_col1:
    active_age = st.radio("🎯 **Active Age Band for Progress Gauges:**", ["11", "12"], horizontal=True, index=0)
with f_col2:
    selected_stroke = st.radio(
        "🏊 **Filter by Stroke:**",
        ["All Events", "Freestyle", "Backstroke", "Breaststroke", "Butterfly", "Individual Medley"],
        horizontal=True,
    )

# Unique Events Gala Sort
unique_events = sorted(df["Event"].unique().tolist(), key=gala_order_key)

# Calculate Unique Yorkshires Cuts for Active Age
unique_yks_cuts = 0
for ev in unique_events:
    sub = df[df["Event"] == ev]
    is_q = False
    for _, r in sub.iterrows():
        _, target_s = lookup_standard("Yorkshires", active_age, r["Course"], ev)
        if target_s is not None:
            if r["PB_Sec"] is not None and r["PB_Sec"] <= target_s:
                is_q = True
                break
            if r["Conv_Sec"] is not None and r["Conv_Sec"] <= target_s:
                is_q = True
                break
    if is_q:
        unique_yks_cuts += 1

# Metric Row
m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Unique Yorkshires (Age {active_age})", unique_yks_cuts)
m2.metric("Total Events Logged", len(unique_events))
m3.metric("Total Recorded PBs", len(df))
m4.metric("Standards Configured", len(st.session_state.standards_db))

st.markdown("---")

# ==============================================================================
# 10. UNIFIED EVENT CARDS (CLEAN UI COMPONENTS, ZERO STRING ERRORS)
# ==============================================================================
for ev in unique_events:
    if selected_stroke != "All Events" and selected_stroke.lower() not in ev.lower():
        continue

    ev_rows = df[df["Event"] == ev]
    lc_sub = ev_rows[ev_rows["Course"] == "Long Course (50m)"]
    sc_sub = ev_rows[ev_rows["Course"] == "Short Course (25m)"]

    with st.container():
        st.subheader(f"🏊 {ev}")

        # --- 1. LONG COURSE ROW ---
        if not lc_sub.empty:
            lc_r = lc_sub.iloc[0]
            col_l, col_r = st.columns([1, 1])

            # Retrieve targets
            y11_t, y11_s = lookup_standard("Yorkshires", "11", "Long Course (50m)", ev)
            y12_t, y12_s = lookup_standard("Yorkshires", "12", "Long Course (50m)", ev)
            n11_t, n11_s = lookup_standard("NERs", "11", "Long Course (50m)", ev)
            n12_t, n12_s = lookup_standard("NERs", "12", "Long Course (50m)", ev)
            yw_t, _ = lookup_standard("Yorkshire Winter", active_age, "Long Course (50m)", ev)
            nw_t, _ = lookup_standard("NER Winter", active_age, "Long Course (50m)", ev)

            # Evaluate
            ev_y11 = evaluate_pace(lc_r["PB_Sec"], y11_s)
            ev_y12 = evaluate_pace(lc_r["PB_Sec"], y12_s)
            ev_n11 = evaluate_pace(lc_r["PB_Sec"], n11_s)
            ev_n12 = evaluate_pace(lc_r["PB_Sec"], n12_s)

            with col_l:
                st.markdown(f"**🏊‍♂️ LC PB:** `{lc_r['PB_Time']}` &nbsp;|&nbsp; Conv SC: `{lc_r['Conv_Time']}`")
                st.markdown(
                    f"**Yorkshires:** Age 11: `{y11_t or '--'}` ({ev_y11[1]}) &bull; "
                    f"Age 12: `{y12_t or '--'}` ({ev_y12[1]})"
                )
                st.markdown(
                    f"**NERs:** Age 11: `{n11_t or '--'}` ({ev_n11[1]}) &bull; "
                    f"Age 12: `{n12_t or '--'}` ({ev_n12[1]})"
                )
                st.markdown(
                    f"**Winter (Age {active_age}):** YKS: `{yw_t or '--'}` &bull; NER: `{nw_t or '--'}`"
                )

            with col_r:
                act_y_s = y11_s if active_age == "11" else y12_s
                act_n_s = n11_s if active_age == "11" else n12_s
                if act_y_s is not None:
                    res_y = evaluate_pace(lc_r["PB_Sec"], act_y_s)
                    st.caption(f"LC Yorkshires (Age {active_age}): {res_y[0]} ({res_y[3]:.1f}%)")
                    st.progress(res_y[3] / 100.0)
                if act_n_s is not None:
                    res_n = evaluate_pace(lc_r["PB_Sec"], act_n_s)
                    st.caption(f"LC NERs (Age {active_age}): {res_n[0]} ({res_n[3]:.1f}%)")
                    st.progress(res_n[3] / 100.0)
        else:
            st.caption("No official Long Course (50m) PB recorded for this event.")

        st.markdown("---")

        # --- 2. SHORT COURSE ROW ---
        if not sc_sub.empty:
            sc_r = sc_sub.iloc[0]
            col_sl, col_sr = st.columns([1, 1])

            # Retrieve targets
            sy11_t, sy11_s = lookup_standard("Yorkshires", "11", "Short Course (25m)", ev)
            sy12_t, sy12_s = lookup_standard("Yorkshires", "12", "Short Course (25m)", ev)
            sn11_t, sn11_s = lookup_standard("NERs", "11", "Short Course (25m)", ev)
            sn12_t, sn12_s = lookup_standard("NERs", "12", "Short Course (25m)", ev)
            syw_t, _ = lookup_standard("Yorkshire Winter", active_age, "Short Course (25m)", ev)
            snw_t, _ = lookup_standard("NER Winter", active_age, "Short Course (25m)", ev)

            # Evaluate
            s_ev_y11 = evaluate_pace(sc_r["PB_Sec"], sy11_s)
            s_ev_y12 = evaluate_pace(sc_r["PB_Sec"], sy12_s)
            s_ev_n11 = evaluate_pace(sc_r["PB_Sec"], sn11_s)
            s_ev_n12 = evaluate_pace(sc_r["PB_Sec"], sn12_s)

            with col_sl:
                st.markdown(f"**🏊‍♀️ SC PB:** `{sc_r['PB_Time']}` &nbsp;|&nbsp; Conv LC: `{sc_r['Conv_Time']}`")
                st.markdown(
                    f"**Yorkshires:** Age 11: `{sy11_t or '--'}` ({s_ev_y11[1]}) &bull; "
                    f"Age 12: `{sy12_t or '--'}` ({s_ev_y12[1]})"
                )
                st.markdown(
                    f"**NERs:** Age 11: `{sn11_t or '--'}` ({s_ev_n11[1]}) &bull; "
                    f"Age 12: `{sn12_t or '--'}` ({s_ev_n12[1]})"
                )
                st.markdown(
                    f"**Winter (Age {active_age}):** YKS: `{syw_t or '--'}` &bull; NER: `{snw_t or '--'}`"
                )

            with col_sr:
                act_sy_s = sy11_s if active_age == "11" else sy12_s
                act_sn_s = sn11_s if active_age == "11" else sn12_s
                if act_sy_s is not None:
                    res_sy = evaluate_pace(sc_r["PB_Sec"], act_sy_s)
                    st.caption(f"SC Yorkshires (Age {active_age}): {res_sy[0]} ({res_sy[3]:.1f}%)")
                    st.progress(res_sy[3] / 100.0)
                if act_sn_s is not None:
                    res_sn = evaluate_pace(sc_r["PB_Sec"], act_sn_s)
                    st.caption(f"SC NERs (Age {active_age}): {res_sn[0]} ({res_sn[3]:.1f}%)")
                    st.progress(res_sn[3] / 100.0)
        else:
            st.caption("No official Short Course (25m) PB recorded for this event.")

        st.markdown("<br>", unsafe_allow_html=True)

# ==============================================================================
# 11. TABULAR SUMMARY VIEW
# ==============================================================================
with st.expander("📋 Tabular View of All Swims"):
    summary_rows = []
    for _, r in df.iterrows():
        y_cut, y_s = lookup_standard("Yorkshires", active_age, r["Course"], r["Event"])
        n_cut, n_s = lookup_standard("NERs", active_age, r["Course"], r["Event"])
        res_y = evaluate_pace(r["PB_Sec"], y_s)
        res_n = evaluate_pace(r["PB_Sec"], n_s)

        summary_rows.append({
            "Course": r["Course"],
            "Event": r["Event"],
            "PB Time": r["PB_Time"],
            "Converted Time": r["Conv_Time"],
            f"Yorkshires ({active_age}) Cut": y_cut or "--",
            "YKS Status": res_y[0],
            "YKS Gap": res_y[1],
            f"NERs ({active_age}) Cut": n_cut or "--",
            "NER Status": res_n[0],
            "NER Gap": res_n[1],
        })

    view_df = pd.DataFrame(summary_rows)
    view_df["sort"] = view_df["Event"].apply(gala_order_key)
    view_df = view_df.sort_values(by="sort").drop(columns=["sort"])
    st.dataframe(view_df, use_container_width=True, hide_index=True)
