import io
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
css_style = (
    "<style>\n"
    "    .main { background-color: #f4f6fa; }\n"
    "    .leeds-header {\n"
    "        background: linear-gradient(135deg, #001a4d 0%, #003399 70%, #0055d4 100%);\n"
    "        border-radius: 12px;\n"
    "        padding: 24px 28px;\n"
    "        color: #ffffff;\n"
    "        margin-bottom: 25px;\n"
    "        box-shadow: 0 4px 14px rgba(0, 32, 91, 0.15);\n"
    "        border-left: 6px solid #FFC72C;\n"
    "        display: flex;\n"
    "        align-items: center;\n"
    "        justify-content: space-between;\n"
    "    }\n"
    "    .leeds-title { font-size: 2.1rem; font-weight: 800; color: #ffffff; margin: 0; letter-spacing: -0.5px; }\n"
    "    .leeds-sub { font-size: 1.0rem; color: #FFC72C; font-weight: 600; margin-top: 4px; }\n"
    "    .event-card {\n"
    "        background: #ffffff;\n"
    "        border-radius: 10px;\n"
    "        padding: 18px 22px;\n"
    "        margin-bottom: 18px;\n"
    "        border: 1px solid #e1e6f0;\n"
    "        box-shadow: 0 2px 8px rgba(0,0,0,0.04);\n"
    "        border-top: 4px solid #003399;\n"
    "    }\n"
    "    .event-header { font-size: 1.35rem; font-weight: 700; color: #00205B; margin-bottom: 12px; }\n"
    "    .pill-lc { background-color: #003399; color: #ffffff; font-weight: 700; font-size: 0.8rem; padding: 4px 10px; border-radius: 6px; display: inline-block; margin-right: 8px; }\n"
    "    .pill-sc { background-color: #008080; color: #ffffff; font-weight: 700; font-size: 0.8rem; padding: 4px 10px; border-radius: 6px; display: inline-block; margin-right: 8px; }\n"
    "    .badge-green { background-color: #d1e7dd; color: #0f5132; padding: 2px 7px; border-radius: 5px; font-weight: 700; font-size: 0.85rem; display: inline-block; }\n"
    "    .badge-orange { background-color: #ffe5d0; color: #b25e00; padding: 2px 7px; border-radius: 5px; font-weight: 700; font-size: 0.85rem; display: inline-block; }\n"
    "    .badge-red { background-color: #f8d7da; color: #842029; padding: 2px 7px; border-radius: 5px; font-weight: 700; font-size: 0.85rem; display: inline-block; }\n"
    "    .badge-gray { background-color: #e9ecef; color: #6c757d; padding: 2px 7px; border-radius: 5px; font-weight: 500; font-size: 0.85rem; display: inline-block; }\n"
    "    div[data-testid='stMetric'] {\n"
    "        background-color: #ffffff;\n"
    "        border: 1px solid #e1e6f0;\n"
    "        padding: 12px 16px;\n"
    "        border-radius: 10px;\n"
    "        border-bottom: 3px solid #FFC72C;\n"
    "        box-shadow: 0 2px 6px rgba(0,0,0,0.02);\n"
    "    }\n"
    "</style>\n"
)
st.markdown(css_style, unsafe_allow_html=True)

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
# GALA ORDER SORTING KEY
# ==========================================
def event_sort_key(event_name: str) -> tuple:
    name = str(event_name).lower()
    if "free" in name:
        stroke_rank = 1
    elif "back" in name:
        stroke_rank = 2
    elif "breast" in name:
        stroke_rank = 3
    elif "fly" in name or "butterfly" in name:
        stroke_rank = 4
    elif "medley" in name or "im" in name:
        stroke_rank = 5
    else:
        stroke_rank = 6

    dist_match = re.search(r"\d+", name)
    dist = int(dist_match.group(0)) if dist_match else 9999
    return (stroke_rank, dist, name)


