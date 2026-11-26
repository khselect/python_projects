"""FRED 시계열 (PLAN.md §6.1, §6.3).

공개 화면 고지: "This product uses the FRED® API but is not endorsed or certified by the
Federal Reserve Bank of St. Louis." + FRED API 약관 링크.
ICE BofA 시리즈(BAMLH0A0HYM2)는 제3자 공개 금지 → 값은 내부 계산 전용, 화면에는 신호만.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from pf.settings import offline

API = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    "DFEDTARU": "연방기금 목표금리 상단",
    "GDP": "명목 GDP (분기)",
    "BAMLH0A0HYM2": "하이일드 스프레드 (ICE BofA, 내부 계산 전용)",
    "T10Y2Y": "장단기 금리차 10Y−2Y",
    "DTWEXBGS": "광의 달러지수 (연준)",
}
INTERNAL_ONLY = {"BAMLH0A0HYM2"}

NOTICE = (
    "This product uses the FRED® API but is not endorsed or certified by the "
    "Federal Reserve Bank of St. Louis."
)
TERMS_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"


class FredError(RuntimeError):
    pass


class FredClient:
    name = "fred"

    def __init__(self, api_key: str | None = None, timeout: float = 30):
        self.api_key = api_key or os.environ.get("FRED_API_KEY", "").strip()
        if not self.api_key:
            raise FredError("FRED_API_KEY 없음 — market-app/.env에 설정")
        self.timeout = timeout

    def series(self, series_id: str, start: str = "2012-01-01") -> pd.Series:
        q = urllib.parse.urlencode(
            {"series_id": series_id, "api_key": self.api_key, "file_type": "json", "observation_start": start}
        )
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=self.timeout) as r:
                body = json.load(r)
        except Exception as e:  # 키를 메시지에 남기지 않는다
            raise FredError(f"{series_id} 수집 실패: {type(e).__name__}") from None
        obs = body.get("observations", [])
        s = pd.Series(
            [np.nan if o["value"] in (".", "") else float(o["value"]) for o in obs],
            index=pd.to_datetime([o["date"] for o in obs]),
            name=series_id,
        )
        return s.sort_index()

    def frame(self, ids: list[str], start: str = "2012-01-01") -> dict[str, pd.Series]:
        return {i: self.series(i, start) for i in ids}


class SyntheticFred:
    """오프라인 합성 매크로 시계열 (결정론적)."""

    name = "synthetic"

    def __init__(self, end: str = "2026-11-25"):
        self.end = pd.Timestamp(end)

    def frame(self, ids: list[str], start: str = "2012-01-01") -> dict[str, pd.Series]:
        days = pd.bdate_range(start, self.end)
        n = len(days)
        rng = np.random.default_rng(20261126)
        t = np.arange(n)
        out = {}
        # 기준금리: 0.25 → 인상기 → 동결 → 인하 (계단)
        rate = np.clip(0.25 + 5.25 / (1 + np.exp(-(t - n * 0.65) / (n * 0.03))) - 1.0 * (t > n * 0.9), 0.25, None)
        out["DFEDTARU"] = pd.Series(np.round(rate * 4) / 4, index=days)
        # 명목 GDP: 분기, 연 4~6% 성장 + 순환
        q = pd.date_range(pd.Timestamp(start).to_period("Q").start_time, self.end, freq="QS")
        g = 0.012 + 0.006 * np.sin(np.arange(len(q)) / 3) + rng.normal(0, 0.002, len(q))
        out["GDP"] = pd.Series(18000 * np.cumprod(1 + g), index=q)
        # 하이일드 스프레드: 최근 3년만 (FRED 제공 범위와 같게)
        hy = 4 + np.cumsum(rng.normal(0, 0.03, n))
        hy = pd.Series(np.clip(hy - (hy.mean() - 4), 2.5, 9), index=days)
        out["BAMLH0A0HYM2"] = hy[hy.index >= self.end - pd.DateOffset(years=3)]
        # 장단기 금리차: 역전 구간 포함
        out["T10Y2Y"] = pd.Series(1.2 * np.cos(t / (n / 5)) + rng.normal(0, 0.05, n), index=days)
        # 달러지수
        out["DTWEXBGS"] = pd.Series(110 * np.exp(np.cumsum(rng.normal(0.00005, 0.003, n))), index=days)
        return {i: out[i] for i in ids}


def get_fred():
    return SyntheticFred() if offline() else FredClient()
