"""종합 인사이트 — 모든 화면 오른쪽에 고정되는 패널 (F19 세 층 판정, F20 AI 해설 + 자유 질문).

이름 (v0.17): 판정은 AI가 아닌 규칙 계산이라 "AI 어시스턴트" 대신 "종합 인사이트".
F20 연결 뒤 AI 칸을 위로 올리거나 이름을 바꿀 수 있다.

보고 있는 화면의 맥락(그룹·종목)을 따라간다.
  V. 종목 상세 : 선택한 종목 + 그 종목의 산업 그룹
  그 외 화면  : 사이드바 관심 그룹 (+ V에서 마지막으로 본 종목이 같은 그룹이면 함께)
"""

from __future__ import annotations

import json

import streamlit as st

from common import coverage
from pf.ai.pregen import load_ai
from pf.macro.publish import MACRO_PATH
from pf.publish.group import load_group
from pf.publish.ticker import load_published
from pf.synth.rules import synthesize

BADGE_COLOR = {"agree_pos": "blue", "agree_neg": "red", "conflict": "orange", "partial": "gray", "neutral": "gray", "none": "gray"}
STICKY_CSS = """
<style>
/* 오른쪽 종합 인사이트 패널: 스크롤해도 화면에 고정 (넓은 화면에서만, 좁으면 아래로 쌓임).
   열을 행 높이만큼 늘이지 않도록 부모 행의 정렬을 위쪽으로 두고, 패널 열에 sticky를 준다. */
@media (min-width: 900px) {
  div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"] .synth-anchor) {
    align-items: flex-start;
  }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"][data-testid="stColumn"]:has(.synth-anchor) {
    position: sticky; top: 3.75rem; align-self: flex-start; height: auto;
    max-height: calc(100vh - 4.5rem); overflow-y: auto;
    border-left: 1px solid #e6e6e6; padding-left: 1rem;
  }
}
</style>
"""


@st.cache_data(ttl=300)
def _macro():
    return json.loads(MACRO_PATH.read_text(encoding="utf-8")) if MACRO_PATH.exists() else None


@st.cache_data(ttl=300)
def _group(gid: str):
    return load_group(gid)


@st.cache_data(ttl=300)
def _ai(kind: str, key: str):
    return load_ai(kind, key)


@st.cache_data(ttl=300)
def _ticker(t: str):
    return load_published(t)


def _context(page_path: str) -> tuple[str, str | None]:
    cov = coverage()
    gid = st.session_state.get("group") or cov.defaults.get("groups", ["semis"])[0]
    # V의 선택 위젯 키("ticker")는 다른 화면으로 가면 Streamlit이 지운다 → 마지막으로 본 종목을 따로 쓴다
    t = st.session_state.get("ticker") or st.session_state.get("last_ticker")
    if page_path == "ticker":
        t = t if t in cov.tickers else "AVGO"  # V. 첫 진입 기본값과 같게
        own = next((g.id for g in cov.industry if t in g.members), gid)
        return own, t
    members = cov.group(gid).members
    return gid, (t if t in members else None)


def render(page_path: str) -> None:
    # 기본(첫) 화면의 url_path는 항상 "" (Streamlit 규칙) → 이름으로 바꿔 쓴다.
    # (v0.20까지 기본 화면이던 II에서 page_path == "macro"가 맞지 않아 매크로 해설 대신 그룹 해설이 나오던 버그)
    page_path = page_path or "overview"
    st.html(STICKY_CSS)
    st.markdown('<div class="synth-anchor"></div>', unsafe_allow_html=True)
    st.markdown("#### 종합 인사이트")
    gid, t = _context(page_path)
    gname = coverage().group(gid).name
    st.caption(f"보는 중: {gname}" + (f" · {t}" if t else ""))

    v = synthesize(_macro(), _group(gid), _ticker(t) if t else None)
    st.markdown("**세 층 판정**", help="매크로 → 그룹 → 종목. 규칙 기반 계산(AI 미사용). 상위 층을 우선하고 점수를 평균내지 않습니다.")
    st.markdown(f"**:{BADGE_COLOR[v.code]}-background[{v.title}]**")
    st.caption(v.text)
    for layer in v.layers:
        ref = " :gray-background[참고용]" if layer.reference_only else ""
        st.markdown(f"**{layer.name}** · {layer.label}{ref}")
        st.caption(layer.basis)
    st.caption("상위 층(매크로 → 그룹 → 종목)을 우선하고 점수를 평균내지 않습니다. 과거 통계 기반 참고 정보입니다.")

    st.divider()
    _ai_section(page_path, gid, t)


