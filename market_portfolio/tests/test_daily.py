import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import pf.data.store as store
import pf.jobs.run as run
import pf.jobs.scheduler as sched
import pf.publish.ticker as pub
from pf.config import load_model
from pf.data.sources import SyntheticSource

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(pub, "PUBLISH_DIR", tmp_path / "publish" / "ticker")
    monkeypatch.setattr(pub, "PRED_DIR", tmp_path / "predictions")
    monkeypatch.setattr(run, "PUBLISH_DIR", tmp_path / "publish" / "ticker")
    monkeypatch.setattr(run, "STATUS", tmp_path / "publish" / "status.json")
    import pf.macro.publish as mpub

    monkeypatch.setattr(mpub, "MACRO_PATH", tmp_path / "publish" / "macro.json")
    import pf.publish.group as gpub

    monkeypatch.setattr(gpub, "GROUP_DIR", tmp_path / "publish" / "group")
    monkeypatch.setattr(gpub, "CALENDAR_PATH", tmp_path / "publish" / "calendar.json")
    cfg = load_model()
    cfg["simulation"]["n_iter"] = 20_000  # 테스트 속도
    monkeypatch.setattr(pub, "load_model", lambda: cfg)
    monkeypatch.setattr(pub, "get_source", lambda: SyntheticSource())
    return tmp_path


def test_daily_publishes_all_industry_groups(tmp_data):
    assert run.daily() == 0
    st = json.loads((tmp_data / "publish" / "status.json").read_text(encoding="utf-8"))
    assert st["ok"] and len(st["groups"]) == 10 and st["macro"]["ok"]
    assert (tmp_data / "publish" / "macro.json").exists()
    assert st["group_pages"]["ok"]
    groups = sorted(p.stem for p in (tmp_data / "publish" / "group").glob("*.json"))
    assert len(groups) == 11 and "bigtech" in groups  # 산업 10 + 테마 1
    g = json.loads((tmp_data / "publish" / "group" / "semis.json").read_text(encoding="utf-8"))
    assert g["car"]["n_events"] > 100 and len(g["car"]["mean"]) == 69
    assert len(g["heatmap"]["years"]) >= 10
    for f in (tmp_data / "publish" / "group").glob("*.json"):
        assert f.stat().st_size < 50 * 1024
    cal = json.loads((tmp_data / "publish" / "calendar.json").read_text(encoding="utf-8"))
    assert len(cal["groups"]) == 11
    assert all(0 <= e["days"] <= 84 for grp in cal["groups"] for e in grp["events"])
    assert len(list((tmp_data / "publish" / "ticker").glob("*.json"))) == 50
    assert not list((tmp_data / "publish" / "ticker").glob("*.tmp"))


def test_due_events_and_auto_record(tmp_data, monkeypatch):
    pub.publish_group("semis", source=SyntheticSource())
    d = pub.load_published("AVGO")
    # AVGO 다음 실적을 기준일 3일 뒤로 바꿔 자동 기록 대상이 되게 한다
    d["next_event"]["date"] = (datetime.fromisoformat(d["asof"]) + timedelta(days=3)).date().isoformat()
    pub._write_json(pub.PUBLISH_DIR / "AVGO.json", d)
    assert "AVGO" in pub.due_events()
    monkeypatch.setattr(run, "publish_all", lambda: {"source": "synthetic", "asof": d["asof"], "groups": {}})
    run.daily()
    st = run.last_status()
    assert any(r.startswith("AVGO_") for r in st["recorded"])


def test_earnings_cache_reused_within_max_age(tmp_data):
    calls = []

    class Counting(SyntheticSource):
        def earnings(self, t):
            calls.append(t)
            return super().earnings(t)

    src = Counting()
    pub.fetch_earnings(src, "AVGO", max_age_days=3)
    pub.fetch_earnings(src, "AVGO", max_age_days=3)
    pub.fetch_earnings(src, "AVGO", max_age_days=None)
    assert calls == ["AVGO", "AVGO"]


def test_next_run_and_ran_today(tmp_data):
    now = datetime(2026, 12, 9, 6, 0, tzinfo=KST)
    assert sched.next_run(now, "07:15") == datetime(2026, 12, 9, 7, 15, tzinfo=KST)
    assert sched.next_run(now.replace(hour=8), "07:15") == datetime(2026, 12, 10, 7, 15, tzinfo=KST)
    assert not sched.ran_today(now, "07:15")
    st = run.STATUS
    st.parent.mkdir(parents=True, exist_ok=True)
    # 어제 07:30에 끝난 배치 → 오늘 06:00 기준으로는 '최근 슬롯(어제 07:15) 이후' 실행됨
    pub._write_json(st, {"finished_at": datetime(2026, 12, 8, 7, 30, tzinfo=KST).isoformat()})
    assert sched.ran_today(now, "07:15")
    # 오늘 08:00 기준 → 오늘 07:15 슬롯 이후 실행 기록 없음
    assert not sched.ran_today(now.replace(hour=8), "07:15")


def test_start_reason_reruns_after_code_change(tmp_data):
    now = datetime(2026, 12, 9, 8, 0, tzinfo=KST)
    st = run.STATUS
    st.parent.mkdir(parents=True, exist_ok=True)
    done = datetime(2026, 12, 9, 7, 20, tzinfo=KST).isoformat()
    # 오늘 이미 돌았고 코드도 같으면 기다린다
    pub._write_json(st, {"finished_at": done, "code_hash": run.code_hash()})
    assert sched.start_reason(now, "07:15") is None
    # 오늘 돌았어도 코드가 바뀌었으면 바로 실행
    pub._write_json(st, {"finished_at": done, "code_hash": "old0000"})
    assert "코드·설정 변경" in sched.start_reason(now, "07:15")
    # 예전 status.json (code_hash 없음)도 다시 실행
    pub._write_json(st, {"finished_at": done})
    assert sched.start_reason(now, "07:15") is not None


def test_daily_records_code_hash(tmp_data):
    run.daily()
    assert run.last_status()["code_hash"] == run.code_hash()
