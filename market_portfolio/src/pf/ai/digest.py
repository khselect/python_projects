"""게시 JSON → AI 해설 근거(digest). 숫자는 여기서만 만들어진다.

LLM은 이 근거 문장만 보고 풀어 쓰며, 답변의 숫자·날짜는 guard가 이 근거와 대조한다.
그래서 숫자 표기(소수 자리·부호)는 화면과 같게, 그리고 한 가지 방식으로만 쓴다.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from pf.config import load_glossary
from pf.synth.rules import fmt_score, synthesize

SIGNAL = {1.0: "우호", 0.0: "중립", -1.0: "비우호"}


@dataclass
class Digest:
    kind: str  # macro | group | ticker
    key: str  # "macro" | 그룹 id | 종목 코드
    title: str
    asof: str
    facts: list[str]
    terms: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    loss: list[str] = field(default_factory=list)  # 손실 쪽 숫자(90% 하단·CVaR). 답변에 하나 이상 있어야 통과

    def text(self) -> str:
        lines = [f"[화면] {self.title} (기준일 {self.asof})", "[근거]"]
        lines += [f"- {f}" for f in self.facts]
        if self.terms:
            lines += ["[용어]"] + [f"- {t}" for t in self.terms]
        return "\n".join(lines)

    def hash(self) -> str:
        return hashlib.sha256(self.text().encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return asdict(self)


def pct(v: float | None, nd: int = 1) -> str:
    """부호 있는 백분율. 화면(_pct)과 같은 표기."""
    if v is None:
        return "—"
    x = round(v * 100, nd)
    return f"{0:.{nd}f}%" if x == 0 else f"{x:+.{nd}f}%"


def prob(v: float) -> str:
    return f"{round(v * 100):d}%"


def _terms(keys: list[str]) -> list[str]:
    g = load_glossary()
    return [f"{g[k]['label']}: {g[k]['tip']}" for k in keys if k in g]


def _verdict_facts(macro: dict | None, group: dict | None, ticker: dict | None) -> list[str]:
    v = synthesize(macro, group, ticker)
    out = [f"세 층 종합 판정(규칙 기반): {v.title}. {v.text}"]
    for l in v.layers:
        ref = ", 참고용" if l.reference_only else ""
        out.append(f"{l.name} 층 {l.label.split(' ', 1)[-1]}{ref}: {l.basis}")
    return out


# ── ① 매크로 ─────────────────────────────────────────────

def _indicator_fact(ind: dict) -> str:
    name, s, v = ind["name"], SIGNAL.get(ind["signal"], "자료 없음"), ind.get("values") or {}
    detail = ""
    if ind.get("public_values", True):
        k = ind["key"]
        v = {kk: vv for kk, vv in v.items() if vv is not None}
        if k == "liquidity" and "gap" in v:
            detail = f", GDP 전년비 − 기준금리 {v['gap']:+.2f}%p"
        elif k in ("commodity", "breadth", "dollar") and "vs_ma" in v:
            detail = f", 200일 평균 대비 {pct(v['vs_ma'])}"
        elif k == "curve" and "level" in v:
            detail = f", 10년−2년 금리차 {v['level']:+.2f}%p"
    elif v.get("direction"):
        detail = f", 스프레드 방향 {v['direction']} (값은 비공개)"
    since = f", {ind['last_switch']}부터" if ind.get("last_switch") else ""
    return f"{name}: {s}{detail}{since}"


def macro_digest(macro: dict) -> Digest:
    inds = macro["indicators"]
    cnt = {lab: sum(1 for i in inds if SIGNAL.get(i["signal"]) == lab) for lab in ("우호", "중립", "비우호")}
    facts = [
        f"국면 점수 {fmt_score(macro['score'])} (범위 −6~+6), 국면 '{macro['regime']}', {macro['regime_since']}부터",
        f"{len(inds)}개 지표 중 우호 {cnt['우호']}개, 중립 {cnt['중립']}개, 비우호 {cnt['비우호']}개",
    ]
    facts += [_indicator_fact(i) for i in inds]
    for m in ("3", "6", "12"):
        c = (macro.get("compare") or {}).get(m)
        if c:
            facts.append(f"{m}개월 전({c['date']}) 국면 점수 {fmt_score(c['score'])}, '{c['regime']}'")
    mk = macro.get("markets")
    if mk and mk.get("change"):
        chg = ", ".join(f"{mk['names'][k]} {pct(v)}" for k, v in mk["change"].items())
        facts.append(f"{mk['dates'][0]}부터 기준일까지 누적 변화: {chg}")
    return Digest(
        "macro", "macro", "① 매크로 국면", macro["asof"], facts,
        _terms(["regime_score", "liquidity", "commodity", "breadth", "credit", "curve", "dollar"]),
        [f"macro.json ({macro['asof']})"],
    )


# ── ③ 그룹 ──────────────────────────────────────────────

def _valuation_facts(val: dict | None) -> list[str]:
    if not val:
        return []
    cov = val.get("coverage") or {}
    ttm = val.get("ttm") or {}
    out = []
    if ttm.get("pe"):
        last = {k: (ttm.get(k) or [None])[-1] for k in ("pe", "pfcf", "gap", "conv", "n")}
        n = last["n"] if last["n"] is not None else len(cov.get("have", []))
        parts = [f"후행 P/E {last['pe']:.1f}배" if last["pe"] is not None else "후행 P/E 산출 불가(합산 순이익 0 이하)",
                 f"P/FCF {last['pfcf']:.1f}배" if last["pfcf"] is not None else "P/FCF 산출 불가(합산 FCF 0 이하)"]
        if last["gap"] is not None:
            parts.append(f"괴리(P/FCF − P/E) {last['gap']:+.1f}")
        if last["conv"] is not None:
            parts.append(f"FCF 전환율 {last['conv']:.2f}")
        out.append(", ".join(parts) + f" (재무 확보 {n:.0f}종목 합산)")
    fwd = (val.get("forward_pe") or {}).get("values") or []
    if fwd and fwd[-1] is not None:
        out.append(f"선행 P/E {fwd[-1]:.1f}배")
    if cov.get("missing"):
        out.append(f"재무 미확보 종목: {', '.join(cov['missing'])}")
    return out


def group_digest(group: dict, valuation: dict | None = None, macro: dict | None = None) -> Digest:
    g = group["group"]
    car = group["car"]
    c21 = car.get("car21") or {}
    facts = [
        f"{g['name']} 그룹 구성 종목: {', '.join(g['members'])}",
        f"비교 기준(벤치마크): {g['benchmark']} ETF — 구성 종목이 아님",
    ]
    loss = []
    if c21:
        loss.append(pct(c21["p5"]))
        facts.append(
            f"과거 실적 후 21일 초과수익 중앙값 {pct(c21['median'])}, 90% 구간 {pct(c21['p5'])} ~ {pct(c21['p95'])}, "
            f"하락 비율 {prob(c21['p_down'])}, 표본 {c21['n']}건 ({car['first']} ~ {car['last']})")
    hm = group.get("heatmap") or {}
    if hm.get("annual"):
        y, a = hm["years"][-1], hm["annual"][-1]
        b = (hm.get("bench_annual") or [None])[-1]
        part = " (연중)" if hm.get("partial_last_year") else ""
        facts.append(f"{y}년{part} 그룹 동일가중 수익률 {pct(a)}" + (f", 벤치마크 {pct(b)}" if b is not None else ""))
    for u in (group.get("upcoming") or [])[:3]:
        if u.get("p_down") is None or u.get("p5") is None:
            facts.append(f"다가오는 실적: {u['ticker']} {u['date']} {u['timing']} ({u['days']}일 남음)")
            continue
        loss.append(pct(u["p5"]))
        facts.append(f"다가오는 실적: {u['ticker']} {u['date']} {u['timing']} ({u['days']}일 남음), "
                     f"다음 날 하락 확률 {prob(u['p_down'])}, 90% 하단 {pct(u['p5'])}")
    facts += _valuation_facts(valuation)
    facts += _verdict_facts(macro, group, None)
    return Digest(
        "group", g["id"], f"③ 그룹 상세 — {g['name']}", group["asof"], facts,
        _terms(["car", "interval90", "regime_score"]),
        [f"group/{g['id']}.json ({group['asof']})"] + ([f"valuation/{g['id']}.json"] if valuation else [])
        + (["macro.json"] if macro else []),
        loss,
    )


# ── ④ 종목 ──────────────────────────────────────────────

def ticker_digest(t: dict, group: dict | None = None, macro: dict | None = None) -> Digest:
    h1 = t["sim"]["horizons"]["1"]
    s, ev, m = t["sample"], t.get("next_event"), t["model"]["ticker"]
    facts = [
        f"{t['ticker']} ({t['group']['name']}), 다음 실적 " + (f"{ev['date']} {ev['timing']}" if ev else "미정"),
        f"표본 {s['n_events']}건 ({s['first']} ~ {s['last']}), 그룹 표본 {s['group_events']}건, 상태 {t['gate']['status']}",
        f"다음 날: 상승 확률 {prob(h1['p_up'])}, 하락 확률 {prob(h1['p_down'])}, 기대값 {pct(h1['mean'])}, "
        f"90% 구간 {pct(h1['pcts']['5'])} ~ {pct(h1['pcts']['95'])}, CVaR5 {pct(h1['cvar5'])}",
        "시나리오: " + ", ".join(f"{lab} 비중 {round(w * 100):d}% 평균 {pct(mu)}"
                               for lab, w, mu in zip(m["labels"], m["weights"], m["means"])),
    ]
    for hz in ("21",):
        x = t["sim"]["horizons"].get(hz)
        if x:
            facts.append(f"{hz}일 누적: 중앙값 {pct(x['pcts']['50'])}, 90% 구간 {pct(x['pcts']['5'])} ~ {pct(x['pcts']['95'])}")
    facts += _verdict_facts(macro, group, t)
    return Digest(
        "ticker", t["ticker"], f"④ 종목 상세 — {t['ticker']}", t["asof"], facts,
        _terms(["p_down", "interval90"]),
        [f"ticker/{t['ticker']}.json ({t['asof']})"],
        [pct(h1["pcts"]["5"]), pct(h1["cvar5"])],
    )


def dumps(d: Digest) -> str:
    return json.dumps(d.to_dict(), ensure_ascii=False)