def _md(s: str) -> str:
    """마크다운 오해석 방지: '~'(취소선), '$'(수식)."""
    return s.replace("~", "\\~").replace("$", "\\$")


def _ai_section(page_path: str, gid: str, t: str | None) -> None:
    """F20 1단계: 매일 배치가 미리 만든 해설을 읽기만 한다 (페이지 조회당 LLM 호출 0)."""
    if page_path == "overview":
        d = _ai("overview", "overview") or _ai("macro", "macro")
    elif page_path == "macro":
        d = _ai("macro", "macro")
    else:
        d = (_ai("ticker", t) if t else None) or _ai("group", gid)
    st.markdown("**AI 해설**", help="맥미니 로컬 sLLM(Ollama)이 매일 배치에서 이 사이트의 수치와 용어 가이드만 근거로 "
                "미리 쓴 해설입니다. 답변 속 숫자·날짜는 근거와 코드로 대조하고, 맞지 않으면 버리고 근거 요약(템플릿)을 보여줍니다.")
    if not d:
        st.caption("오늘 해설이 아직 없습니다. 다음 배치(매일 07:15) 뒤에 표시됩니다.")
    else:
        if d["mode"] == "ai":
            st.caption(f"대상: {d['title']} · {d['model']} · 기준일 {d['asof']}")
        else:
            st.caption(f"대상: {d['title']} · :gray-background[근거 요약] AI 해설을 쓰지 못해 근거 앞부분을 보여줍니다")
        st.markdown(_md(d["text"]))
        with st.expander("근거 보기"):
            st.caption(" · ".join(d.get("sources", [])))
            st.markdown("\n".join(f"- {_md(f)}" for f in d["facts"]))
            if d.get("reason"):
                st.caption(f"템플릿 사유: {d['reason']}")
        st.caption("AI가 쓴 문장은 틀릴 수 있습니다. 숫자는 위 판정과 각 화면을 기준으로 보세요. 투자 권유가 아닙니다.")
    _qa_section(page_path, gid, t)


# ── F20 2단계: 자유 질문 ─────────────────────────────────────
@st.cache_resource
def _qa_runtime():
    """프로세스 하나에 설정·대기열 하나 (방문자 모두 공유 — 모델이 달라도 Ollama는 한 번에 1건)."""
    from pf.ai.qa import Gate, qa_config

    cfg = qa_config()
    return cfg, Gate(cfg["queue_max"])


@st.cache_resource
def _qa_client(model: str, timeout: float):
    from pf.ai.client import get_client

    return get_client(model, timeout=timeout)


@st.cache_data(ttl=300)
def _installed_models(default: str) -> list[str]:
    c = _qa_client(default, 10)
    return c.models() if c is not None else []


@st.cache_data(ttl=300)
def _overview():
    from pf.publish.overview import OVERVIEW_PATH

    return json.loads(OVERVIEW_PATH.read_text(encoding="utf-8")) if OVERVIEW_PATH.exists() else None


@st.cache_data(ttl=300)
def _valuation(gid: str):
    from pf.publish.valuation import load_valuation

    return load_valuation(gid)


