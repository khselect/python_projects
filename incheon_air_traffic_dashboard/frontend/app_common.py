"""공통 유틸: 백엔드 API 호출 헬퍼."""
import os
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")


@st.cache_data(ttl=300)
def get_stations():
    r = requests.get(f"{BACKEND_URL}/api/stations", timeout=10)
    r.raise_for_status()
    return r.json()


def pm25_stations(stations):
    return [s["name"] for s in stations if s["has_pm25"]]


def api_get(path: str, params: dict | None = None):
    r = requests.get(f"{BACKEND_URL}{path}", params=params or {}, timeout=20)
    r.raise_for_status()
    return r.json()
