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

    def close_and_splits(self, tickers: list[str], start: str = "2014-01-01") -> tuple[pd.DataFrame, dict[str, pd.Series]]:
        """밸류에이션용: 분할만 반영한 종가(배당 미반영)와 종목별 분할 이력."""
        raise NotImplementedError

    def forward_snapshot(self, tickers: list[str]) -> pd.DataFrame:
        """오늘의 종목별 시가총액·선행 P/E. index=ticker, columns=[market_cap, forward_pe]."""
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


# 합성 지수·선물의 마지막 값 (⓪ 시장 개요 화면이 그럴듯하게 보이도록 수준만 맞춘다)
SYNTH_LEVELS = {
    "^GSPC": 6700, "^NDX": 24500, "^DJI": 46500, "^KS11": 3900, "^KQ11": 880,
    "DX-Y.NYB": 99, "KRW=X": 1420, "CL=F": 61, "BZ=F": 65, "GC=F": 3950, "SI=F": 47, "HG=F": 5.0, "NG=F": 4.2,
}


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

            from pf.config import load_overview

            ref = load_coverage().reference_etfs
            ov = {i["symbol"] for p in load_overview()["panels"].values() for i in p["items"]}
            no_events = frozenset({t for v in ref.values() for t in v} | ov)
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

    ORIGIN = "2005-01-03"  # 시작일과 무관하게 같은 경로를 만들고 잘라낸다 (⓪·① 화면의 같은 종목 값이 일치하도록)

    def prices(self, tickers: list[str], start: str = "2012-01-01") -> pd.DataFrame:
        full = self._prices(tickers, min(pd.Timestamp(start), pd.Timestamp(self.ORIGIN)))
        return full[full.index >= pd.Timestamp(start)]

    def _prices(self, tickers: list[str], start) -> pd.DataFrame:
        days = self._calendar(start)
        mkt = self._market(days)
        out = {}
        for t in tickers:
            rng = np.random.default_rng(_seed(t))
            beta = 0.8 + 0.6 * rng.random()
            idio = 0.003 if t.startswith("^") or "=" in t or t.startswith("DX-") else 0.012  # 지수·선물은 분산된 바스켓
            ret = beta * mkt + rng.standard_t(5, len(days)) * idio
            # 실적 반응 (장후 발표 → 다음 거래일)
            ev = [] if t in self.no_events else self._event_dates(t, days)
            erng = np.random.default_rng(_seed(t + "#jumps"))
            w, m, s = map(np.array, (self.truth.weights, self.truth.means, self.truth.scales))
            for d in ev:
                k = erng.choice(3, p=w)
                j = days.get_loc(d) + 1
                if j < len(days):
                    ret[j] += m[k] + s[k] * erng.standard_t(6)
            if t == "^VIX":  # 변동성 지수: 시장 21일 실현변동성(연율) × 1.15 + 소음
                rv = pd.Series(mkt).rolling(21, min_periods=5).std().bfill().to_numpy() * np.sqrt(252) * 100
                out[t] = np.clip(rv * 1.15 + 2 + rng.normal(0, 0.8, len(days)), 9, None)
                continue
            out[t] = 100 * np.exp(np.cumsum(np.log1p(np.clip(ret, -0.6, None))))
            if t in SYNTH_LEVELS:
                out[t] = out[t] * SYNTH_LEVELS[t] / out[t][-1]
        return pd.DataFrame(out, index=days)

    def close_and_splits(self, tickers, start="2014-01-01"):
        return self.prices(tickers, start), {}

    def forward_snapshot(self, tickers):
        rows = {}
        for t in tickers:
            rng = np.random.default_rng(_seed(t + "#fwd"))
            rows[t] = {"market_cap": 1e11 * (1 + 20 * rng.random()), "forward_pe": 18 + 20 * rng.random()}
        return pd.DataFrame.from_dict(rows, orient="index")

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
        close = close.reindex(columns=tickers)
        # 일괄 다운로드에서 빠진 종목은 한 번 더 개별로 받는다 (Yahoo 일시 오류 대비)
        for t in [t for t in tickers if close[t].notna().sum() == 0]:
            try:
                one = yf.download(t, start=start, auto_adjust=True, progress=False)
                col = one["Close"]
                col = col[t] if isinstance(col, pd.DataFrame) else col
                col.index = pd.DatetimeIndex(col.index).tz_localize(None).normalize()
                close[t] = col.reindex(close.index)
            except Exception:
                pass  # 그래도 없으면 publish 단계에서 그 종목만 건너뛰고 경고
        return close.dropna(how="all")

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


def _yahoo_close_and_splits(tickers: list[str], start: str) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    import yfinance as yf

    raw = yf.download(tickers, start=start, auto_adjust=False, progress=False, threads=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].set_axis(tickers, axis=1)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None).normalize()
    splits = {}
    for t in tickers:
        try:
            sp = yf.Ticker(t).splits
            if sp is not None and len(sp):
                sp.index = pd.DatetimeIndex(sp.index).tz_localize(None)
                splits[t] = sp
        except Exception:
            pass
    return close.reindex(columns=tickers), splits


def _yahoo_forward_snapshot(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    rows = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info or {}
            rows[t] = {"market_cap": float(info.get("marketCap") or np.nan),
                       "forward_pe": float(info.get("forwardPE") or np.nan)}
        except Exception:
            continue
    return pd.DataFrame.from_dict(rows, orient="index", columns=["market_cap", "forward_pe"])


YahooSource.close_and_splits = lambda self, tickers, start="2014-01-01": _yahoo_close_and_splits(tickers, start)
YahooSource.forward_snapshot = lambda self, tickers: _yahoo_forward_snapshot(tickers)


def get_source() -> Source:
    return SyntheticSource() if offline() else YahooSource()
