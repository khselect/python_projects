"""원천 데이터 캐시 (Parquet). 화면은 이 파일을 직접 읽지 않는다 — publish JSON만 읽는다."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from pf.settings import DATA_DIR


def _dir(source: str) -> Path:
    d = DATA_DIR / "raw" / source
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_prices(source: str, df: pd.DataFrame) -> Path:
    p = _dir(source) / "prices.parquet"
    df.to_parquet(p)
    return p


def load_prices(source: str) -> pd.DataFrame | None:
    p = _dir(source) / "prices.parquet"
    return pd.read_parquet(p) if p.exists() else None


def save_earnings(source: str, ticker: str, df: pd.DataFrame) -> Path:
    p = _dir(source) / f"earnings_{ticker}.parquet"
    df.to_parquet(p)
    return p


def load_earnings(source: str, ticker: str) -> pd.DataFrame | None:
    p = _dir(source) / f"earnings_{ticker}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def frame_hash(*frames: pd.DataFrame) -> str:
    """재현성 기록용 데이터 해시 (내용 기준, 12자리)."""
    h = hashlib.sha256()
    for f in frames:
        h.update(pd.util.hash_pandas_object(f, index=True).values.tobytes())
    return h.hexdigest()[:12]
