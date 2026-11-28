"""국면 점수 검증 — 스트레스 구간을 얼마나 빨리 잡고, 얼마나 자주 헛경보를 내는가 (v0.21~).

신뢰성공학의 탐지 성능 관점: 탐지 지연(lead/lag)과 오경보율을 설계안별로 비교한다.
  v6   기존안(v0.20): 매크로 층 6개, 경계 ±3, 급변 규칙 없음
  v10i v0.21: 매크로 6 + 시장 4 = 10개, 경계 ±4, 급변 규칙 즉시 해제
  v10  현재안(v0.22): v10i + 급변 해제 히스테리시스 (VIX < 25 · 나스닥100 −15%보다 회복 5거래일 연속)

스트레스 구간(정답 사건): S&P 500이 **52주 고점** 대비 −15% 이상 하락한 구간 (고점 → 저점).
  v0.21은 역대 최고가 기준이라 2008 하락이 2013 신고가까지 한 구간으로 이어져 2010·2011 하락이 빠졌다.
  52주 고점 기준 −10% 이하가 이어지는 구간마다 하나로 보고, 같은 고점에서 나온 구간은 합친다.
  탐지일   : 고점 이후 처음 '위험회피'(점수 ≤ 하단 또는 급변)가 된 날
  지연     : 고점 → 탐지일 거래일 수, 그리고 −10% 도달일 대비 며칠 앞/뒤인지
  놓침     : 저점까지 한 번도 위험회피가 아니었음
오경보: 위험회피로 '들어간' 날 중 스트레스 구간 밖이고, 이후 63거래일 동안 S&P 500 최대 낙폭이 −7%보다 얕은 경우.

주의: 하이일드 스프레드(신용)는 FRED에 최근 3년만 있어 그 이전은 두 안 모두 신용 기여 0.
경계값을 이 결과로 고르면 과적합 위험이 있다 — 바꿀 때는 근거와 함께 PLAN에 기록한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from pf.config import load_model
from pf.data.fred import get_fred
from pf.data.sources import get_source
from pf.macro.indicators import SPX
from pf.macro.publish import frame
from pf.publish.ticker import PUBLISH_DIR, _write_json

EVAL_PATH = PUBLISH_DIR.parent / "macro_eval.json"
EPISODE_DD = -0.15
CONFIRM_DD = -0.10
FA_HORIZON, FA_DD = 63, -0.07


def episodes(px: pd.Series, depth: float = EPISODE_DD, window: int = 252) -> list[dict]:
    """52주 고점 대비 −10% 이하가 이어지는 구간 중 바닥이 depth 이하인 것: 고점 → 저점."""
    px = px.dropna()
    if px.empty:
        return []
    dd = px / px.rolling(window, min_periods=1).max() - 1
    below = (dd <= CONFIRM_DD).to_numpy()
    idx, n, out, i = px.index, len(px), [], 0
    while i < n:
        if not below[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and below[j + 1]:
            j += 1
        peak = px.iloc[max(0, i - window + 1):i + 1].idxmax()
        seg = px.iloc[i:j + 1]
        trough = seg.idxmin()
        d = float(px[trough] / px[peak] - 1)
        # 같은 고점에서 다시 빠졌거나, 새 고점이 앞 구간 저점보다 이르면(52주 창이 밀리며 생긴 겹침,
        # 예: 2022-01 약세장 속 2022-03 고점 → 2023-03 재하락) 같은 하락으로 보고 합친다 (v0.22)
        if out and (out[-1]["peak"] == peak or peak <= out[-1]["trough"]):
            e = out[-1]
            if px[trough] < px[e["trough"]]:
                e["trough"], e["depth"] = trough, float(px[trough] / px[e["peak"]] - 1)
            e["recovered"] = j < n - 1
        elif d <= depth:
            out.append({"peak": peak, "confirm10": idx[i], "trough": trough, "depth": d, "recovered": j < n - 1})
        i = j + 1
    return out


def riskoff_flags(df: pd.DataFrame, variant: str, hi: int, lo: int) -> pd.Series:
    if variant == "v6":
        return df["score_macro"] <= -3
    col = "stress_entry" if variant == "v10i" else "stress"
    st = df[col] == 1 if col in df else False
    return (df["score"] <= lo) | st


def score_variant(df: pd.DataFrame, px: pd.Series, eps: list[dict], variant: str, hi: int, lo: int) -> dict:
    ro = riskoff_flags(df, variant, hi, lo).reindex(px.index).fillna(False).astype(bool)
    pos = {d: k for k, d in enumerate(px.index)}
    rows = []
    for e in eps:
        win = ro[(ro.index >= e["peak"]) & (ro.index <= e["trough"])]
        hit = win[win].index.min() if win.any() else None
        already = bool(ro.get(e["peak"], False))  # 고점에서 이미 위험회피 → 지연 계산에서 제외(정보 없음)
        rows.append({
            "already_on": already,
            "detected": None if hit is None else hit.date().isoformat(),
            "lag_from_peak": None if hit is None else pos[hit] - pos[e["peak"]],
            "vs_confirm10": None if hit is None else pos[hit] - pos[e["confirm10"]],
        })
    # 오경보: 위험회피 진입일
    onset = ro & ~ro.shift(1, fill_value=False)
    in_ep = pd.Series(False, index=px.index)
    for e in eps:
        in_ep |= (px.index >= e["peak"] - pd.Timedelta(days=30)) & (px.index <= e["trough"])
    fa = []
    for d in onset[onset].index:
        if in_ep.get(d, False):
            continue
        k = pos[d]
        fwd = px.iloc[k:k + FA_HORIZON + 1]
        mdd = float((fwd / fwd.cummax() - 1).min()) if len(fwd) > 1 else 0.0
        if mdd > FA_DD:
            fa.append({"date": d.date().isoformat(), "fwd_mdd": round(mdd, 4)})
    years = max((px.index[-1] - px.index[0]).days / 365.25, 1e-9)
    # 헛 위험회피 일수: 하락 구간(고점 30일 전 ~ 저점) 밖에서 위험회피였던 날의 비율.
    # 오경보 '횟수'는 위험회피 진입만 세므로, 오래 머무는 설계(히스테리시스)가 유리하게 보인다 → 기간으로도 본다.
    false_days = ro & ~in_ep
    lags = [r["lag_from_peak"] for r in rows if r["lag_from_peak"] is not None and not r["already_on"]]
    vs = [r["vs_confirm10"] for r in rows if r["vs_confirm10"] is not None and not r["already_on"]]
    return {
        "per_episode": rows,
        "detected": sum(r["detected"] is not None for r in rows),
        "missed": sum(r["detected"] is None for r in rows),
        "already_on": sum(r["already_on"] for r in rows),
        "median_lag_from_peak": None if not lags else float(np.median(lags)),
        "median_vs_confirm10": None if not vs else float(np.median(vs)),
        "false_alarms": len(fa),
        "false_alarms_per_year": round(len(fa) / years, 2),
        "false_alarm_dates": fa[-10:],
        "riskoff_share": round(float(ro.mean()), 3),
        "false_riskoff_share": round(float(false_days.mean()), 3),
        "riskoff_in_episodes": round(float((ro & in_ep).sum() / max(in_ep.sum(), 1)), 3),
    }


def evaluate(df: pd.DataFrame, px: pd.Series, hi: int, lo: int) -> dict:
    # 두 안을 같은 기간으로 비교: 시장 층 4개가 모두 계산되기 시작한 날부터 (200일선·52주 준비 기간 이후)
    ready = df[["raw_vix", "raw_trend", "raw_sectors", "raw_rates"]].notna().all(axis=1)
    start = ready.idxmax() if ready.any() else df.index[0]
    d = df[df.index >= start]
    p = px[(px.index >= start) & (px.index <= d.index[-1])]
    eps = episodes(p)
    return {
        "period": [p.index[0].date().isoformat(), p.index[-1].date().isoformat()],
        "episodes": [{**{k: (v.date().isoformat() if isinstance(v, pd.Timestamp) else v) for k, v in e.items()},
                      "depth": round(e["depth"], 4)} for e in eps],
        "variants": {
            "v6": {"name": "기존안 — 매크로 6개, ±3", **score_variant(d, p, eps, "v6", 3, -3)},
            "v10i": {"name": f"v0.21 — 10개, ±{hi} + 급변(즉시 해제)", **score_variant(d, p, eps, "v10i", hi, lo)},
            "v10": {"name": f"현재안 — 10개, ±{hi} + 급변(해제 히스테리시스)", **score_variant(d, p, eps, "v10", hi, lo)},
        },
        "rules": {"episode_dd": EPISODE_DD, "confirm_dd": CONFIRM_DD, "fa_horizon": FA_HORIZON, "fa_dd": FA_DD},
    }


def publish_eval(start: str = "2007-01-01", source=None, fred=None, df=None, prices=None) -> dict:
    """df·prices를 주면 다시 수집하지 않는다 (매일 배치에서 publish_macro와 같은 계산을 재사용)."""
    cfg = load_model()["macro"]
    source, fred = source or get_source(), fred or get_fred()
    if df is None:
        df, prices, _ = frame(source, fred, cfg, start=start)
    res = evaluate(df, prices[SPX].reindex(df.index).ffill(), cfg["regime_expansion_min"], cfg["regime_riskoff_max"])
    res.update(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               source=f"{source.name}+{fred.name}", note="신용(하이일드)은 최근 3년만 — 그 이전은 두 안 모두 신용 기여 0")
    EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(EVAL_PATH, res, indent=1)
    return res


def report(res: dict) -> str:
    lines = [f"국면 점수 검증 {res['period'][0]} ~ {res['period'][1]} ({res.get('source', '')})",
             f"스트레스 구간 (S&P 500 52주 고점 대비 {EPISODE_DD:.0%} 이상): {len(res['episodes'])}개"]
    vs = res["variants"]
    v6, v10 = vs["v6"], vs["v10"]
    lines.append(f"{'고점':<11} {'저점':<11} {'낙폭':>6}  {'기존안 탐지(지연)':<22} {'현재안 탐지(지연)':<22}")
    for e, a, b in zip(res["episodes"], v6["per_episode"], v10["per_episode"]):
        fmt = lambda r: ("놓침" if r["detected"] is None else ("고점 전부터 위험회피" if r["already_on"] else  # noqa: E731
                         f"{r['detected']} ({r['lag_from_peak']}일, −10% 대비 {r['vs_confirm10']:+d})"))
        lines.append(f"{e['peak']:<11} {e['trough']:<11} {e['depth']:>6.1%}  {fmt(a):<22} {fmt(b):<22}")
    for v in vs.values():
        lines.append(f"- {v['name']}: 탐지 {v['detected']}/{v['detected'] + v['missed']} (고점 전부터 {v['already_on']}), 고점→탐지 중앙 {v['median_lag_from_peak']}거래일, "
                     f"−10% 도달일 대비 중앙 {v['median_vs_confirm10']}일, 오경보 {v['false_alarms']}회({v['false_alarms_per_year']}/년), "
                     f"위험회피 비중 {v['riskoff_share']:.0%} (하락 구간 밖 {v.get('false_riskoff_share', 0):.0%}, "
                     f"하락 구간 중 {v.get('riskoff_in_episodes', 0):.0%})")
    lines.append(res.get("note", ""))
    return "\n".join(lines)


def load_eval() -> dict | None:
    return json.loads(EVAL_PATH.read_text(encoding="utf-8")) if EVAL_PATH.exists() else None
