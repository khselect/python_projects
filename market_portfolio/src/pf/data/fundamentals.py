"""분기 재무제표 (밸류에이션용) — Alpha Vantage CASH_FLOW·BALANCE_SHEET.

종목당 2회 호출. 무료 키는 하루 25회라 대기열로 나눠 받는다(하루 예산 기본 20회, 우선 그룹부터).
값은 분기 단위(누적 아님): netIncome, operatingCashflow, capitalExpenditures(양수), commonStockSharesOutstanding.
보고 주식수는 액면분할 전 값 그대로라 밸류에이션 계산 때 분할 이력으로 맞춘다(pf.valuation).

Alpha Vantage 무료 키는 개인·비상업 용도 — S0(비공개) 단계 전용 (PLAN.md §6.3).
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from pf.settings import DATA_DIR, offline

API = "https://www.alphavantage.co/query"
COLUMNS = ["net_income", "ocf", "capex", "shares"]


class RateLimited(RuntimeError):
    """오늘 호출 한도 소진 — 대기열을 멈추고 다음 날 이어서."""


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


class AlphaVantageFundamentals:
    name = "alphavantage"

    def __init__(self, api_key: str | None = None, timeout: float = 30, pause: float = 1.2):
        self.api_key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("ALPHAVANTAGE_API_KEY 없음 — market-app/.env에 설정")
        self.timeout, self.pause = timeout, pause

    def _get(self, function: str, symbol: str) -> dict:
        q = urllib.parse.urlencode({"function": function, "symbol": symbol, "apikey": self.api_key})
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=self.timeout) as r:
                body = json.load(r)
        except Exception as e:  # 키를 메시지에 남기지 않는다
            raise RuntimeError(f"{symbol} {function} 수집 실패: {type(e).__name__}") from None
        time.sleep(self.pause)  # 초당 호출 제한 대비
        if "Note" in body or ("Information" in body and "quarterlyReports" not in body):
            raise RateLimited(f"Alpha Vantage 호출 한도 ({symbol} {function})")
        if "Error Message" in body:
            raise ValueError(f"{symbol} {function}: 종목 없음 또는 요청 오류")
        return body

    def quarterly(self, symbol: str) -> pd.DataFrame:
        cf = self._get("CASH_FLOW", symbol).get("quarterlyReports", [])
        bs = self._get("BALANCE_SHEET", symbol).get("quarterlyReports", [])
        a = pd.DataFrame({
            "fiscal_end": [r["fiscalDateEnding"] for r in cf],
            "net_income": [_num(r.get("netIncome")) for r in cf],
            "ocf": [_num(r.get("operatingCashflow")) for r in cf],
            "capex": [abs(_num(r.get("capitalExpenditures"))) for r in cf],
        })
        b = pd.DataFrame({
            "fiscal_end": [r["fiscalDateEnding"] for r in bs],
            "shares": [_num(r.get("commonStockSharesOutstanding")) for r in bs],
        })
        df = a.merge(b, on="fiscal_end", how="outer")
        df["fiscal_end"] = pd.to_datetime(df["fiscal_end"])
        return df.set_index("fiscal_end").sort_index()[COLUMNS]


class SyntheticFundamentals:
    """오프라인 합성 분기 재무 — 이익은 꾸준히 늘고, 최근 2년 설비투자가 커져 FCF가 이익을 덜 따라오는 모양."""

    name = "synthetic"

    def __init__(self, end: str = "2026-09-30"):
        self.end = pd.Timestamp(end)

    def quarterly(self, symbol: str) -> pd.DataFrame:
        rng = np.random.default_rng(zlib.crc32(symbol.encode()) & 0x7FFFFFFF)
        q = pd.date_range("2012-03-31", self.end, freq="QE")
        n = len(q)
        scale = 1.0e9 * (0.8 + 0.6 * rng.random())  # 최근 분기 순이익 — 합성 주가(100 근처)×주식수와 맞춰 P/E 20~40배
        growth = 1 + 0.025 + 0.01 * rng.random()
        ni = scale * growth ** (np.arange(n) - (n - 1)) * (1 + rng.normal(0, 0.08, n))
        ocf = ni * (1.25 + rng.normal(0, 0.05, n))
        capex_share = 0.18 + 0.45 * np.clip((np.arange(n) - (n - 10)) / 10, 0, 1)  # 최근 10분기 설비투자 급증
        capex = ocf * capex_share
        shares = 1e9 * (1 + rng.random()) * (0.995 ** np.arange(n))
        return pd.DataFrame({"net_income": ni, "ocf": ocf, "capex": capex, "shares": shares}, index=q.rename("fiscal_end"))


def get_fundamentals():
    return SyntheticFundamentals() if offline() else AlphaVantageFundamentals()


# ── 캐시·대기열 ────────────────────────────────────────────
def _dir():
    d = DATA_DIR / "raw" / "fundamentals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _meta_path():
    return _dir() / "_meta.json"


def load_meta() -> dict:
    p = _meta_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load(symbol: str) -> pd.DataFrame | None:
    p = _dir() / f"{symbol}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def save(symbol: str, df: pd.DataFrame, source: str) -> None:
    df.to_parquet(_dir() / f"{symbol}.parquet")
    meta = load_meta()
    meta[symbol] = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": source,
                    "quarters": int(len(df))}
    _meta_path().write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def due(symbols: list[str], max_age_days: float, now: datetime | None = None) -> list[str]:
    """받아야 할 종목 (캐시 없음 → 오래된 순). 순서는 symbols(우선순위) 유지."""
    now = now or datetime.now(timezone.utc)
    meta = load_meta()
    missing = [s for s in symbols if s not in meta or load(s) is None]
    stale = [s for s in symbols if s in meta and s not in missing
             and (now - datetime.fromisoformat(meta[s]["fetched_at"])).days >= max_age_days]
    return missing + sorted(stale, key=lambda s: meta[s]["fetched_at"])


def refresh(symbols: list[str], client=None, call_budget: int = 20, max_age_days: float = 90) -> dict:
    """우선순위대로 받을 종목을 하루 호출 예산 안에서 받는다 (종목당 2회)."""
    client = client or get_fundamentals()
    todo = due(symbols, max_age_days)
    done, failed, stopped = [], {}, None
    calls = 0
    for s in todo:
        if calls + 2 > call_budget:
            break
        try:
            df = client.quarterly(s)
            calls += 2
            if df.dropna(how="all").empty:
                failed[s] = "빈 재무제표"
                continue
            save(s, df, client.name)
            done.append(s)
        except RateLimited as e:
            stopped = str(e)
            break
        except Exception as e:
            calls += 2
            failed[s] = f"{type(e).__name__}: {e}"
    have = [s for s in symbols if load(s) is not None]
    return {"fetched": done, "failed": failed, "stopped": stopped, "calls": calls,
            "remaining": [s for s in symbols if s not in have], "have": len(have), "total": len(symbols)}