def _page_digest(page_path: str, gid: str, t: str | None):
    """지금 보는 화면의 근거 (미리 생성 해설과 같은 digest)."""
    from pf.ai.digest import group_digest, macro_digest, overview_digest, ticker_digest

    m = _macro()
    try:
        if page_path == "overview" and _overview():
            return overview_digest(_overview(), m)
        if page_path == "macro" and m:
            return macro_digest(m)
        if page_path == "ticker" and t and _ticker(t):
            return ticker_digest(_ticker(t), _group(gid), m)
        g = _group(gid)
        if g:
            return group_digest(g, _valuation(gid), m)
        return macro_digest(m) if m else None
    except Exception:
        return None


QA_MODE_NOTE = {
    "refused": "범위 밖 질문 — AI를 부르지 않고 안내했습니다",
    "fallback": "검증을 통과한 답이 없어 근거 일부를 보여줍니다",
    "limit": "한도 안내", "busy": "대기열 가득", "error": "연결 오류",
}


def _qa_section(page_path: str, gid: str, t: str | None) -> None:
    from datetime import date

    from pf.ai.qa import answer

    st.markdown("**질문하기**", help="지금 보는 화면의 수치와 용어 설명만 근거로 로컬 AI(기본 gemma3:4b, 아래에서 모델 선택)가 답합니다. "
                "답의 숫자·날짜는 근거와 코드로 대조하고, 맞지 않으면 답 대신 근거를 보여줍니다. "
                "매수·매도·비중·목표가 질문은 AI를 부르지 않고 안내합니다. 개인정보는 입력하지 마세요.")
    cfg, gate = _qa_runtime()
    default = cfg["chat_model"]
    installed = set(_installed_models(default))
    choices = [m for m in cfg["chat_models"] if m in installed or f"{m}:latest" in installed] or [default]
    if st.session_state.get("qa_model") not in choices:
        st.session_state["qa_model"] = default if default in choices else choices[0]
    model = st.selectbox("답변 모델", choices, key="qa_model",
                         help="맥미니에 설치된 로컬 모델 중 고릅니다. 같은 근거·검증을 거치므로 모델별로 답과 걸린 시간을 비교해 볼 수 있습니다. "
                              "qwen3는 생각 모드를 끄고 호출합니다. 기본이 아닌 모델은 5분만 메모리에 머뭅니다.") if len(choices) > 1 else choices[0]
    client = _qa_client(model, cfg["chat_timeout_s"])
    today = date.today().isoformat()
    used = st.session_state.setdefault("qa_used", {}).get(today, 0)
    hist = st.session_state.setdefault("qa_hist", [])
    for h in hist[-3:]:
        with st.chat_message("user"):
            st.markdown(_md(h["q"]))
        with st.chat_message("assistant"):
            st.markdown(_md(h["text"]))
            note = (f"{h.get('model')} · {h.get('seconds')}초 · 검증 통과" if h["mode"] == "ai"
                    else QA_MODE_NOTE.get(h["mode"], h["mode"]))
            st.caption(f"{h['page']} · {note}")
            if h.get("evidence"):
                with st.expander("근거 보기"):
                    st.text(h["evidence"])
    left = cfg["session_daily"] - used
    d = _page_digest(page_path, gid, t)
    disabled = client is None or d is None or left <= 0
    ph = ("AI 해설이 꺼져 있습니다" if client is None else "근거 자료가 아직 없습니다" if d is None
          else "오늘 질문 한도를 다 썼습니다" if left <= 0 else f"이 화면에 대해 질문 (오늘 {left}회 남음)")
    q = st.chat_input(ph, disabled=disabled, key="ai_q", max_chars=cfg["max_question_chars"])
    if q and not disabled:
        with st.spinner("근거를 확인하며 답을 쓰는 중… (보통 10~20초)"):
            res = answer(q, d, client, cfg, gate)
        if res["mode"] in ("ai", "fallback"):
            st.session_state["qa_used"] = {today: used + 1}
        hist.append({"q": q, "page": d.title, **{k: res.get(k) for k in ("mode", "text", "model", "seconds", "evidence")}})
        st.session_state["qa_hist"] = hist[-10:]
        st.rerun()
