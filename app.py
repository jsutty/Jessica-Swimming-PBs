import io
import json
import os
import re
import urllib.parse
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests
import streamlit as st

# ==============================================================================
# 1. APPLICATION & PROFILE CONFIG
# ==============================================================================
SWIMMER_NAME = "Jessica Sutcliffe"
SWIMMER_TIREF = "1749292"
SWIMMER_URL = (
    "https://www.swimmingresults.org/individualbest/personal_best.php?"
    f"back=individualbestname&mode=A&name=Sutcliffe&tiref={SWIMMER_TIREF}"
)
CLUB_LOGO_URL = "https://www.swimleeds.org.uk/wp-content/uploads/2026/02/colswc-logo-tag.svg"

DEFAULT_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1zwHlCW-r2GaSJMkIdMKp-w3yIT_qZxoHA6zFaxLdjuk/edit?usp=drivesdk"
DEFAULT_WORKSHEET_TAB = "EXPORT"
DEFAULT_WORKSHEET_GID = "839340006"

ALL_AGE_BANDS = [str(a) for a in range(10, 18)]  # ['10', '11', '12', '13', '14', '15', '16', '17']

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
PBS_FILE = os.path.join(DATA_DIR, "jessica_pbs.json")
STANDARDS_FILE = os.path.join(DATA_DIR, "standards.json")

st.set_page_config(
    page_title=f"{SWIMMER_NAME} - City of Leeds SC Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
)

