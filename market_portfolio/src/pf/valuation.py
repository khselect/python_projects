"""그룹 밸류에이션 — 후행(TTM) P/E·P/FCF와 괴리, 선행 P/E 누적 (IV. 그룹 상세).

Bloomberg의 선행(12M Forward) P/E·P/FCF는 컨센서스 추정치 이력이 필요해 무료 데이터로 재현할 수 없다.
대신 같은 메시지("이익은 느는데 현금흐름이 따라오지 않는다")를 후행 기준으로 확인한다.

  그룹 P/E   = Σ 시가총액 / Σ TTM 순이익
  그룹 P/FCF = Σ 시가총액 / Σ TTM FCF,  FCF = 영업현금흐름 − 설비투자
  괴리       = P/FCF − P/E   (= P/E × (이익/FCF − 1), 클수록 이익 대비 FCF가 적음)

- 분기 값은 분기 말 + report_lag_days(기본 45일) 뒤부터 반영 → 그날 몰랐던 실적을 쓰지 않는다.
- 시가총액 = 분할 반영 종가 × 분할 반영 주식수.
  보고 주식수는 분기에 따라 분할 전 값(제출 당시)일 수도, 이미 분할 반영된 값(나중 보고서에서 수정)일 수도 있다.
  분할마다 직전·직후 분기 주식수 비율을 보고 분할 비율에 가까울 때만 보정한다 (v0.22 — 항상 곱했더니
  NVDA 주식수가 이미 반영돼 있어 시가총액이 40배·10배로 부풀어 그룹 P/E가 1,000배로 나왔음, 11-28 운영).
- 분모 합이 0 이하(그룹 전체 적자·음의 FCF)면 그날 값은 비운다.
- 선행 P/E: yfinance 종목별 forwardPE·시가총액을 매일 저장(오늘부터 누적, 과거는 채울 수 없음).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pf.settings import DATA_DIR


def ttm(q: pd.DataFrame, lag_days: int = 45) -> pd.DataFrame:
    """분기 → 발표 반영일 기준 TTM 순이익·FCF·주식수. 4개 분기가 연속으로 있어야 TTM."""
    q = q.sort_index()
    out = pd.DataFrame(index=q.index)
    out["ni_ttm"] = q["net_income"].rolling(4, min_periods=4).sum()
    out["fcf_ttm"] = (q["ocf"] - q["capex"]).rolling(4, min_periods=4).sum()
    out["ocf_ttm"] = q["ocf"].rolling(4, min_periods=4).sum()
    out["capex_ttm"] = q["capex"].rolling(4, min_periods=4).sum()
    out["shares"] = q["shares"].ffill()
    out["fiscal_end"] = q.index
    out.index = q.index + pd.Timedelta(days=lag_days)
    return out.dropna(subset=["ni_ttm", "fcf_ttm", "shares"])


def split_factor(fiscal_ends: pd.DatetimeIndex, splits: pd.Series | None, shares=None) -> np.ndarray:
    """각 분기 주식수를 현재 분할 기준으로 바꾸는 배수.

    shares를 주면 분할마다 직전·직후 분기 주식수 비율로 '보고 값이 이미 분할 반영인지' 판단한다:
    비율이 분할 비율에 가까우면(로그 거리 비교) 분할 전 값 → 그 이전 분기에 비율을 곱하고, 1에 가까우면 건너뛴다.
    직후 분기가 아직 없으면(분할이 마지막 분기 뒤) 분할 전 값으로 보고 곱한다.
    """
    f = np.ones(len(fiscal_ends))
    if splits is None or splits.empty:
        return f
    sp = splits[splits > 0]
    sp.index = pd.DatetimeIndex(sp.index).tz_localize(None) if getattr(sp.index, "tz", None) else pd.DatetimeIndex(sp.index)
    ends = pd.DatetimeIndex(fiscal_ends)
    sh = None if shares is None else np.asarray(shares, dtype=float)
    for d, ratio in sp.items():
        before = np.where(ends < d)[0]
        after = np.where(ends >= d)[0]
        if not len(before) or ratio == 1:
            continue
        if sh is not None and len(after):
            a, b = sh[before[-1]], sh[after[0]]
            if a > 0 and b > 0:
                obs = np.log(b / a)
                if abs(obs - np.log(ratio)) >= abs(obs):  # 1에 더 가까움 → 이미 분할 반영된 값
                    continue
        f[before] *= ratio
    return f


def ticker_daily(close: pd.Series, q: pd.DataFrame, splits: pd.Series | None, lag_days: int = 45) -> pd.DataFrame:
    """종목 하루 단위: 시가총액, TTM 순이익·FCF (발표 반영일 이후 값 유지)."""
    t = ttm(q, lag_days)
    if t.empty:
        return pd.DataFrame(index=close.index, columns=["mcap", "ni", "fcf", "ocf", "capex"], dtype=float)
    t["shares_adj"] = t["shares"].to_numpy() * split_factor(pd.DatetimeIndex(t["fiscal_end"]), splits, t["shares"].to_numpy())
    t = t[~t.index.duplicated(keep="last")]
    al = t.reindex(close.index.union(t.index)).ffill().reindex(close.index)
    return pd.DataFrame({
        "mcap": close * al["shares_adj"],
        "ni": al["ni_ttm"], "fcf": al["fcf_ttm"], "ocf": al["ocf_ttm"], "capex": al["capex_ttm"],
    }, index=close.index)


def group_series(daily: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """종목별 일간 값 → 그룹 P/E·P/FCF·괴리·반영 종목 수 (일간)."""
    if not daily:
        return pd.DataFrame(columns=["pe", "pfcf", "gap", "n", "conv"])
    idx = sorted(set().union(*[d.index for d in daily.values()]))
    mcap = ni = fcf = ocf = capex = n = 0
    for d in daily.values():
        d = d.reindex(idx)
        ok = d[["mcap", "ni", "fcf"]].notna().all(axis=1)
        mcap = mcap + d["mcap"].where(ok, 0)
        ni = ni + d["ni"].where(ok, 0)
        fcf = fcf + d["fcf"].where(ok, 0)
        if "ocf" in d:
            ocf = ocf + d["ocf"].where(ok, 0).fillna(0)
            capex = capex + d["capex"].where(ok, 0).fillna(0)
        n = n + ok.astype(int)
    df = pd.DataFrame({"mcap": mcap, "ni": ni, "fcf": fcf, "ocf": ocf, "capex": capex, "n": n}, index=pd.DatetimeIndex(idx))
    df["pe"] = (df["mcap"] / df["ni"]).where((df["ni"] > 0) & (df["n"] > 0))
    df["pfcf"] = (df["mcap"] / df["fcf"]).where((df["fcf"] > 0) & (df["n"] > 0))
    df["gap"] = df["pfcf"] - df["pe"]
    df["conv"] = (df["fcf"] / df["ni"]).where(df["ni"] > 0)  # FCF 전환율 = FCF ÷ 순이익
    df["capex_share"] = (df["capex"] / df["ocf"]).where(df["ocf"] > 0)  # 설비투자 ÷ 영업현금흐름
    return df


def insight(df: pd.DataFrame, lookback: int = 252) -> dict | None:
    """그래프 해설용 수치 (판정 없음, 서술만). df = group_series 결과(일간, 기간 필터 후).

    1년 변화 분해: log(P/E) 변화 = log(시가총액) 변화 − log(이익) 변화 → 배수가 주가 때문에 움직였는지 이익 때문인지.
    반영 종목 수가 1년 사이 바뀌었으면 분해는 하지 않는다(구성 변화가 섞임).
    """
    d = df.dropna(subset=["pe"])
    if len(d) < 20:
        return None
    now = d.iloc[-1]
    hist = d["pe"]
    out = {
        "since": d.index[0].date().isoformat(),
        "pe": float(now["pe"]),
        "pe_pct": float((hist < now["pe"]).mean()),
        "pe_median": float(hist.median()),
        "pe_p10": float(hist.quantile(0.1)), "pe_p90": float(hist.quantile(0.9)),
        "conv": None if pd.isna(now["conv"]) else float(now["conv"]),
        "capex_share": None if pd.isna(now.get("capex_share")) else float(now["capex_share"]),
        "n": int(now["n"]),
    }
    if len(d) > lookback:
        ago = d.iloc[-1 - lookback]
        out["date_1y"] = d.index[-1 - lookback].date().isoformat()
        out["pe_1y"] = float(ago["pe"])
        out["conv_1y"] = None if pd.isna(ago["conv"]) else float(ago["conv"])
        out["capex_share_1y"] = None if pd.isna(ago.get("capex_share")) else float(ago["capex_share"])
        if int(ago["n"]) == int(now["n"]) and ago["ni"] > 0 and now["ni"] > 0:
            out["mcap_chg_1y"] = float(now["mcap"] / ago["mcap"] - 1)
            out["ni_chg_1y"] = float(now["ni"] / ago["ni"] - 1)
            out["fcf_chg_1y"] = float(now["fcf"] / ago["fcf"] - 1) if ago["fcf"] > 0 and now["fcf"] > 0 else None
    return out


# ── 선행 P/E 일별 누적 ─────────────────────────────────────
def _fwd_path() -> Path:
    d = DATA_DIR / "valuation"
    d.mkdir(parents=True, exist_ok=True)
    return d / "forward_pe.parquet"


def append_forward(snapshot: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    """snapshot: index=ticker, columns=[market_cap, forward_pe]. 같은 날짜는 덮어쓴다."""
    p = _fwd_path()
    old = pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["date", "ticker", "market_cap", "forward_pe"])
    new = snapshot.reset_index().rename(columns={"index": "ticker"})
    new["date"] = pd.Timestamp(date).normalize()
    cols = ["date", "ticker", "market_cap", "forward_pe"]
    keep = old[old["date"] != new["date"].iloc[0]] if len(old) else None
    allp = pd.concat([keep[cols], new[cols]], ignore_index=True) if keep is not None and len(keep) else new[cols].reset_index(drop=True)
    allp.to_parquet(p)
    return allp


def load_forward() -> pd.DataFrame:
    p = _fwd_path()
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["date", "ticker", "market_cap", "forward_pe"])


def group_forward_pe(fwd: pd.DataFrame, members: list[str]) -> pd.Series:
    """그룹 선행 P/E = Σ 시가총액 / Σ (시가총액 / 선행 P/E), 선행 P/E > 0 종목만."""
    f = fwd[fwd["ticker"].isin(members) & (fwd["forward_pe"] > 0) & (fwd["market_cap"] > 0)].copy()
    if f.empty:
        return pd.Series(dtype=float)
    f["earn"] = f["market_cap"] / f["forward_pe"]
    g = f.groupby("date")[["market_cap", "earn"]].sum()
    return (g["market_cap"] / g["earn"]).sort_index()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
