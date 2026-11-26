import json

import pytest

import pf.data.store as store
import pf.publish.ticker as pub
from pf.data.sources import SyntheticSource


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pub, "PUBLISH_DIR", tmp_path / "publish" / "ticker")
    monkeypatch.setattr(pub, "PRED_DIR", tmp_path / "predictions")
    return tmp_path


def test_publish_semis_offline_and_record(tmp_data):
    paths = pub.publish_group("semis", source=SyntheticSource())
    assert {p.stem for p in paths} == {"NVDA", "AVGO", "AMD", "MU", "QCOM"}
    for p in paths:
        assert p.stat().st_size < 50 * 1024  # 게시 용량 기준 (PLAN.md 비기능 요구사항)
    d = pub.load_published("AVGO")
    assert d["gate"]["status"] == "참고용"
    assert d["sample"]["n_events"] >= 20
    assert set(d["sim"]["horizons"]) == {"1", "5", "21", "63"}
    assert len(d["sim"]["fan"]["p50"]) == 63
    assert d["repro"]["data_hash"] and d["repro"]["config_hash"]

    rec = pub.record_prediction("AVGO")
    body = json.loads(rec.read_text(encoding="utf-8"))
    assert body["event"] == d["next_event"] and body["outcome"] is None
    # 같은 실적·기준일 기록은 덮어쓰지 않는다
    assert pub.record_prediction("AVGO") == rec


def test_publish_is_reproducible(tmp_data):
    pub.publish_group("semis", source=SyntheticSource())
    a = pub.load_published("NVDA")
    pub.publish_group("semis", source=SyntheticSource(), use_cache=True)
    b = pub.load_published("NVDA")
    assert a["sim"]["horizons"] == b["sim"]["horizons"]
    assert a["repro"]["data_hash"] == b["repro"]["data_hash"]


def test_missing_ticker_skipped_not_whole_group(tmp_data):
    """한 종목 시세가 비어도 그룹의 나머지는 게시된다 (2026-11-26 ISRG 사례)."""
    import numpy as np

    class MissingISRG(SyntheticSource):
        def prices(self, tickers, start="2012-01-01"):
            px = super().prices(tickers, start)
            if "ISRG" in px:
                px["ISRG"] = np.nan
            return px

    skipped = []
    paths = pub.publish_group("healthcare", source=MissingISRG(), skipped=skipped)
    assert {p.stem for p in paths} == {"LLY", "UNH", "JNJ", "ABBV"}
    assert skipped == ["ISRG: 시세 없음"]
