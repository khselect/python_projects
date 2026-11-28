"""비교 문장 — '평균보다 높았나, 몇 번째인가'를 코드가 계산해 AI 근거에 넣는다 (v0.23).

LLM은 숫자를 만들지 않으므로(guard가 근거에 없는 숫자를 버림), 비교·순위·평균·높다/낮다 판정은 여기서 끝낸다.
모델은 이 문장을 옮기기만 하면 된다 — 추론(생각) 모드가 필요 없다.

  IV 그룹 : 올해(진행 중)와 과거 10년 같은 기간 비교, 순위, 최고·최저 해, 연간 평균, 벤치마크를 이긴 해 수,
           최근 달과 예년 같은 달 비교
  II 매크로: 국면 점수의 최근 2년 중 위치, 위험회피·급변 주 비율, 현재 국면 지속 기간, VIX의 1년 중 위치
"""

from __future__ import annotations

import statistics
from datetime import date

from pf.synth.rules import fmt_score

YEARS = 10


def _p(v: float, nd: int = 1) -> str:
    x = round(v * 100, nd)
    return f"{0:.{nd}f}%" if x == 0 else f"{x:+.{nd}f}%"


def _compound(rets: list) -> float | None:
    if not rets or any(r is None for r in rets):
        return None
    out = 1.0
    for r in rets:
        out *= 1 + r
    return out - 1


def _cmp_word(x: float, ref: float) -> str:
    return "높음" if x > ref else ("낮음" if x < ref else "같음")


def group_year_facts(hm: dict, asof: str, years: int = YEARS) -> list[str]:
    """연도×월 히트맵(그룹 동일가중 월수익률) → 비교 문장."""
    ys, vals = hm.get("years") or [], hm.get("values") or []
    if len(ys) < 3:
        return []
    out = []
    cur_y, cur_row = ys[-1], vals[-1]
    partial = bool(hm.get("partial_last_year"))
    m = max((i + 1 for i, v in enumerate(cur_row) if v is not None), default=0)  # 올해 값이 있는 마지막 달
    past = [(y, r) for y, r in zip(ys[:-1], vals[:-1])][-years:] if partial else [(y, r) for y, r in zip(ys, vals)][-years - 1:-1]
    if partial and m:
        cur = _compound(cur_row[:m])
        same = [(y, _compound(r[:m])) for y, r in past]
        same = [(y, v) for y, v in same if v is not None]
        if cur is not None and len(same) >= 3:
            sv = [v for _, v in same]
            avg, med = statistics.mean(sv), statistics.median(sv)
            span = f"1~{m}월" if m > 1 else "1월"
            mtd = f"·{m}월은 기준일까지" if asof and int(asof[5:7]) == m else ""
            out.append(f"{cur_y}년({span}, 진행 중{mtd}) 그룹 수익률 {_p(cur)} — 과거 {len(same)}년"
                       f"({same[0][0]}~{same[-1][0]}) 같은 기간 평균 {_p(avg)}보다 {_cmp_word(cur, avg)}, 중앙값 {_p(med)}보다 {_cmp_word(cur, med)}")
            allv = sorted(same + [(cur_y, cur)], key=lambda x: x[1], reverse=True)
            rank = [y for y, _ in allv].index(cur_y) + 1
            best, worst = allv[0], allv[-1]
            out.append(f"같은 기간({span}) 수익률 순위: {len(allv)}년 중 {rank}위 "
                       f"(최고 {best[0]}년 {_p(best[1])}, 최저 {worst[0]}년 {_p(worst[1])})")
            # 최근 달 vs 예년 같은 달
            last = cur_row[m - 1]
            hist_m = [r[m - 1] for _, r in past if r[m - 1] is not None]
            if last is not None and len(hist_m) >= 3:
                am = statistics.mean(hist_m)
                out.append(f"{cur_y}년 {m}월{'(기준일까지)' if mtd else ''} 그룹 수익률 {_p(last)} — 과거 {len(hist_m)}년 {m}월 평균 "
                           f"{_p(am)}보다 {_cmp_word(last, am)}, {m}월이 플러스였던 해 {sum(v > 0 for v in hist_m)}/{len(hist_m)}년")
    ann, bann = hm.get("annual") or [], hm.get("bench_annual") or []
    full = list(zip(ys, ann, bann or [None] * len(ys)))
    full = full[:-1] if partial else full
    full = [x for x in full if x[1] is not None][-years:]
    if len(full) >= 3:
        av = [a for _, a, _ in full]
        out.append(f"과거 {len(full)}년({full[0][0]}~{full[-1][0]}) 연간 수익률 평균 {_p(statistics.mean(av))}, "
                   f"중앙값 {_p(statistics.median(av))}, 플러스였던 해 {sum(a > 0 for a in av)}/{len(av)}년")
        beat = [(y, a, b) for y, a, b in full if b is not None]
        if beat:
            out.append(f"같은 {len(beat)}년 중 벤치마크보다 수익률이 높았던 해 {sum(a > b for _, a, b in beat)}/{len(beat)}년")
    return out


def macro_history_facts(macro: dict) -> list[str]:
    """국면 점수·국면의 최근 2년 중 위치 (주간 이력 기준)."""
    h = macro.get("history") or {}
    sc = h.get("score") or []
    if len(sc) < 10:
        return []
    out = []
    now = macro["score"]
    lower = sum(v < now for v in sc)
    same = sum(v == now for v in sc)
    med = statistics.median(sc)
    med_s = fmt_score(int(med)) if float(med).is_integer() else f"{med:+.1f}"
    out.append(f"최근 2년 주간 국면 점수 {len(sc)}개 중 지금({fmt_score(now)})보다 낮았던 주 {lower}개, 같았던 주 {same}개 "
               f"(2년 최저 {fmt_score(min(sc))}, 최고 {fmt_score(max(sc))}, 중앙값 {med_s})")
    th = macro.get("thresholds") or {"riskoff": -4, "expansion": 4}
    st = h.get("stress") or [False] * len(sc)
    ro = sum((v <= th["riskoff"]) or s for v, s in zip(sc, st))
    ex = sum(v >= th["expansion"] and not s for v, s in zip(sc, st))
    out.append(f"최근 2년 {len(sc)}주 중 위험회피 {ro}주, 확장 {ex}주, 급변 규칙 발동 {sum(bool(s) for s in st)}주")
    try:
        days = (date.fromisoformat(macro["asof"]) - date.fromisoformat(macro["regime_since"])).days
        out.append(f"현재 국면 '{macro['regime']}' — {macro['regime_since']}부터 {days}일째(달력일)")
    except (KeyError, ValueError):
        pass
    vix = next((i for i in macro.get("indicators", []) if i["key"] == "vix"), None)
    v = (vix or {}).get("values") or {}
    if v.get("level") is not None and v.get("pct_1y") is not None:
        out.append(f"VIX {v['level']:.1f} — 최근 1년 거래일 중 {round(v['pct_1y'] * 100):d}%의 날보다 높은 수준"
                   + (f" (1년 최고 {v['max_1y']:.1f})" if v.get("max_1y") is not None else ""))
    return out
