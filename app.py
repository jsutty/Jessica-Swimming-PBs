def parse_standards_dataframe(df_raw, default_meet):
    if df_raw.empty or df_raw.shape[1] < 2:
        return 0, "Table has fewer than 2 columns."

    # Identify whether we have a dedicated Competition column
    has_comp_col = False
    comp_col = None
    event_col = None

    for col in df_raw.columns:
        col_clean = str(col).strip().lower()
        if "comp" in col_clean or "meet" in col_clean or "championship" in col_clean:
            has_comp_col = True
            comp_col = col
        elif "event" in col_clean or "stroke" in col_clean or "race" in col_clean:
            event_col = col

    # Fallbacks if headers weren't named exactly "Competition" / "Event"
    if not event_col:
        event_col = df_raw.columns[1] if has_comp_col else df_raw.columns[0]
    if not has_comp_col and df_raw.shape[1] >= 3:
        # Check if column 0 contains meet names
        sample_val = str(df_raw.iloc[0, 0]).lower()
        if any(k in sample_val for k in ["ner", "york", "winter", "lc", "sc"]):
            has_comp_col = True
            comp_col = df_raw.columns[0]
            event_col = df_raw.columns[1]

    # Map Age 11 and Age 12 columns strictly
    age_cols = []
    for col in df_raw.columns:
        if col in [comp_col, event_col]:
            continue
        c_str = str(col).strip().lower()
        if re.search(r"\b11\b", c_str) or "age 11" in c_str or "11yr" in c_str:
            age_cols.append((col, "11"))
        elif re.search(r"\b12\b", c_str) or "age 12" in c_str or "12yr" in c_str:
            age_cols.append((col, "12"))

    if not age_cols:
        return 0, f"No 'Age 11' or 'Age 12' columns found. Detected headers: {list(df_raw.columns)}"

    saved_count = 0
    current_meet = default_meet

    for _, row in df_raw.iterrows():
        # Determine meet for this row
        if has_comp_col and pd.notna(row[comp_col]) and str(row[comp_col]).strip():
            c_text = str(row[comp_col]).strip().lower()
            if "ner" in c_text and ("sc" in c_text or "winter" in c_text or "25" in c_text):
                current_meet = "NER SC (Winter)"
            elif "ner" in c_text and ("lc" in c_text or "50" in c_text):
                current_meet = "NER LC"
            elif "york" in c_text and ("sc" in c_text or "winter" in c_text or "25" in c_text):
                current_meet = "Yorkshire SC (Winter)"
            elif "york" in c_text and ("lc" in c_text or "50" in c_text):
                current_meet = "Yorkshire LC"

        raw_ev = str(row[event_col]).strip()
        if not raw_ev or "event" in raw_ev.lower() or "stroke" in raw_ev.lower():
            continue

        clean_ev = normalize_event_name(raw_ev)

        for col_name, age_band in age_cols:
            val_str = str(row[col_name]).strip()
            sec = time_to_seconds(val_str)
            if sec is None:
                continue

            key = (current_meet, age_band, clean_ev)
            st.session_state.standards_db[key] = {"time": val_str, "sec": sec}
            saved_count += 1

    return saved_count, None
