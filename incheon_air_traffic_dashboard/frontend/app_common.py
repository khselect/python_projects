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


def api_post_file(path: str, filename: str, file_bytes: bytes, data: dict | None = None):
    """엑셀 파일 업로드. 백엔드가 4xx로 거절하면 detail 메시지를 RuntimeError로 올린다."""
    r = requests.post(
        f"{BACKEND_URL}{path}",
        files={"file": (filename, file_bytes,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data=data or {},
        timeout=120,
    )
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise RuntimeError(detail)
    return r.json()