# ==============================================================================
# 2. STYLING (CITY OF LEEDS SC NAVY & GOLD)
# ==============================================================================
st.markdown(
    """
    <style>
    .main { background-color: #f1f5f9; }
    .stApp header { background-color: transparent; }

    .txt-green { color: #047857; font-weight: 700; }
    .txt-amber { color: #b45309; font-weight: 700; }
    .txt-red { color: #b91c1c; font-weight: 700; }
    .txt-gray { color: #64748b; }

    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-top: 4px solid #002B49;
        border-bottom: 4px solid #FFC72C;
        border-radius: 8px;
        padding: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    
    .times-box {
        background-color: #ffffff;
        border-left: 5px solid #005A9C;
        border-top: 1px solid #e2e8f0;
        border-right: 1px solid #e2e8f0;
        border-bottom: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .matrix-box {
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 14px 16px;
    }
    .summary-card {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-top: 4px solid #002B49;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }

    div.sync-btn-container button {
        background-color: #FFC72C !important;
        color: #002B49 !important;
        font-weight: 800 !important;
        font-size: 0.98rem !important;
        border: 2px solid #002B49 !important;
        border-radius: 8px !important;
        padding: 6px 12px !important;
        box-shadow: 0 2px 4px rgba(0, 43, 73, 0.12) !important;
        transition: all 0.15s ease-in-out !important;
    }
    div.sync-btn-container button:hover {
        background-color: #ffd866 !important;
        color: #001f35 !important;
        border-color: #001f35 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 6px rgba(0, 43, 73, 0.18) !important;
    }

    div.sync-pbs-container button {
        background-color: #002B49 !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        font-size: 0.88rem !important;
        border: 2px solid #FFC72C !important;
        border-radius: 8px !important;
        padding: 5px 10px !important;
        margin-top: 4px !important;
        box-shadow: 0 2px 4px rgba(0, 43, 73, 0.12) !important;
        transition: all 0.15s ease-in-out !important;
    }
    div.sync-pbs-container button:hover {
        background-color: #00406c !important;
        color: #FFC72C !important;
        border-color: #FFC72C !important;
        transform: translateY(-1px) !important;
    }

    .donut-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 10px;
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 140px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    .donut-card-title {
        font-size: 0.78rem;
        font-weight: 700;
        color: #002B49;
        margin-bottom: 6px;
        line-height: 1.1;
    }
    .donut-card-status {
        font-size: 0.75rem;
        font-weight: 600;
        margin-top: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# 3. TIME HELPERS, NORMALIZATION & DONUT RENDERER
# ==============================================================================
def render_donut_chart(title, pace_eval):
    status, gap_text, status_class, pct = pace_eval

    if status == "No Cut":
        color = "#94a3b8"
        disp_pct = "--"
        stroke_dash = "0, 100"
        subtitle = "<span class='txt-gray'>No standard</span>"
    else:
        disp_pct = f"{int(round(pct))}%"
        stroke_dash = f"{min(pct, 100):.1f}, 100"
        if "Qualified" in status:
            color = "#047857"
            subtitle = f"<span class='txt-green'>{gap_text} (Met)</span>"
        elif "Within 1s" in status:
            color = "#d97706"
            subtitle = f"<span class='txt-amber'>{gap_text}</span>"
        else:
            color = "#dc2626"
            subtitle = f"<span class='txt-red'>{gap_text}</span>"

    svg_donut = f"""
    <div class="donut-card">
        <div class="donut-card-title">{title}</div>
        <svg viewBox="0 0 36 36" style="width: 68px; height: 68px; transform: rotate(-90deg);">
            <path stroke="#e2e8f0" stroke-width="3.8" fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            <path stroke="{color}" stroke-width="3.8" stroke-dasharray="{stroke_dash}" stroke-linecap="round" fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            <text x="18" y="20.5" text-anchor="middle"
                  style="fill: #002B49; font-weight: 800; font-size: 8.5px; transform: rotate(90deg); transform-origin: 18px 18px;">
                {disp_pct}
            </text>
        </svg>
        <div class="donut-card-status">{subtitle}</div>
    </div>
    """
    return svg_donut

def parse_time_value(val):
    if val is None or pd.isna(val):
        return None

    if isinstance(val, (int, float)):
        try:
            f = float(val)
            return f if f > 0 else None
        except (ValueError, TypeError):
            return None

    val_str = str(val).strip().replace("'", ":").replace('"', "").replace(";", ":")
    if not val_str or val_str.lower() in ["--", "-", "nt", "dq", "no cut", "nan", "none"]:
        return None

    try:
        f = float(val_str)
        return f if f > 0 else None
    except ValueError:
        pass

    parts = val_str.split(":")
    try:
        if len(parts) == 3:
            h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
            return h * 3600.0 + m * 60.0 + s
        elif len(parts) == 2:
            m, s = float(parts[0]), float(parts[1])
            return m * 60.0 + s
    except (ValueError, TypeError):
        pass

    m = re.search(r"(?:(?:(\d+):)?(\d+):)?(\d+(?:\.\d+)?)", val_str)
    if m:
        hrs, mins, secs = m.groups()
        try:
            total = float(secs)
            if mins:
                total += float(mins) * 60.0
            if hrs:
                total += float(hrs) * 3600.0
            return total if total > 0 else None
        except (ValueError, TypeError):
            return None

    return None

def format_display_time(sec):
    if sec is None or pd.isna(sec):
        return "--"
    try:
        sec = float(sec)
    except (ValueError, TypeError):
        return "--"

    mins = int(sec // 60)
    rem = sec % 60
    if mins > 0:
        return f"{mins}:{rem:05.2f}"
    return f"{rem:05.2f}"

def evaluate_pace(pb_sec, target_sec):
    if pb_sec is None or target_sec is None or pd.isna(pb_sec) or pd.isna(target_sec):
        return "No Cut", "--", "txt-gray", 0.0
    try:
        p = float(pb_sec)
        t = float(target_sec)
    except (ValueError, TypeError):
        return "No Cut", "--", "txt-gray", 0.0

    gap = p - t
    pct = min(max((t / p) * 100.0 if p > 0 else 0, 0), 100)

    if gap <= 0:
        return "Qualified 🎯", f"-{abs(gap):.2f}s", "txt-green", pct
    elif gap <= 1.0:
        return "Within 1s ⚡", f"+{gap:.2f}s", "txt-amber", pct
    else:
        return "Chasing ⏱️", f"+{gap:.2f}s", "txt-red", pct

def normalize_event_name(ev_name):
    s = str(ev_name).lower()
    s = re.sub(r"\bmeters?\b|\bm\b", "", s)
    s = re.sub(r"\bfreestyle\b|\bfree\b", "free", s)
    s = re.sub(r"\bbackstroke\b|\bback\s*stroke\b|\bback\b", "back", s)
    s = re.sub(r"\bbreaststroke\b|\bbreast\s*stroke\b|\bbreast\b", "breast", s)
    s = re.sub(r"\bbutterfly\b|\bfly\b", "fly", s)
    s = re.sub(r"\bindividual medley\b|\bim\b|\bmedley\b", "im", s)
    return re.sub(r"[^a-z0-9]", "", s)

def extract_distance_and_stroke(ev_name):
    s = str(ev_name).lower()
    dist_m = re.search(r"\d+", s)
    dist = int(dist_m.group(0)) if dist_m else None
    
    stroke = None
    if "free" in s:
        stroke = "free"
    elif "back" in s:
        stroke = "back"
    elif "breast" in s:
        stroke = "breast"
    elif "fly" in s or "butterfly" in s:
        stroke = "fly"
    elif "im" in s or "medley" in s:
        stroke = "im"
        
    return dist, stroke

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
# 4. STORAGE HELPERS
# ==============================================================================
def load_saved_pbs():
    if os.path.exists(PBS_FILE):
        try:
            with open(PBS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return pd.DataFrame(data)
        except Exception:
            pass
    return None

def save_pbs_to_disk(df):
    if df is not None and not df.empty:
        try:
            with open(PBS_FILE, "w", encoding="utf-8") as f:
                json.dump(df.to_dict(orient="records"), f, indent=2)
        except Exception:
            pass

def load_saved_standards():
    if os.path.exists(STANDARDS_FILE):
        try:
            with open(STANDARDS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                out = {}
                for k, v in raw.items():
                    parts = k.split("|||")
                    if len(parts) == 3:
                        out[(parts[0], parts[1], parts[2])] = v
                return out
        except Exception:
            pass
    return {}

def save_standards_to_disk(standards_dict):
    try:
        serializable = {
            f"{k[0]}|||{k[1]}|||{k[2]}": v
            for k, v in standards_dict.items()
        }
        with open(STANDARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
    except Exception:
        pass

# ==============================================================================
# 5. SWIM ENGLAND PARSER & DIRECT LIVE INGESTION
# ==============================================================================
def parse_swim_england_table(raw_content):
    if not raw_content or not str(raw_content).strip():
        return None

    records = []
    event_pattern = re.compile(
        r"\b(freestyle|breaststroke|backstroke|butterfly|individual medley|im|free|breast|back|fly)\b",
        re.I,
    )
    time_regex = re.compile(r"(?:\d+:)?\d{1,2}\.\d{1,2}")

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
                pb_s = parse_time_value(pb_t)
                conv_t = times[1] if len(times) > 1 else "--"
                conv_s = parse_time_value(conv_t)

                records.append({
                    "Course": c_name,
                    "Event": ev_candidate,
                    "PB_Time": format_display_time(pb_s),
                    "PB_Sec": pb_s,
                    "Conv_Label": conv_lbl,
                    "Conv_Time": format_display_time(conv_s),
                    "Conv_Sec": conv_s,
                })

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
                    pb_s = parse_time_value(pb_t)
                    conv_t = times[1] if len(times) > 1 else "--"
                    conv_s = parse_time_value(conv_t)
                    conv_lbl = "Conv to SC" if current_c == "Long Course (50m)" else "Conv to LC"

                    records.append({
                        "Course": current_c,
                        "Event": ev_cand if ev_cand else "Swim Event",
                        "PB_Time": format_display_time(pb_s),
                        "PB_Sec": pb_s,
                        "Conv_Label": conv_lbl,
                        "Conv_Time": format_display_time(conv_s),
                        "Conv_Sec": conv_s,
                    })

    if not records:
        return None
    return pd.DataFrame(records).drop_duplicates(subset=["Course", "Event", "PB_Time"])

def fetch_and_parse_swim_england_direct():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.swimmingresults.org/",
    }
    try:
        resp = requests.get(SWIMMER_URL, impersonate="chrome120", headers=headers, timeout=14)
        if resp.status_code != 200 or not resp.text.strip():
            return None, f"HTTP Error {resp.status_code} received from Swim England."

        parsed_df = parse_swim_england_table(resp.text)
        if parsed_df is not None and not parsed_df.empty:
            return parsed_df, None
        return None, "Profile page loaded, but no valid swim PB tables could be detected."
    except Exception as e:
        return None, f"Direct connection failed: {str(e)}"

# ==============================================================================
# 6. RELIABLE MULTI-TABLE FETCHER (YORKSHIRE LC + 3 OTHER MEETS)
# ==============================================================================
def fetch_google_sheet_csv(sheet_url, tab_identifier):
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not match:
        return None, "Invalid Google Sheets URL. Could not find Sheet ID."

    sheet_id = match.group(1)
    
    gid_match = re.search(r"gid=(\d+)", sheet_url + " " + str(tab_identifier))
    if gid_match:
        gid = gid_match.group(1)
    elif str(tab_identifier).isdigit():
        gid = str(tab_identifier)
    else:
        gid = DEFAULT_WORKSHEET_GID

    candidate_urls = [
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}",
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}",
    ]

    if tab_identifier and not str(tab_identifier).isdigit():
        encoded_tab = urllib.parse.quote(str(tab_identifier).strip())
        candidate_urls.extend([
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={encoded_tab}",
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&sheet={encoded_tab}",
        ])

    csv_text = None
    last_err = ""
    for url in candidate_urls:
        try:
            resp = requests.get(
                url,
                impersonate="chrome120",
                timeout=12,
                headers={"Accept": "text/csv,text/plain,*/*"},
            )
            if resp.status_code == 200 and len(resp.text.strip()) > 20 and "<!DOCTYPE" not in resp.text:
                csv_text = resp.text
                break
            else:
                last_err = f"HTTP {resp.status_code}"
        except Exception as e:
            last_err = str(e)

    if not csv_text:
        return None, f"Could not fetch tab content for gid={gid}. ({last_err})"

    raw_lines = [ln for ln in csv_text.splitlines() if ln.strip()]
    if not raw_lines:
        return None, "Worksheet appears to be completely empty."

    # Look specifically for the table header line without clipping Yorkshire LC at line 0
    header_idx = 0
    for i, line in enumerate(raw_lines[:15]):
        line_l = line.lower()
        has_age = bool(re.search(r"(?<!\d)(?:1[0-7])(?!\d)", line_l))
        has_ev = any(k in line_l for k in ["event", "stroke", "free", "comp", "50", "100", "distance"])
        if has_age and has_ev:
            header_idx = i
            break

    try:
        clean_csv = "\n".join(raw_lines[header_idx:])
        df = pd.read_csv(io.StringIO(clean_csv))
        df = df.dropna(how="all", axis=0).dropna(how="all", axis=1)
        return df, None
    except Exception as e:
        return None, f"Error parsing CSV structure: {str(e)}"

def resolve_meet_from_string(text, default_meet):
    if not text or pd.isna(text):
        return default_meet
    t = str(text).strip().lower()
    
    if "ner" in t:
        if any(k in t for k in ["sc", "winter", "25"]):
            return "NER SC (Winter)"
        elif any(k in t for k in ["lc", "50", "summer"]):
            return "NER LC"
        else:
            return "NER SC (Winter)"
    elif any(k in t for k in ["york", "yks"]):
        if any(k in t for k in ["sc", "winter", "25"]):
            return "Yorkshire SC (Winter)"
        elif any(k in t for k in ["lc", "50", "summer"]):
            return "Yorkshire LC"
        else:
            return "Yorkshire LC"
            
    return default_meet

def parse_standards_dataframe(df_raw, default_meet):
    if df_raw.empty or df_raw.shape[1] < 2:
        return 0, "Table has fewer than 2 columns."

    df = df_raw.copy()
    if df.shape[1] >= 2:
        df.iloc[:, 0] = df.iloc[:, 0].ffill()

    has_comp_col = False
    comp_col = None
    event_col = None

    for col in df.columns:
        col_c = str(col).strip().lower()
        if any(k in col_c for k in ["comp", "meet", "championship"]):
            has_comp_col = True
            comp_col = col
        elif any(k in col_c for k in ["event", "race", "stroke name", "event name"]):
            event_col = col

    if not has_comp_col and df.shape[1] >= 3:
        sample_vals = [str(x).lower() for x in df.iloc[:15, 0].dropna()]
        if any(any(k in s for k in ["ner", "york", "winter", "lc", "sc"]) for s in sample_vals):
            has_comp_col = True
            comp_col = df.columns[0]
            event_col = df.columns[1]

    if not event_col:
        event_col = df.columns[1] if has_comp_col else df.columns[0]

    detected_age_cols = []
    mapped_ages = set()

    for col in df.columns:
        if col in [comp_col, event_col]:
            continue
        c_str = str(col).strip().lower()

        for target_age in range(10, 18):
            age_str = str(target_age)
            if age_str in mapped_ages:
                continue
            
            if target_age == 17:
                is_match = bool(re.search(r"(?<!\d)17(?!\d)", c_str)) or any(k in c_str for k in ["17+", "17/ov", "17 & over", "17 & ov", "17+yrs"])
            else:
                if any(bad in c_str for bad in ["17", "18", "19", "over", "ov", "+"]) and target_age < 17:
                    continue
                is_match = bool(re.search(rf"(?<!\d){target_age}(?!\d)", c_str))

            if is_match:
                detected_age_cols.append((col, age_str))
                mapped_ages.add(age_str)
                break

    if not detected_age_cols:
        return 0, f"Could not detect any Age columns (10-17). Found headers: {list(df.columns)}"

    saved_count = 0
    current_meet = default_meet

    for _, row in df.iterrows():
        if has_comp_col and pd.notna(row[comp_col]) and str(row[comp_col]).strip():
            current_meet = resolve_meet_from_string(row[comp_col], default_meet)

        raw_ev = str(row[event_col]).strip()
        raw_ev_lower = raw_ev.lower()
        if not raw_ev or raw_ev_lower in ["event", "stroke", "qualifying", "consideration", "events"]:
            continue

        clean_ev = normalize_event_name(raw_ev)

        for col_name, age_band in detected_age_cols:
            val_raw = row[col_name]
            sec = parse_time_value(val_raw)
            if sec is None:
                continue

            disp_str = format_display_time(sec)
            key = (current_meet, age_band, clean_ev)
            st.session_state.standards_db[key] = {"time": disp_str, "sec": sec}
            saved_count += 1

    mapped_labels = [f"Age {a}: '{c}'" for c, a in detected_age_cols]
    return saved_count, f"Mapped: " + " | ".join(mapped_labels)

# ==============================================================================
# 7. UNIFIED AUTO-SYNC & INITIALIZATION
# ==============================================================================
if "swimmer_df" not in st.session_state:
    st.session_state.swimmer_df = load_saved_pbs()

if "standards_db" not in st.session_state:
    st.session_state.standards_db = load_saved_standards()

if "competitor_name" not in st.session_state:
    st.session_state.competitor_name = "Competitor"

if "competitor_df" not in st.session_state:
    st.session_state.competitor_df = None

def perform_manual_sync():
    df_s, err_s = fetch_google_sheet_csv(DEFAULT_GSHEET_URL, DEFAULT_WORKSHEET_GID)
    if err_s:
        return False, f"Failed: {err_s}"
    # Complete reset to prevent cross-table corruption
    st.session_state.standards_db = {}
    count, msg = parse_standards_dataframe(df_s, "Yorkshire LC")
    if count > 0:
        save_standards_to_disk(st.session_state.standards_db)
        return True, f"Synchronized {count} standards across all 4 meets! ({msg})"
    return False, msg

# Run clean sync automatically on initial startup
if "auto_synced" not in st.session_state:
    perform_manual_sync()
    st.session_state.auto_synced = True

def lookup_standard(meet, age, event_name):
    clean_ev = normalize_event_name(event_name)
    key = (meet, str(age), clean_ev)
    if key in st.session_state.standards_db:
        return st.session_state.standards_db[key]["time"], st.session_state.standards_db[key]["sec"]

    req_dist, req_stroke = extract_distance_and_stroke(event_name)
    if req_dist and req_stroke:
        for (m, a, e), data in st.session_state.standards_db.items():
            if m == meet and str(a) == str(age):
                cand_dist, cand_stroke = extract_distance_and_stroke(e)
                if cand_dist == req_dist and cand_stroke == req_stroke:
                    return data["time"], data["sec"]

    for (m, a, e), data in st.session_state.standards_db.items():
        if m == meet and str(a) == str(age) and (e == clean_ev or e == str(event_name).lower()):
            return data["time"], data["sec"]

    return None, None

# ==============================================================================
# 8. CITY OF LEEDS SC HEADER WITH STACKED SYNC BUTTONS
# ==============================================================================
banner_left, banner_mid, banner_right = st.columns([5, 2.4, 2])

with banner_left:
    st.markdown(
        f"""
        <div style="padding-top: 4px;">
            <h1 style="color: #002B49; margin-bottom: 2px; font-weight: 800; font-size: 2.1rem;">
                🏊‍♀️ {SWIMMER_NAME}
            </h1>
            <p style="color: #475569; font-size: 1.02rem; margin: 0;">
                <strong style="color: #005A9C;">City of Leeds Swimming Club</strong> &bull; 
                Swim England: <code style="background-color: #e2e8f0; padding: 2px 6px; border-radius: 4px;">{SWIMMER_TIREF}</code> &bull; 
                <a href="{SWIMMER_URL}" target="_blank" style="color: #005A9C; font-weight: 600;">Rankings Profile ↗</a>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with banner_mid:
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    
    st.markdown('<div class="sync-btn-container">', unsafe_allow_html=True)
    if st.button("⚡ Sync QTs", use_container_width=True, help="Fetch latest qualifying times directly from Google Sheets"):
        with st.spinner("Syncing qualifying times..."):
            ok, res_msg = perform_manual_sync()
            if ok:
                st.toast("✅ Qualifying times synchronized successfully!")
                st.rerun()
            else:
                st.error(res_msg)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sync-pbs-container">', unsafe_allow_html=True)
    if st.button("🏊‍♀️ Sync PBs from Swim England", use_container_width=True, help="Directly pulls official PBs from Jessica's Swim England profile"):
        with st.spinner("Fetching PBs directly from Swim England rankings..."):
            direct_df, direct_err = fetch_and_parse_swim_england_direct()
            if direct_df is not None and not direct_df.empty:
                st.session_state.swimmer_df = direct_df
                save_pbs_to_disk(direct_df)
                st.toast(f"✅ Successfully refreshed {len(direct_df)} PBs from Swim England!")
                st.rerun()
            else:
                st.error(f"Live rankings pull failed: {direct_err}")
                st.info("Tip: You can always use the Step 1 expander below to paste the table directly if Swim England is blocking automated requests.")
    st.markdown('</div>', unsafe_allow_html=True)

with banner_right:
    st.image(CLUB_LOGO_URL, width=170)

st.markdown("<hr style='border: none; border-top: 3px solid #FFC72C; margin: 10px 0 20px 0;'>", unsafe_allow_html=True)

# ==============================================================================
# 9. INGESTION WORKFLOW
# ==============================================================================
with st.expander("📥 Step 1: Update Jessica's Times from Rankings", expanded=(st.session_state.swimmer_df is None)):
    st.write("1. Open Jessica's Swim England profile using the link above.")
    st.write("2. Select all content from the page table, copy it, and paste it below:")
    raw_input = st.text_area("Paste table content here:", height=110, placeholder="Paste Swim England table text or HTML...")
    if st.button("🚀 Process & Store Times", use_container_width=True):
        parsed = parse_swim_england_table(raw_content=raw_input)
        if parsed is not None and not parsed.empty:
            st.session_state.swimmer_df = parsed
            save_pbs_to_disk(parsed)
            st.success(f"Successfully captured and saved {len(parsed)} swim times!")
            st.rerun()
        else:
            st.error("No valid times found. Please check that table rows were included.")

if st.session_state.swimmer_df is None:
    st.info("Paste and process Jessica's table above or tap 'Sync PBs from Swim England' to load the tracking dashboard.")
    st.stop()

df = st.session_state.swimmer_df

# ==============================================================================
# 10. CONFIGURE COMPETITION QUALIFYING TIMES (EXPANDER)
# ==============================================================================
with st.expander("⚙️ Configure Competition Qualifying Times", expanded=False):
    tab_gsheet, tab_paste, tab_single = st.tabs(["🌐 Live Google Sheet Link", "📋 Paste Cells", "✏️ Single Event Entry"])

    with tab_gsheet:
        st.caption("Qualifying times sync automatically when the app loads, or whenever you tap the 'Sync QTs' button above.")
        c_url, c_tab = st.columns([2, 1])
        with c_url:
            gsheet_raw_url = st.text_input("Google Sheet Link", value=f"{DEFAULT_GSHEET_URL}#gid={DEFAULT_WORKSHEET_GID}")
        with c_tab:
            worksheet_tab_name = st.text_input("Worksheet Tab Name / gid", value=DEFAULT_WORKSHEET_GID)

        sheet_meet = st.selectbox("Default Meet (if unlisted):", ["Yorkshire LC", "Yorkshire SC (Winter)", "NER LC", "NER SC (Winter)"], key="gsheet_meet")

        c_sync1, c_sync2 = st.columns([1, 1])
        with c_sync1:
            sync_btn = st.button("🔄 Force Refresh Standards Now", use_container_width=True)
        with c_sync2:
            debug_btn = st.button("🔍 Check Connection & Preview Data", use_container_width=True)

        if sync_btn or debug_btn:
            with st.spinner(f"Connecting to Google Sheets (gid={worksheet_tab_name})..."):
                df_sheet, err = fetch_google_sheet_csv(gsheet_raw_url, worksheet_tab_name)
                if err:
                    st.error(f"Failed to fetch sheet: {err}")
                else:
                    st.success("Successfully reached Google Sheet!")
                    st.write("**Detected Columns:**", list(df_sheet.columns))
                    with st.expander("View Raw Google Sheet Rows (First 5 Rows)", expanded=True):
                        st.dataframe(df_sheet.head(5), use_container_width=True)

                    if sync_btn:
                        st.session_state.standards_db = {}
                        count, msg = parse_standards_dataframe(df_sheet, sheet_meet)
                        if count > 0:
                            save_standards_to_disk(st.session_state.standards_db)
                            st.success(f"Loaded and saved {count} standards! ({msg})")
                            st.rerun()
                        else:
                            st.error(msg)

    with tab_paste:
        tsv_paste = st.text_area("Paste cells here (tab or comma separated):", height=110)
        paste_meet = st.selectbox("Default Meet for pasted block:", ["Yorkshire LC", "Yorkshire SC (Winter)", "NER LC", "NER SC (Winter)"], key="paste_meet")
        if st.button("📥 Import Pasted Standards", use_container_width=True):
            sep = "\t" if "\t" in tsv_paste else ","
            try:
                df_paste = pd.read_csv(io.StringIO(tsv_paste.strip()), sep=sep)
                count, parse_err = parse_standards_dataframe(df_paste, paste_meet)
                if count > 0:
                    save_standards_to_disk(st.session_state.standards_db)
                    st.success(f"Loaded and saved {count} standards!")
                    st.rerun()
                else:
                    st.error(parse_err)
            except Exception as e:
                st.error(f"Error parsing table: {e}")

    with tab_single:
        all_evs = sorted(df["Event"].unique().tolist(), key=gala_order_key)
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            s_ev = st.selectbox("Event", all_evs)
        with col_s2:
            s_meet = st.selectbox("Meet", ["Yorkshire LC", "Yorkshire SC (Winter)", "NER LC", "NER SC (Winter)"])
            s_age = st.selectbox("Age Band", ALL_AGE_BANDS, index=1)
        with col_s3:
            s_val = st.text_input("Target Cut (e.g. 12.3, 33.80, or 1:08.20)")
            if st.button("💾 Save Standard", use_container_width=True):
                sec = parse_time_value(s_val)
                if sec:
                    clean_k = normalize_event_name(s_ev)
                    disp_str = format_display_time(sec)
                    st.session_state.standards_db[(s_meet, s_age, clean_k)] = {"time": disp_str, "sec": sec}
                    save_standards_to_disk(st.session_state.standards_db)
                    st.success(f"Saved {s_meet} Age {s_age} target for {s_ev} as {disp_str}!")
                    st.rerun()

    with st.expander("📊 View Currently Saved Standards in Memory", expanded=False):
        if st.session_state.standards_db:
            db_list = [
                {"Meet": k[0], "Age": k[1], "Event Key": k[2], "Validated Time": v["time"], "Seconds": v["sec"]}
                for k, v in st.session_state.standards_db.items()
            ]
            st.dataframe(pd.DataFrame(db_list), use_container_width=True)
            if st.button("🗑️ Clear Stored Standards (Reset)"):
                st.session_state.standards_db = {}
                save_standards_to_disk({})
                st.rerun()
        else:
            st.info("No standards currently saved in app memory.")

unique_events = sorted(df["Event"].unique().tolist(), key=gala_order_key)

def get_best_eligible_times(ev):
    ev_rows = df[df["Event"] == ev]
    lc_sub = ev_rows[ev_rows["Course"] == "Long Course (50m)"]
    sc_sub = ev_rows[ev_rows["Course"] == "Short Course (25m)"]

    lc_pb_sec = lc_sub.iloc[0]["PB_Sec"] if not lc_sub.empty else None
    sc_conv_lc_sec = sc_sub.iloc[0]["Conv_Sec"] if not sc_sub.empty else None
    lc_candidates = [s for s in [lc_pb_sec, sc_conv_lc_sec] if s is not None]
    best_lc_sec = min(lc_candidates) if lc_candidates else None

    sc_pb_sec = sc_sub.iloc[0]["PB_Sec"] if not sc_sub.empty else None
    lc_conv_sc_sec = lc_sub.iloc[0]["Conv_Sec"] if not lc_sub.empty else None
    sc_candidates = [s for s in [sc_pb_sec, lc_conv_sc_sec] if s is not None]
    best_sc_sec = min(sc_candidates) if sc_candidates else None

    return best_lc_sec, best_sc_sec

# ==============================================================================
# 11. APPLICATION NAVIGATION TABS
# ==============================================================================
main_tab_events, main_tab_summary, main_tab_h2h = st.tabs([
    "📊 Event-by-Event Tracker",
    "🏆 Championship Summary & Tracker",
    "⚔️ Swimmer Head-to-Head"
])

# ------------------------------------------------------------------------------
# TAB 1: DETAILED EVENT CARDS
# ------------------------------------------------------------------------------
with main_tab_events:
    f_col1, f_col2 = st.columns([1, 2])
    with f_col1:
        active_age = st.selectbox(
            "🎯 **Active Target Age Category:**",
            ALL_AGE_BANDS,
            index=1,
            key="age_events_dropdown",
            help="Select any competition age band between 10 and 17"
        )
    with f_col2:
        selected_stroke = st.radio(
            "🏊 **Filter by Stroke:**",
            ["All Events", "Freestyle", "Backstroke", "Breaststroke", "Butterfly", "Individual Medley"],
            horizontal=True,
            key="stroke_filter_tab"
        )

    num_yks_lc = 0
    num_ner_lc = 0
    num_yks_sc = 0
    num_ner_sc = 0

    for ev in unique_events:
        best_lc_sec, best_sc_sec = get_best_eligible_times(ev)

        _, y_lc_s = lookup_standard("Yorkshire LC", active_age, ev)
        if y_lc_s is not None and best_lc_sec is not None and best_lc_sec <= y_lc_s:
            num_yks_lc += 1

        _, n_lc_s = lookup_standard("NER LC", active_age, ev)
        if n_lc_s is not None and best_lc_sec is not None and best_lc_sec <= n_lc_s:
            num_ner_lc += 1

        _, y_sc_s = lookup_standard("Yorkshire SC (Winter)", active_age, ev)
        if y_sc_s is not None and best_sc_sec is not None and best_sc_sec <= y_sc_s:
            num_yks_sc += 1

        _, n_sc_s = lookup_standard("NER SC (Winter)", active_age, ev)
        if n_sc_s is not None and best_sc_sec is not None and best_sc_sec <= n_sc_s:
            num_ner_sc += 1

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("No. of Yorkshires (LC)", num_yks_lc)
    m2.metric("No. of NERs (LC)", num_ner_lc)
    m3.metric("No. of Winter Yorkshires (SC)", num_yks_sc)
    m4.metric("No. of Winter NERs (SC)", num_ner_sc)

    st.markdown("---")

    for ev in unique_events:
        if selected_stroke != "All Events" and selected_stroke.lower() not in ev.lower():
            continue

        ev_rows = df[df["Event"] == ev]
        lc_sub = ev_rows[ev_rows["Course"] == "Long Course (50m)"]
        sc_sub = ev_rows[ev_rows["Course"] == "Short Course (25m)"]

        best_lc_sec, best_sc_sec = get_best_eligible_times(ev)

        yks_lc_t, yks_lc_s = lookup_standard("Yorkshire LC", active_age, ev)
        yks_sc_t, yks_sc_s = lookup_standard("Yorkshire SC (Winter)", active_age, ev)
        ner_lc_t, ner_lc_s = lookup_standard("NER LC", active_age, ev)
        ner_sc_t, ner_sc_s = lookup_standard("NER SC (Winter)", active_age, ev)

        eval_yks_lc = evaluate_pace(best_lc_sec, yks_lc_s)
        eval_yks_sc = evaluate_pace(best_sc_sec, yks_sc_s)
        eval_ner_lc = evaluate_pace(best_lc_sec, ner_lc_s)
        eval_ner_sc = evaluate_pace(best_sc_sec, ner_sc_s)

        with st.container():
            st.subheader(f"🏊 {ev}")

            card_left, card_right = st.columns([1, 1])

            with card_left:
                st.markdown('<div class="times-box">', unsafe_allow_html=True)
                if not lc_sub.empty:
                    lc_r = lc_sub.iloc[0]
                    st.markdown(f"**🏊‍♂️ LC PB:** `{lc_r['PB_Time']}` &nbsp;|&nbsp; Conv SC: `{lc_r['Conv_Time']}`")
                else:
                    st.markdown("**🏊‍♂️️ LC PB:** *No official LC PB recorded*")

                if not sc_sub.empty:
                    sc_r = sc_sub.iloc[0]
                    st.markdown(f"**🏊‍♀️ SC PB:** `{sc_r['PB_Time']}` &nbsp;|&nbsp; Conv LC: `{sc_r['Conv_Time']}`")
                else:
                    st.markdown("**🏊‍♀️ SC PB:** *No official SC PB recorded*")

                st.caption(
                    f"Reference Times &bull; Best LC Eligible: **`{format_display_time(best_lc_sec)}`** &bull; "
                    f"Best SC Eligible: **`{format_display_time(best_sc_sec)}`**"
                )
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="matrix-box">', unsafe_allow_html=True)
                st.markdown(
                    f"**Yorkshire LC (Age {active_age}):** `{yks_lc_t or '--'}` &rarr; "
                    f"<span class='{eval_yks_lc[2]}'>{eval_yks_lc[1]} ({eval_yks_lc[0]})</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**Yorkshire SC Winter (Age {active_age}):** `{yks_sc_t or '--'}` &rarr; "
                    f"<span class='{eval_yks_sc[2]}'>{eval_yks_sc[1]} ({eval_yks_sc[0]})</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**NER LC (Age {active_age}):** `{ner_lc_t or '--'}` &rarr; "
                    f"<span class='{eval_ner_lc[2]}'>{eval_ner_lc[1]} ({eval_ner_lc[0]})</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**NER SC Winter (Age {active_age}):** `{ner_sc_t or '--'}` &rarr; "
                    f"<span class='{eval_ner_sc[2]}'>{eval_ner_sc[1]} ({eval_ner_sc[0]})</span>",
                    unsafe_allow_html=True,
                )
                st.markdown('</div>', unsafe_allow_html=True)

            with card_right:
                st.write(f"**Championship Completion (Age {active_age})**")
                
                gauge_r1_c1, gauge_r1_c2 = st.columns(2)
                with gauge_r1_c1:
                    st.markdown(render_donut_chart("Yorkshire LC", eval_yks_lc), unsafe_allow_html=True)
                with gauge_r1_c2:
                    st.markdown(render_donut_chart("Yorkshire SC Winter", eval_yks_sc), unsafe_allow_html=True)

                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

                gauge_r2_c1, gauge_r2_c2 = st.columns(2)
                with gauge_r2_c1:
                    st.markdown(render_donut_chart("NER LC", eval_ner_lc), unsafe_allow_html=True)
                with gauge_r2_c2:
                    st.markdown(render_donut_chart("NER SC Winter", eval_ner_sc), unsafe_allow_html=True)

            st.markdown("<hr style='margin: 1.5rem 0;'>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# TAB 2: CHAMPIONSHIP SUMMARY & TARGET PLANNER
# ------------------------------------------------------------------------------
with main_tab_summary:
    sum_col1, sum_col2 = st.columns([1, 3])
    with sum_col1:
        summary_age = st.selectbox(
            "🎯 **Target Age Category:**",
            ALL_AGE_BANDS,
            index=1,
            key="age_summary_dropdown",
            help="Select any competition age band between 10 and 17"
        )
    with sum_col2:
        st.info(f"Viewing all qualifications, close targets (<1s), and chasing events for **Age {summary_age}**.")

    meets_list = [
        {"title": "Yorkshire Long Course (LC)", "key": "Yorkshire LC", "course": "LC", "emoji": "🥇"},
        {"title": "Yorkshire Short Course (Winter)", "key": "Yorkshire SC (Winter)", "course": "SC", "emoji": "❄️"},
        {"title": "North East Region (NER) Long Course", "key": "NER LC", "course": "LC", "emoji": "🏊‍♂️"},
        {"title": "North East Region (NER) Short Course (Winter)", "key": "NER SC (Winter)", "course": "SC", "emoji": "🏆"},
    ]

    for m_info in meets_list:
        m_title = m_info["title"]
        m_key = m_info["key"]
        is_lc = (m_info["course"] == "LC")

        qual_events = []
        close_events = []
        chasing_events = []

        for ev in unique_events:
            best_lc_sec, best_sc_sec = get_best_eligible_times(ev)
            ref_sec = best_lc_sec if is_lc else best_sc_sec

            cut_str, cut_sec = lookup_standard(m_key, summary_age, ev)
            if cut_sec is None or ref_sec is None:
                continue

            status, gap_str, badge_cls, _ = evaluate_pace(ref_sec, cut_sec)

            record = {
                "Event": ev,
                "PB Time": format_display_time(ref_sec),
                "Qualifying Cut": cut_str,
                "Gap": gap_str,
                "Badge": badge_cls,
                "Sort": gala_order_key(ev),
            }

            if "Qualified" in status:
                qual_events.append(record)
            elif "Within 1s" in status:
                close_events.append(record)
            else:
                chasing_events.append(record)

        qual_events.sort(key=lambda x: x["Sort"])
        close_events.sort(key=lambda x: x["Sort"])
        chasing_events.sort(key=lambda x: x["Sort"])

        total_configured = len(qual_events) + len(close_events) + len(chasing_events)

        st.markdown(f'<div class="summary-card">', unsafe_allow_html=True)
        st.subheader(f"{m_info['emoji']} {m_title} (Age {summary_age})")

        c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
        c_kpi1.metric("Qualified 🎯", len(qual_events))
        c_kpi2.metric("Within 1s ⚡", len(close_events))
        c_kpi3.metric("Chasing ⏱️", len(chasing_events))
        c_kpi4.metric("Standards Set", total_configured)

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        if total_configured == 0:
            st.caption(f"No qualifying standards currently configured for {m_key} (Age {summary_age}).")
        else:
            col_q, col_w, col_c = st.columns(3)

            with col_q:
                st.markdown(f"**🎯 Qualified ({len(qual_events)})**")
                if qual_events:
                    for item in qual_events:
                        st.markdown(
                            f"&bull; **{item['Event']}**: `{item['PB Time']}` &nbsp;"
                            f"<span class='txt-green'>({item['Gap']} under {item['Qualifying Cut']})</span>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No events qualified yet.")

            with col_w:
                st.markdown(f"**⚡ Within 1.0s ({len(close_events)})**")
                if close_events:
                    for item in close_events:
                        st.markdown(
                            f"&bull; **{item['Event']}**: `{item['PB Time']}` &nbsp;"
                            f"<span class='txt-amber'>({item['Gap']} from {item['Qualifying Cut']})</span>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No events currently within 1.0s.")

            with col_c:
                st.markdown(f"**⏱️ Chasing ({len(chasing_events)})**")
                if chasing_events:
                    for item in chasing_events:
                        st.markdown(
                            f"&bull; **{item['Event']}**: `{item['PB Time']}` &nbsp;"
                            f"<span class='txt-red'>({item['Gap']} from {item['Qualifying Cut']})</span>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No other events in progress.")

        st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# TAB 3: SWIMMER HEAD-TO-HEAD COMPARISON (WITH HIGHLIGHTED FASTEST TIME)
# ------------------------------------------------------------------------------
with main_tab_h2h:
    st.markdown("### ⚔️ Compare Personal Bests Side-by-Side")
    st.write(
        "Enter a competitor or teammate's name, paste their Swim England rankings table, "
        "and compare Jessica's official personal bests directly."
    )

    with st.expander("📥 Load Competitor Swim England Profile Data", expanded=(st.session_state.competitor_df is None)):
        comp_name_input = st.text_input("Competitor / Swimmer Name:", value=st.session_state.competitor_name)
        comp_raw_text = st.text_area(
            "Paste Competitor Swim England table text or HTML here:",
            height=120,
            placeholder="Paste table copied from Swim England rankings profile..."
        )
        if st.button("🚀 Load & Compare Swimmer", use_container_width=True):
            if comp_name_input.strip():
                st.session_state.competitor_name = comp_name_input.strip()
            parsed_comp = parse_swim_england_table(comp_raw_text)
            if parsed_comp is not None and not parsed_comp.empty:
                st.session_state.competitor_df = parsed_comp
                st.success(f"Successfully loaded {len(parsed_comp)} PBs for {st.session_state.competitor_name}!")
                st.rerun()
            else:
                st.error("Could not parse swimmer times. Verify you copied the table rows directly from Swim England.")

    comp_df = st.session_state.competitor_df
    comp_name = st.session_state.competitor_name

    if comp_df is None:
        st.info("Paste a swimmer's profile table above to generate the side-by-side comparison.")
    else:
        filter_col1, filter_col2 = st.columns([1, 2])
        with filter_col1:
            course_filter = st.radio(
                "🏊 **Filter Course:**",
                ["All Courses", "Short Course (25m)", "Long Course (50m)"],
                horizontal=True,
                key="h2h_course_filter"
            )
        with filter_col2:
            st.caption(f"Comparing **Jessica Sutcliffe** vs. **{comp_name}**.")

        courses_to_include = (
            ["Short Course (25m)", "Long Course (50m)"]
            if course_filter == "All Courses"
            else [course_filter]
        )

        comparison_rows = []
        jessica_faster = 0
        comp_faster = 0
        tied = 0

        all_unique_evs = sorted(
            list(set(df["Event"].unique().tolist() + comp_df["Event"].unique().tolist())),
            key=gala_order_key
        )

        for ev in all_unique_evs:
            for crs in courses_to_include:
                j_sub = df[(df["Event"] == ev) & (df["Course"] == crs)]
                c_sub = comp_df[(comp_df["Event"] == ev) & (comp_df["Course"] == crs)]

                if j_sub.empty and c_sub.empty:
                    continue

                j_sec = j_sub.iloc[0]["PB_Sec"] if not j_sub.empty else None
                j_time_str = j_sub.iloc[0]["PB_Time"] if not j_sub.empty else "--"

                c_sec = c_sub.iloc[0]["PB_Sec"] if not c_sub.empty else None
                c_time_str = c_sub.iloc[0]["PB_Time"] if not c_sub.empty else "--"

                fastest_swimmer = None
                if j_sec is not None and c_sec is not None:
                    diff = j_sec - c_sec
                    if abs(diff) < 0.001:
                        lead = "Tied 🤝"
                        tied += 1
                        fastest_swimmer = "Tied"
                    elif diff < 0:
                        lead = f"Jessica by -{abs(diff):.2f}s 🎯"
                        jessica_faster += 1
                        fastest_swimmer = "Jessica"
                    else:
                        lead = f"{comp_name} by -{diff:.2f}s"
                        comp_faster += 1
                        fastest_swimmer = "Competitor"
                elif j_sec is not None:
                    lead = "Jessica only"
                    fastest_swimmer = "Jessica"
                else:
                    lead = f"{comp_name} only"
                    fastest_swimmer = "Competitor"

                crs_label = "SC (25m)" if crs == "Short Course (25m)" else "LC (50m)"
                comparison_rows.append({
                    "Event": f"{ev} ({crs_label})" if course_filter == "All Courses" else ev,
                    "Course": crs_label,
                    f"Jessica PB": j_time_str,
                    f"{comp_name} PB": c_time_str,
                    "Advantage": lead,
                    "_fastest": fastest_swimmer,
                    "Sort": gala_order_key(ev),
                })

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Total Events Compared", len(comparison_rows))
        h2.metric("Jessica Ahead 🏊‍♀️", jessica_faster)
        h3.metric(f"{comp_name} Ahead", comp_faster)
        h4.metric("Tied", tied)

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        if comparison_rows:
            comp_display_df = pd.DataFrame(comparison_rows)
            comp_display_df = comp_display_df.sort_values(by="Sort").drop(columns=["Sort"])

            j_col = "Jessica PB"
            c_col = f"{comp_name} PB"

            # Apply bold dark-blue highlighting to fastest swimmer's time cell
            def highlight_fastest_time(row):
                winner = row["_fastest"]
                style_j = ""
                style_c = ""
                highlight_css = "font-weight: 800; color: #002B49; background-color: #E8F0FE;"

                if winner == "Jessica" and row[j_col] != "--":
                    style_j = highlight_css
                elif winner == "Competitor" and row[c_col] != "--":
                    style_c = highlight_css
                elif winner == "Tied":
                    style_j = highlight_css
                    style_c = highlight_css

                res = ["" for _ in row.index]
                if j_col in row.index:
                    res[row.index.get_loc(j_col)] = style_j
                if c_col in row.index:
                    res[row.index.get_loc(c_col)] = style_c
                return res

            styled_table = (
                comp_display_df.style
                .apply(highlight_fastest_time, axis=1)
                .hide(subset=["_fastest"], axis="columns")
            )

            if course_filter != "All Courses" and "Course" in comp_display_df.columns:
                styled_table = styled_table.hide(subset=["Course"], axis="columns")

            st.dataframe(styled_table, use_container_width=True, hide_index=True)
        else:
            st.info("No common events found for the selected course filter.")

# ==============================================================================
# 12. TABULAR VIEW OF ALL SWIMS
# ==============================================================================
with st.expander(f"📋 Full Table View of All Swims & Standards (Active Age: {active_age})"):
    summary_rows = []
    for ev in unique_events:
        best_lc_sec, best_sc_sec = get_best_eligible_times(ev)
        y_lc_t, y_lc_s = lookup_standard("Yorkshire LC", active_age, ev)
        y_sc_t, y_sc_s = lookup_standard("Yorkshire SC (Winter)", active_age, ev)
        n_lc_t, n_lc_s = lookup_standard("NER LC", active_age, ev)
        n_sc_t, n_sc_s = lookup_standard("NER SC (Winter)", active_age, ev)

        ev_y_lc = evaluate_pace(best_lc_sec, y_lc_s)
        ev_y_sc = evaluate_pace(best_sc_sec, y_sc_s)
        ev_n_lc = evaluate_pace(best_lc_sec, n_lc_s)
        ev_n_sc = evaluate_pace(best_sc_sec, n_sc_s)

        summary_rows.append({
            "Event": ev,
            "Best LC Eligible": format_display_time(best_lc_sec),
            f"Yorkshire LC ({active_age})": y_lc_t or "--",
            "YKS LC Status": ev_y_lc[0],
            "YKS LC Gap": ev_y_lc[1],
            "Best SC Eligible": format_display_time(best_sc_sec),
            f"Yorkshire SC ({active_age})": y_sc_t or "--",
            "YKS SC Status": ev_y_sc[0],
            f"NER LC ({active_age})": n_lc_t or "--",
            "NER LC Status": ev_n_lc[0],
            f"NER SC ({active_age})": n_sc_t or "--",
            "NER SC Status": ev_n_sc[0],
        })

    view_df = pd.DataFrame(summary_rows)
    view_df["sort"] = view_df["Event"].apply(gala_order_key)
    view_df = view_df.sort_values(by="sort").drop(columns=["sort"])
    st.dataframe(view_df, use_container_width=True, hide_index=True)
