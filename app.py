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
    page_title=f"{SWIMMER_NAME} - PB & Championship Tracker",
    page_icon="🏊‍♀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==========================================
# TIME CONVERSION HELPERS
# ==========================================
def time_to_seconds(time_str: str) -> float | None:
    """Converts MM:SS.ss or SS.ss into float seconds."""
    if not time_str or not isinstance(time_str, str):
        return None
    time_str = time_str.strip()
