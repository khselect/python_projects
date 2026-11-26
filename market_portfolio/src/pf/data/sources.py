"""시세·실적일 데이터 출처.

- SyntheticSource: PF_OFFLINE=1 (기본). 네트워크 없이 결정론적 합성 데이터.
- YahooSource: yfinance. **S0(본인만 보는 단계) 개인 분석용**. 공개 표시 금지 (PLAN.md §6.3).

모든 출처는 같은 형식을 돌려준다.
  prices(tickers, start) -> DataFrame  index=거래일(naive date), columns=티커, 값=수정 종가
  earnings(ticker)       -> DataFrame  columns=[date, timing, eps_est, eps_act, surprise_pct]
                            date=발표 날짜(미국 동부 기준, naive), timing ∈ {"AMC","BMO","UNK"}
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pf.settings import offline

EARNINGS_COLUMNS = ["date", "timing", "eps_est", "eps_act", "surprise_pct"]


class Source:
    name = "base"

    def prices(self, tickers: list[str], start: str = "2012-01-01") -> pd.DataFrame:
        raise NotImplementedError

    def earnings(self, ticker: str) -> pd.DataFrame:
        raise NotImplementedError


# ── 합성 데이터 ─────────────────────────────────────────────
def _seed(name: str) -> int:
    return zlib.crc32(name.encode()) & 0x7FFFFFFF


@dataclass(frozen=True)
class SyntheticTruth:
    """합성 실적 반응의 참값 (테스트에서 모델 복원 확인용)."""

    weights: tuple[float, float, float] = (0.25, 0.45, 0.30)  # 약세, 중립, 강세
    means: tuple[float, float, float] = (-0.07, 0.005, 0.06)
    scales: tuple[float, float, float] = (0.03, 0.015, 0.03)


class SyntheticSource(Source):
    """결정론적 합성 데이터. 같은 티커·종료일이면 항상 같은 값."""

    name = "synthetic"

    def __init__(
        self,
        end: str | None = None,
        truth: SyntheticTruth = SyntheticTruth(),
        no_events: frozenset[str] | None = None,
    ):
        self.end = pd.Timestamp(end or "2026-11-25")
        self.truth = truth
        if no_events is None:  # ETF에는 실적 반응을 넣지 않는다
            from pf.config import load_coverage

            ref = load_coverage().reference_etfs
            no_events = frozenset(t for v in ref.values() for t in v)
        self.no_events = no_events

    def _calendar(self, start: str) -> pd.DatetimeIndex:
        return pd.bdate_range(start, self.end)

    def _market(self, days: pd.DatetimeIndex) -> np.ndarray:
        rng = np.random.default_rng(_seed("__market__"))
        return rng.standard_t(5, len(days)) * 0.009 + 0.0004

    def _event_dates(self, ticker: str, days: pd.DatetimeIndex) -> list[pd.Timestamp]:
        rng = np.random.default_rng(_seed(ticker + "#events"))
        offset = int(rng.integers(0, 60))
        dates, i = [], offset
        while i < len(days):
            dates.append(days[i])
            i += 63 + int(rng.integers(-3, 4))
        return dates

    def prices(self, tickers: list[str], start: str = "2012-01-01") -> pd.DataFrame:
        days = self._calendar(start)
        mkt = self._market(days)
        out = {}
        for t in tickers:
            rng = np.random.default_rng(_seed(t))
            beta = 0.8 + 0.6 * rng.random()
            ret = beta * mkt + rng.standard_t(5, len(days)) * 0.012
            # 실적 반응 (장후 발표 → 다음 거래일)
            ev = [] if t in self.no_events else self._event_dates(t, days)
            erng = np.random.default_rng(_seed(t + "#jumps"))
            w, m, s = map(np.array, (self.truth.weights, self.truth.means, self.truth.scales))
            for d in ev:
                k = erng.choice(3, p=w)
                j = days.get_loc(d) + 1
                if j < len(days):
                    ret[j] += m[k] + s[k] * erng.standard_t(6)
            out[t] = 100 * np.exp(np.cumsum(np.log1p(np.clip(ret, -0.6, None))))
        return pd.DataFrame(out, index=days)

    def earnings(self, ticker: str) -> pd.DataFrame:
        days = self._calendar("2012-01-01")
        ev = self._event_dates(ticker, days)
        rng = np.random.default_rng(_seed(ticker + "#eps"))
        rows = []
        for d in ev:
            est = round(1 + rng.random(), 2)
            act = round(est * (1 + rng.normal(0.03, 0.05)), 2)
            rows.append([d, "AMC", est, act, round((act / est - 1) * 100, 2)])
        # 다음 실적일 (미래)
        nxt = ev[-1] + pd.offsets.BDay(63)
        while nxt <= self.end:
            nxt += pd.offsets.BDay(63)
        rows.append([nxt, "AMC", round(1 + rng.random(), 2), np.nan, np.nan])
        return pd.DataFrame(rows, columns=EARNINGS_COLUMNS)


# ── yfinance ───────────────────────────────────────────────
def _pick(df: pd.DataFrame, *keys: str) -> pd.Series:
    """컬럼 이름이 버전마다 조금씩 달라도 찾는다 (대소문자·공백 무시 부분 일치)."""
    norm = {c: str(c).lower().replace(" ", "") for c in df.columns}
    for k in keys:
        k = k.lower().replace(" ", "")
        for c, n in norm.items():
            if k in n:
                return pd.to_numeric(df[c], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def _timing(ts: pd.Timestamp) -> str:
    """발표 시각(미국 동부)으로 장전·장후 판정. 시각 정보가 없으면 UNK."""
    if ts.hour == 0 and ts.minute == 0:
        return "UNK"
    hm = ts.hour * 60 + ts.minute
    if hm >= 16 * 60:
        return "AMC"
    if hm < 9 * 60 + 30:
        return "BMO"
    return "UNK"


class YahooSource(Source):
    name = "yfinance"

    def prices(self, tickers: list[str], start: str = "2012-01-01") -> pd.DataFrame:
        import yfinance as yf

        raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, threads=True)
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if not isinstance(raw.columns, pd.MultiIndex):
            close.columns = tickers
        close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
        return close[tickers].dropna(how="all")

    def earnings(self, ticker: str) -> pd.DataFrame:
        import yfinance as yf

        df = yf.Ticker(ticker).get_earnings_dates(limit=60)
        if df is None or df.empty:
            return pd.DataFrame(columns=EARNINGS_COLUMNS)
        idx = pd.DatetimeIndex(df.index)
        if idx.tz is not None:
            idx = idx.tz_convert("America/New_York")
        out = pd.DataFrame(
            {
                "date": idx.tz_localize(None).normalize() if idx.tz is not None else idx.normalize(),
                "timing": [_timing(t) for t in idx],
                "eps_est": _pick(df, "EPS Estimate").values,
                "eps_act": _pick(df, "Reported EPS").values,
                "surprise_pct": _pick(df, "Surprise").values,
            }
        )
        return out.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def get_source() -> Source:
    return SyntheticSource() if offline() else YahooSource()
