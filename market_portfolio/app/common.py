"""모든 화면이 공유하는 사이드바·고지 문구·도움말."""

from __future__ import annotations

import streamlit as st

import json

from pf.config import load_coverage, load_glossary
from pf.publish.ticker import PUBLISH_DIR
from pf.settings import offline

DISCLAIMER = (
    "정보 제공 목적이며 투자 자문이 아닙니다 · "
    "과거 통계는 미래 수익을 보장하지 않습니다"
)


@st.cache_data
def coverage():
    return load_coverage()


@st.cache_data
def glossary() -> dict:
    return load_glossary()


@st.cache_data(ttl=300)
def latest_asof() -> str:
    """게시된 계산 결과 중 가장 최근 기준일."""
    dates = []
    for p in PUBLISH_DIR.glob("*.json"):
        try:
            dates.append(json.loads(p.read_text(encoding="utf-8"))["asof"])
        except (OSError, ValueError, KeyError):
            continue
    return max(dates) if dates else "—"


def tip(key: str) -> str | None:
    """glossary.yaml의 한 줄 툴팁 (help= 인자용)."""
    item = glossary().get(key)
    return item["tip"] if item else None


def sidebar() -> None:
    cov = coverage()
    with st.sidebar:
        st.subheader("관심 그룹")
        options = [g.id for g in cov.groups]
        default = cov.defaults.get("groups", options[:1])[0]
        st.radio(
            "그룹",
            options,
            index=options.index(st.session_state.get("group", default)),
            format_func=lambda gid: cov.group(gid).name,
            key="group",
            label_visibility="collapsed",
        )
        st.divider()
        st.caption(f"데이터: {'합성(오프라인)' if offline() else '실데이터'}")
        st.caption(f"기준일: {latest_asof()}")
        st.caption("LLM 호출: 0회")


def footer() -> None:
    st.divider()
    st.caption(DISCLAIMER)