# ==========================================
# PARSER ENGINE FOR PB CONTENT
# ==========================================
def parse_swim_content(content_str: str):
    if not content_str or not content_str.strip():
        return None

    records = []
    event_pattern = re.compile(
        r"\b(freestyle|breaststroke|backstroke|butterfly|individual medley|im|free|breast|back|fly)\b", re.I
    )
    time_regex = re.compile(r"(?:\d+:)?\d{1,2}\.\d{2}")

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
# GOOGLE SHEETS / TSV TARGETS PARSER
# ==========================================
def parse_google_sheets_targets(tsv_str: str, default_course: str):
    if not tsv_str or not tsv_str.strip():
        return 0

    lines = [ln.strip() for ln in tsv_str.strip().split("\n") if ln.strip()]
    if not lines:
        return 0

    sep = "\t" if "\t" in lines[0] else ","
    try:
        df_raw = pd.read_csv(io.StringIO("\n".join(lines)), sep=sep)
    except Exception:
        return 0

    if df_raw.empty or df_raw.shape[1] < 2:
        return 0

    event_col = df_raw.columns[0]
    count_saved = 0

    for _, row in df_raw.iterrows():
        ev_name = str(row[event_col]).strip()
        if not ev_name:
            continue

        for col in df_raw.columns[1:]:
            col_clean = str(col).lower()
            val_str = str(row[col]).strip()
            val_sec = time_to_seconds(val_str)
            if val_sec is None:
                continue

            meet = "Yorkshires"
            if "ner winter" in col_clean:
                meet = "NER Winter"
            elif "ner" in col_clean:
                meet = "NERs"
            elif "yorkshire winter" in col_clean or "yks winter" in col_clean:
                meet = "Yorkshire Winter"

            age = "12" if "12" in col_clean else "11"

            course = default_course
            if "long" in col_clean or "50m" in col_clean or "lc" in col_clean:
                course = "Long Course (50m)"
            elif "short" in col_clean or "25m" in col_clean or "sc" in col_clean:
                course = "Short Course (25m)"

            target_key = (meet, age, course, ev_name.lower())
            st.session_state.multi_targets[target_key] = {
                "time_str": val_str,
                "seconds": val_sec,
            }
            count_saved += 1

    return count_saved


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
# SESSION STATE INITIALIZATION
# ==========================================
if "jessica_pbs_df" not in st.session_state:
    st.session_state.jessica_pbs_df = None

if "multi_targets" not in st.session_state:
    st.session_state.multi_targets = {}

# ==========================================
# CITY OF LEEDS CLUB HEADER
# ==========================================
header_html = (
    '<div class="leeds-header">\n'
    '  <div>\n'
    f'    <div class="leeds-title">🏊‍♀️ {SWIMMER_NAME}</div>\n'
    '    <div class="leeds-sub">CITY OF LEEDS SWIMMING CLUB &bull; CHAMPIONSHIP STANDARDS TRACKER</div>\n'
    '    <div style="font-size: 0.85rem; color: #d0e0ff; margin-top: 4px;">\n'
    f'      Swim England Number: <b>{SWIMMER_TIREF}</b> &bull; \n'
    f'      <a href="{SWIMMER_URL}" target="_blank" style="color: #FFC72C; text-decoration: underline;">View Live Swim England Profile</a>\n'
    '    </div>\n'
    '  </div>\n'
    '  <div>\n'
    f'    <img src="{CLUB_LOGO_URL}" style="max-height: 85px; background: rgba(255,255,255,0.9); padding: 5px; border-radius: 8px;" alt="City of Leeds SC" onerror="this.style.display=\'none\'">\n'
    '  </div>\n'
    '</div>\n'
)
st.markdown(header_html, unsafe_allow_html=True)

# ==========================================
# SYNC MODAL FOR SWIM RESULTS
# ==========================================
with st.expander("📥 Sync / Update Jessica's Times", expanded=(st.session_state.jessica_pbs_df is None)):
    instructions = (
        "**Update times from Swim England:**\n"
        f"1. Open: [Jessica's Swim England Rankings Page]({SWIMMER_URL})\n"
        "2. Select all and copy the table.\n"
        "3. Paste below and tap **Parse & Save Times**."
    )
    st.markdown(instructions)
    pasted_data = st.text_area(
        "Paste page content or table rows here:",
        height=120,
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
    st.info("👆 Tap the expander above to paste Jessica's table. Once pasted, all consolidated event cards will display.")
    st.stop()

# ==========================================
# TARGET TIMES IMPORTER
# ==========================================
with st.expander("🎯 Import Qualifying Standards (Google Sheets & Manual)", expanded=False):
    tab_bulk, tab_single = st.tabs(["📋 Paste from Google Sheets", "✏️ Single Event Entry"])

    with tab_bulk:
        bulk_desc = (
            "**Copy columns straight from Google Sheets / Excel.**\n\n"
            "Format example with header row:\n"
            "```text\n"
            "Event\tYorkshires 11\tYorkshires 12\tNER 11\tNER 12\n"
            "50 Freestyle\t33.50\t31.80\t32.00\t30.50\n"
            "100 Freestyle\t1:13.00\t1:08.50\t1:10.00\t1:06.00\n"
            "
