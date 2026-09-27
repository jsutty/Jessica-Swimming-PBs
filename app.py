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
CLUB_LOGO_URL = "https://www.swimleeds.org.uk/wp-content/uploads/2021/04/City-of-Leeds-Swimming-Club-Logo.png"

DEFAULT_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1zwHlCW-r2GaSJMkIdMKp-w3yIT_qZxoHA6zFaxLdjuk/edit?usp=drivesdk"
DEFAULT_WORKSHEET_TAB = "EXPORT"
DEFAULT_WORKSHEET_GID = "839340006"

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
PBS_FILE = os.path.join(DATA_DIR, "jessica_pbs.json")
STANDARDS_FILE = os.path.join(DATA_DIR, "standards.json")

st.set_page_config(
    page_title=f"{SWIMMER_NAME} - City of Leeds SC Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
)

# ==============================================================================
# 2. STYLING (CITY OF LEEDS PALETTE & STATUS COLORS)
# ==============================================================================
st.markdown(
    """
    <style>
    .main { background-color: #f6f8fb; }
    .stApp header { background-color: transparent; }
    .txt-green { color: #0f5132; font-weight: 700; }
    .txt-amber { color: #d97706; font-weight: 700; }
    .txt-red { color: #dc2626; font-weight: 700; }
    .txt-gray { color: #6b7280; }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #dce3ed;
        border-bottom: 4px solid #FFC72C;
        border-radius: 8px;
        padding: 12px;
    }
    .times-box {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .matrix-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# 3. ROBUST TIME VALIDATION & NORMALIZATION
# ==============================================================================
def parse_time_value(val):
    """
    Parses any text or duration format into total float seconds:
    - hh:mm:ss.ff (e.g. '00:00:33.80' or '00:01:14.20')
    - mm:ss.ff (e.g. '1:14.20')
    - ss.ff (e.g. '33.80' or '33.8')
    Returns total float seconds, or None if invalid.
    """
    if val is None or pd.isna(val):
        return None
    val_str = str(val).strip().replace("'", ":").replace('"', "").replace(";", ":")
    if not val_str or val_str in ["--", "-", "nt", "dq", "no cut"]:
        return None

    # Format 1: hh:mm:ss.ff or hh:mm:ss
    hms = re.match(r"^(\d{1,2}):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$", val_str)
    if hms:
        hours, mins, secs = hms.groups()
        try:
            return float(hours) * 3600.0 + float(mins) * 60.0 + float(secs)
        except ValueError:
            pass

    # Format 2: mm:ss.ff or mm:ss
    ms = re.match(r"^(\d{1,2}):(\d{1,2}(?:\.\d+)?)$", val_str)
    if ms:
        mins, secs = ms.groups()
        try:
            return float(mins) * 60.0 + float(secs)
        except ValueError:
            pass

    # Format 3: pure seconds (ss.ff or ss)
    s_only = re.match(r"^(\d+(?:\.\d+)?)$", val_str)
    if s_only:
        try:
            return float(s_only.group(1))
        except ValueError:
            pass

    # Fallback search extraction
    match = re.search(r"(?:(?:(\d+):)?(\d+):)?(\d+(?:\.\d+)?)", val_str)
    if match:
        h, m, s = match.groups()
        try:
            total = float(s)
            if m:
                total += float(m) * 60.0
            if h:
                total += float(h) * 3600.0
            return total
        except (ValueError, TypeError):
            return None

    return None

def format_display_time(sec):
    """Formats float seconds into standard swimming time format (e.g. '33.80' or '1:14.20')."""
    if sec is None or pd.isna(sec):
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
    s = re.sub(r"\bfreestyle\b", "free", s)
    s = re.sub(r"\bbackstroke\b", "back", s)
    s = re.sub(r"\bbreaststroke\b", "breast", s)
    s = re.sub(r"\bbutterfly\b", "fly", s)
    s = re.sub(r"\bindividual medley\b", "im", s)
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
# 5. SWIM ENGLAND PARSER
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

# ==============================================================================
# 6. GOOGLE SHEETS FETCHER & TIME VALIDATING PARSER
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

    header_idx = 0
    for i, line in enumerate(raw_lines[:15]):
        line_l = line.lower()
        has_11 = bool(re.search(r"(?<!\d)11(?!\d)", line_l))
        has_ev = any(k in line_l for k in ["event", "stroke", "50", "100", "free", "comp"])
        if has_11 and has_ev:
            header_idx = i
            break
        elif has_ev and i > 0 and header_idx == 0:
            header_idx = i

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
        elif any(k in col_c for k in ["event", "stroke", "race"]):
            event_col = col

    if not has_comp_col and df.shape[1] >= 3:
        sample_vals = [str(x).lower() for x in df.iloc[:10, 0].dropna()]
        if any(any(k in s for k in ["ner", "york", "winter", "lc", "sc"]) for s in sample_vals):
            has_comp_col = True
            comp_col = df.columns[0]
            event_col = df.columns[1]

    if not event_col:
        event_col = df.columns[1] if has_comp_col else df.columns[0]

    col_age_11 = None
    col_age_12 = None

    for col in df.columns:
        if col in [comp_col, event_col]:
            continue
        c_str = str(col).strip().lower()

        if any(k in c_str for k in ["17", "18", "19", "over", "ov", "+"]):
            continue

        if re.search(r"(?<!\d)11(?!\d)", c_str):
            col_age_11 = col
        elif re.search(r"(?<!\d)12(?!\d)", c_str):
            col_age_12 = col

    age_cols = []
    if col_age_11:
        age_cols.append((col_age_11, "11"))
    if col_age_12:
        age_cols.append((col_age_12, "12"))

    if not age_cols:
        return 0, f"Could not isolate Age 11 or Age 12 columns. Detected headers: {list(df.columns)}"

    saved_count = 0
    current_meet = default_meet

    for _, row in df.iterrows():
        if has_comp_col and pd.notna(row[comp_col]) and str(row[comp_col]).strip():
            current_meet = resolve_meet_from_string(row[comp_col], default_meet)

        raw_ev = str(row[event_col]).strip()
        if not raw_ev or any(k in raw_ev.lower() for k in ["event", "stroke", "qualifying", "consideration"]):
            continue

        clean_ev = normalize_event_name(raw_ev)

        for col_name, age_band in age_cols:
            val_raw = row[col_name]
            sec = parse_time_value(val_raw)
            if sec is None:
                continue

            disp_str = format_display_time(sec)
            key = (current_meet, age_band, clean_ev)
            st.session_state.standards_db[key] = {"time": disp_str, "sec": sec}
            saved_count += 1

    return saved_count, None

# ==============================================================================
# 7. SESSION STATE INITIALIZATION & MULTI-TIER LOOKUP
# ==============================================================================
if "swimmer_df" not in st.session_state:
    st.session_state.swimmer_df = load_saved_pbs()

if "standards_db" not in st.session_state:
    st.session_state.standards_db = load_saved_standards()

def lookup_standard(meet, age, event_name):
    clean_ev = normalize_event_name(event_name)
    key = (meet, age, clean_ev)
    if key in st.session_state.standards_db:
        return st.session_state.standards_db[key]["time"], st.session_state.standards_db[key]["sec"]

    req_dist, req_stroke = extract_distance_and_stroke(event_name)
    if req_dist and req_stroke:
        for (m, a, e), data in st.session_state.standards_db.items():
            if m == meet and a == age:
                cand_dist, cand_stroke = extract_distance_and_stroke(e)
                if cand_dist == req_dist and cand_stroke == req_stroke:
                    return data["time"], data["sec"]

    for (m, a, e), data in st.session_state.standards_db.items():
        if m == meet and a == age and (e == clean_ev or e == str(event_name).lower()):
            return data["time"], data["sec"]

    return None, None

# ==============================================================================
# 8. CLUB HEADER
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
# 9. INGESTION WORKFLOW
# ==============================================================================
with st.expander("📥 Step 1: Update Jessica's Times from Rankings", expanded=(st.session_state.swimmer_df is None)):
    st.write("1. Open Jessica's Swim England profile using the link above.")
    st.write("2. Select all content from the page table, copy it, and paste it below:")
    raw_input = st.text_area("Paste table content here:", height=110, placeholder="Paste Swim England table text or HTML...")
    if st.button("🚀 Process & Store Times", use_container_width=True):
        parsed = parse_swim_england_table(raw_input)
        if parsed is not None and not parsed.empty:
            st.session_state.swimmer_df = parsed
            save_pbs_to_disk(parsed)
            st.success(f"Successfully captured and saved {len(parsed)} swim times!")
            st.rerun()
        else:
            st.error("No valid times found. Please check that table rows were included.")

if st.session_state.swimmer_df is None:
    st.info("Paste and process Jessica's table above to load the tracking dashboard.")
    st.stop()

df = st.session_state.swimmer_df

# ==============================================================================
# 10. STANDARDS IMPORT & LIVE DIAGNOSTICS
# ==============================================================================
with st.expander("🎯 Step 2: Import Qualifying Standards (Google Sheets & Diagnostics)", expanded=(len(st.session_state.standards_db) == 0)):
    tab_gsheet, tab_paste, tab_single = st.tabs(["🌐 Live Google Sheet Link", "📋 Paste Cells", "✏️ Single Event Entry"])

    with tab_gsheet:
        st.markdown(
            f"Sync directly from your shared Google Sheet tab (`{DEFAULT_WORKSHEET_TAB}` &bull; `gid={DEFAULT_WORKSHEET_GID}`):"
        )
        c_url, c_tab = st.columns([2, 1])
        with c_url:
            gsheet_raw_url = st.text_input(
                "Google Sheet Link",
                value=f"{DEFAULT_GSHEET_URL}#gid={DEFAULT_WORKSHEET_GID}",
            )
        with c_tab:
            worksheet_tab_name = st.text_input("Worksheet Tab Name / gid", value=DEFAULT_WORKSHEET_GID)

        sheet_meet = st.selectbox(
            "Default Meet (used only if Column A is completely blank):",
            ["NER SC (Winter)", "NER LC", "Yorkshire SC (Winter)", "Yorkshire LC"],
            key="gsheet_meet",
        )

        c_sync1, c_sync2 = st.columns([1, 1])
        with c_sync1:
            sync_btn = st.button("🔄 Sync Directly from Google Sheet", use_container_width=True)
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
                        count, parse_err = parse_standards_dataframe(df_sheet, sheet_meet)
                        if count > 0:
                            save_standards_to_disk(st.session_state.standards_db)
                            st.success(f"Successfully converted and saved {count} qualifying standards across all meets!")
                            st.rerun()
                        else:
                            st.error(parse_err)

    with tab_paste:
        st.write("Paste cells copied directly from Google Sheets / Excel:")
        paste_meet = st.selectbox(
            "Default Meet for pasted block:",
            ["NER SC (Winter)", "NER LC", "Yorkshire SC (Winter)", "Yorkshire LC"],
            key="paste_meet",
        )
        tsv_paste = st.text_area("Paste cells here (tab or comma separated):", height=110)
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
                    st.error(parse_err or "Verify that headers include 'Age 11' or 'Age 12'.")
            except Exception as e:
                st.error(f"Error parsing table: {e}")

    with tab_single:
        all_evs = sorted(df["Event"].unique().tolist(), key=gala_order_key)
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            s_ev = st.selectbox("Event", all_evs)
        with col_s2:
            s_meet = st.selectbox("Meet", ["Yorkshire LC", "Yorkshire SC (Winter)", "NER LC", "NER SC (Winter)"])
            s_age = st.selectbox("Age Band", ["11", "12"])
        with col_s3:
            s_val = st.text_input("Target Cut (e.g. 33.80, 00:00:33.8, or 1:08.20)")
            if st.button("💾 Save Standard", use_container_width=True):
                sec = parse_time_value(s_val)
                if sec:
                    clean_k = normalize_event_name(s_ev)
                    disp_str = format_display_time(sec)
                    st.session_state.standards_db[(s_meet, s_age, clean_k)] = {"time": disp_str, "sec": sec}
                    save_standards_to_disk(st.session_state.standards_db)
                    st.success(f"Saved {s_meet} Age {s_age} target for {s_ev} as {disp_str}!")
                    st.rerun()

    # Active Database Inspector & Clear Option
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
            st.info("No standards currently saved in app memory. Tap 'Sync Directly from Google Sheet' above.")

# Download JSON Backups
with st.expander("💾 Download / Backup Permanent JSON Files", expanded=False):
    st.write("Download these files to commit them to your GitHub repository for permanent offline backups:")
    c_dl1, c_dl2 = st.columns(2)
    with c_dl1:
        pbs_json_str = json.dumps(df.to_dict(orient="records"), indent=2)
        st.download_button(
            "📥 Download jessica_pbs.json",
            data=pbs_json_str,
            file_name="jessica_pbs.json",
            mime="application/json",
            use_container_width=True,
        )
    with c_dl2:
        std_serializable = {f"{k[0]}|||{k[1]}|||{k[2]}": v for k, v in st.session_state.standards_db.items()}
        st.download_button(
            "📥 Download standards.json",
            data=json.dumps(std_serializable, indent=2),
            file_name="standards.json",
            mime="application/json",
            use_container_width=True,
        )

# ==============================================================================
# 11. DASHBOARD FILTERS & KPI
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

# Calculate Unique Yorkshire LC Cuts for Active Age
unique_yks_cuts = 0
for ev in unique_events:
    best_lc_sec, _ = get_best_eligible_times(ev)
    _, target_s = lookup_standard("Yorkshire LC", active_age, ev)
    if target_s is not None and best_lc_sec is not None and best_lc_sec <= target_s:
        unique_yks_cuts += 1

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Unique Yorkshire LC Cuts (Age {active_age})", unique_yks_cuts)
m2.metric("Total Events Logged", len(unique_events))
m3.metric("Total Recorded PBs", len(df))
m4.metric("Standards Configured", len(st.session_state.standards_db))

st.markdown("---")

# ==============================================================================
# 12. UNIFIED EVENT CARDS (ONE PB BLOCK + ONE QUALIFYING MATRIX)
# ==============================================================================
for ev in unique_events:
    if selected_stroke != "All Events" and selected_stroke.lower() not in ev.lower():
        continue

    ev_rows = df[df["Event"] == ev]
    lc_sub = ev_rows[ev_rows["Course"] == "Long Course (50m)"]
    sc_sub = ev_rows[ev_rows["Course"] == "Short Course (25m)"]

    best_lc_sec, best_sc_sec = get_best_eligible_times(ev)

    yks_lc_11_t, yks_lc_11_s = lookup_standard("Yorkshire LC", "11", ev)
    yks_lc_12_t, yks_lc_12_s = lookup_standard("Yorkshire LC", "12", ev)
    yks_sc_11_t, yks_sc_11_s = lookup_standard("Yorkshire SC (Winter)", "11", ev)
    yks_sc_12_t, yks_sc_12_s = lookup_standard("Yorkshire SC (Winter)", "12", ev)

    ner_lc_11_t, ner_lc_11_s = lookup_standard("NER LC", "11", ev)
    ner_lc_12_t, ner_lc_12_s = lookup_standard("NER LC", "12", ev)
    ner_sc_11_t, ner_sc_11_s = lookup_standard("NER SC (Winter)", "11", ev)
    ner_sc_12_t, ner_sc_12_s = lookup_standard("NER SC (Winter)", "12", ev)

    eval_yks_lc_11 = evaluate_pace(best_lc_sec, yks_lc_11_s)
    eval_yks_lc_12 = evaluate_pace(best_lc_sec, yks_lc_12_s)
    eval_yks_sc_11 = evaluate_pace(best_sc_sec, yks_sc_11_s)
    eval_yks_sc_12 = evaluate_pace(best_sc_sec, yks_sc_12_s)

    eval_ner_lc_11 = evaluate_pace(best_lc_sec, ner_lc_11_s)
    eval_ner_lc_12 = evaluate_pace(best_lc_sec, ner_lc_12_s)
    eval_ner_sc_11 = evaluate_pace(best_sc_sec, ner_sc_11_s)
    eval_ner_sc_12 = evaluate_pace(best_sc_sec, ner_sc_12_s)

    with st.container():
        st.subheader(f"🏊 {ev}")

        card_left, card_right = st.columns([1, 1])

        with card_left:
            st.markdown('<div class="times-box">', unsafe_allow_html=True)
            if not lc_sub.empty:
                lc_r = lc_sub.iloc[0]
                st.markdown(f"**🏊‍♂️ LC PB:** `{lc_r['PB_Time']}` &nbsp;|&nbsp; Conv SC: `{lc_r['Conv_Time']}`")
            else:
                st.markdown("**🏊‍♂️ LC PB:** *No official LC PB recorded*")

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
                f"**Yorkshire LC:**  \n"
                f"Age 11: `{yks_lc_11_t or '--'}` &rarr; <span class='{eval_yks_lc_11[2]}'>{eval_yks_lc_11[1]} ({eval_yks_lc_11[0]})</span> &nbsp;|&nbsp; "
                f"Age 12: `{yks_lc_12_t or '--'}` &rarr; <span class='{eval_yks_lc_12[2]}'>{eval_yks_lc_12[1]} ({eval_yks_lc_12[0]})</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**Yorkshire SC (Winter):**  \n"
                f"Age 11: `{yks_sc_11_t or '--'}` &rarr; <span class='{eval_yks_sc_11[2]}'>{eval_yks_sc_11[1]} ({eval_yks_sc_11[0]})</span> &nbsp;|&nbsp; "
                f"Age 12: `{yks_sc_12_t or '--'}` &rarr; <span class='{eval_yks_sc_12[2]}'>{eval_yks_sc_12[1]} ({eval_yks_sc_12[0]})</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**NER LC:**  \n"
                f"Age 11: `{ner_lc_11_t or '--'}` &rarr; <span class='{eval_ner_lc_11[2]}'>{eval_ner_lc_11[1]} ({eval_ner_lc_11[0]})</span> &nbsp;|&nbsp; "
                f"Age 12: `{ner_lc_12_t or '--'}` &rarr; <span class='{eval_ner_lc_12[2]}'>{eval_ner_lc_12[1]} ({eval_ner_lc_12[0]})</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**NER SC (Winter):**  \n"
                f"Age 11: `{ner_sc_11_t or '--'}` &rarr; <span class='{eval_ner_sc_11[2]}'>{eval_ner_sc_11[1]} ({eval_ner_sc_11[0]})</span> &nbsp;|&nbsp; "
                f"Age 12: `{ner_sc_12_t or '--'}` &rarr; <span class='{eval_ner_sc_12[2]}'>{eval_ner_sc_12[1]} ({eval_ner_sc_12[0]})</span>",
                unsafe_allow_html=True,
            )
            st.markdown('</div>', unsafe_allow_html=True)

        with card_right:
            st.write(f"**Championship Progress (Active: Age {active_age})**")

            act_yks_lc_eval = eval_yks_lc_11 if active_age == "11" else eval_yks_lc_12
            if act_yks_lc_eval[0] != "No Cut":
                st.caption(f"Yorkshire LC: {act_yks_lc_eval[0]} ({act_yks_lc_eval[3]:.1f}%)")
                st.progress(act_yks_lc_eval[3] / 100.0)
            else:
                st.caption("Yorkshire LC: No target set.")

            act_yks_sc_eval = eval_yks_sc_11 if active_age == "11" else eval_yks_sc_12
            if act_yks_sc_eval[0] != "No Cut":
                st.caption(f"Yorkshire SC (Winter): {act_yks_sc_eval[0]} ({act_yks_sc_eval[3]:.1f}%)")
                st.progress(act_yks_sc_eval[3] / 100.0)
            else:
                st.caption("Yorkshire SC (Winter): No target set.")

            act_ner_lc_eval = eval_ner_lc_11 if active_age == "11" else eval_ner_lc_12
            if act_ner_lc_eval[0] != "No Cut":
                st.caption(f"NER LC: {act_ner_lc_eval[0]} ({act_ner_lc_eval[3]:.1f}%)")
                st.progress(act_ner_lc_eval[3] / 100.0)
            else:
                st.caption("NER LC: No target set.")

            act_ner_sc_eval = eval_ner_sc_11 if active_age == "11" else eval_ner_sc_12
            if act_ner_sc_eval[0] != "No Cut":
                st.caption(f"NER SC (Winter): {act_ner_sc_eval[0]} ({act_ner_sc_eval[3]:.1f}%)")
                st.progress(act_ner_sc_eval[3] / 100.0)
            else:
                st.caption("NER SC (Winter): No target set.")

        st.markdown("<hr style='margin: 1.5rem 0;'>", unsafe_allow_html=True)

# ==============================================================================
# 13. TABULAR SUMMARY VIEW
# ==============================================================================
with st.expander("📋 Tabular View of All Swims & Active Age Standards"):
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
