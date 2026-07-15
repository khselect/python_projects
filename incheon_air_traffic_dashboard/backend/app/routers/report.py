"""종합 리포트 API — LLM/추론 없이 DB에 적재된 데이터만 집계해 리포트를 생성.

모든 문장은 집계 수치를 고정 템플릿에 채워 넣은 것으로, 통계적 사실만 서술한다.
상관계수 해석("약한/뚜렷한" 등)도 고정 구간표(|r| 기준) 분류이며 모델 추론이 아니다.
"""
from __future__ import annotations
import datetime as dt
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analysis, crud, models
from ..database import get_db

router = APIRouter(prefix="/api/report", tags=["report"])


def _corr_word(r: float) -> str:
    a = abs(r)
    direction = "양(+)" if r >= 0 else "음(-)"
    if a < 0.2:
        strength = "거의 없는"
    elif a < 0.4:
        strength = "약한"
    elif a < 0.6:
        strength = "중간 수준의"
    elif a < 0.8:
        strength = "뚜렷한"
    else:
        strength = "매우 강한"
    return f"{strength} {direction} 상관"


@router.get("")
def report(db: Session = Depends(get_db)):
    stations = crud.get_all_stations(db)
    st_by_id = {s.id: s for s in stations}
    summary = crud.get_dataset_summary(db)
    pm_months = [d["month"] for d in summary["pm25"]]
    tr_periods = [d["period"] for d in summary["traffic"]]

    # ---------- PM2.5 집계 ----------
    pm_rows = db.execute(select(models.PM25Hourly.station_id,
                                 models.PM25Hourly.ts,
                                 models.PM25Hourly.value)).all()
    pm_station_vals: dict[int, list[float]] = defaultdict(list)
    pm_month_vals: dict[str, list[float]] = defaultdict(list)
    pm_hour_vals: dict[int, list[float]] = defaultdict(list)
    over35 = 0
    for sid, ts, v in pm_rows:
        pm_station_vals[sid].append(v)
        pm_month_vals[ts.strftime("%Y-%m")].append(v)
        pm_hour_vals[ts.hour].append(v)
        if v > 35:
            over35 += 1

    def _avg(vs):
        return sum(vs) / len(vs) if vs else 0.0

    pm25 = None
    if pm_rows:
        station_avgs = sorted(
            ({"station": st_by_id[sid].name, "avg": round(_avg(vs), 1)}
             for sid, vs in pm_station_vals.items() if sid in st_by_id),
            key=lambda d: d["avg"], reverse=True,
        )
        hour_avgs = sorted(
            ({"hour": h, "avg": round(_avg(vs), 1)} for h, vs in pm_hour_vals.items()),
            key=lambda d: d["avg"], reverse=True,
        )
        pm25 = {
            "months": pm_months,
            "overall_avg": round(_avg([v for _, _, v in pm_rows]), 1),
            "over35_ratio": round(100.0 * over35 / len(pm_rows), 1),
            "monthly": [{"month": m, "avg": round(_avg(vs), 1)}
                         for m, vs in sorted(pm_month_vals.items())],
            "top_stations": station_avgs[:5],
            "bottom_stations": station_avgs[-5:][::-1],
            "peak_hours": hour_avgs[:3],
            "clean_hours": hour_avgs[-3:][::-1],
        }

    # ---------- 통행량 집계 ----------
    tr_rows = db.execute(select(models.TrafficHourly.station_id,
                                 models.TrafficHourly.period_label,
                                 models.TrafficHourly.hour_label,
                                 models.TrafficHourly.count)).all()
    traffic = None
    if tr_rows:
        period_total: dict[str, int] = defaultdict(int)
        period_station: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        period_hour: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for sid, period, hlabel, cnt in tr_rows:
            period_total[period] += cnt
            period_station[period][sid] += cnt
            period_hour[period][hlabel] += cnt

        per_period = []
        for p in tr_periods:
            top_st = sorted(period_station[p].items(), key=lambda kv: kv[1], reverse=True)[:5]
            top_hr = sorted(period_hour[p].items(), key=lambda kv: kv[1], reverse=True)[:3]
            per_period.append({
                "period": p,
                "total": period_total[p],
                "top_stations": [{"station": st_by_id[sid].name, "total": n}
                                  for sid, n in top_st if sid in st_by_id],
                "peak_hours": [{"hour_label": h, "total": n} for h, n in top_hr],
            })
        change = None
        if len(tr_periods) >= 2:
            prev_p, last_p = tr_periods[-2], tr_periods[-1]
            prev_t, last_t = period_total[prev_p], period_total[last_p]
            if prev_t:
                change = {"from": prev_p, "to": last_p,
                          "pct": round(100.0 * (last_t - prev_t) / prev_t, 1),
                          "diff": last_t - prev_t}
        traffic = {"periods": tr_periods, "per_period": per_period, "period_change": change}

    # ---------- 교차 상관 (역별 PM2.5 평균 × 통행량 총량, 최신 기준월) ----------
    cross = None
    if pm_rows and tr_rows:
        latest = tr_periods[-1]
        xs, ys = [], []
        for s in stations:
            if not s.has_pm25 or s.id not in pm_station_vals:
                continue
            total = sum(cnt for sid2, p, _, cnt in tr_rows
                        if sid2 == s.id and p == latest)
            if total:
                xs.append(_avg(pm_station_vals[s.id]))
                ys.append(float(total))
        corr = analysis.pearson(xs, ys)
        cross = {"period": latest, "stations": len(xs),
                 "correlation": round(corr, 4), "interpretation": _corr_word(corr)}

    # ---------- 템플릿 기반 요약 문장 (모두 위 집계값 대입, 추론 없음) ----------
    findings: list[str] = []
    findings.append(
        f"분석 대상은 인천 1호선 {len(stations)}개 역이며, PM2.5 측정소 보유 역은 "
        f"{sum(1 for s in stations if s.has_pm25)}곳입니다. 적재 데이터: PM2.5 {len(pm_months)}개월"
        f"({', '.join(pm_months) if pm_months else '-'}), 통행량 {len(tr_periods)}개월"
        f"({', '.join(tr_periods) if tr_periods else '-'})."
    )
    if pm25:
        top, bot = pm25["top_stations"][0], pm25["bottom_stations"][0]
        findings.append(
            f"PM2.5 전체 평균은 {pm25['overall_avg']}㎍/㎥이며, 역별 평균이 가장 높은 곳은 "
            f"{top['station']}({top['avg']}㎍/㎥), 가장 낮은 곳은 {bot['station']}({bot['avg']}㎍/㎥)입니다."
        )
        findings.append(
            f"환경기준(35㎍/㎥) 초과 시간 비율은 전체 측정 시간의 {pm25['over35_ratio']}%입니다. "
            f"시간대별 평균은 {pm25['peak_hours'][0]['hour']}시({pm25['peak_hours'][0]['avg']}㎍/㎥)가 "
            f"가장 높고 {pm25['clean_hours'][0]['hour']}시({pm25['clean_hours'][0]['avg']}㎍/㎥)가 가장 낮습니다."
        )
        if len(pm25["monthly"]) >= 2:
            ms = ", ".join(f"{d['month']} {d['avg']}㎍/㎥" for d in pm25["monthly"])
            findings.append(f"월별 PM2.5 평균: {ms}.")
    if traffic:
        last = traffic["per_period"][-1]
        findings.append(
            f"통행량({last['period']})은 총 {last['total']:,}명이며, 최다 역은 "
            f"{last['top_stations'][0]['station']}({last['top_stations'][0]['total']:,}명), "
            f"피크 시간대는 {last['peak_hours'][0]['hour_label']}"
            f"({last['peak_hours'][0]['total']:,}명)입니다."
        )
        ch = traffic["period_change"]
        if ch:
            updown = "증가" if ch["diff"] >= 0 else "감소"
            findings.append(
                f"{ch['from']} 대비 {ch['to']} 통행량은 {abs(ch['diff']):,}명 "
                f"({abs(ch['pct'])}%) {updown}했습니다."
            )
    if cross:
        findings.append(
            f"역별 PM2.5 평균과 통행량 총량({cross['period']} 기준, {cross['stations']}개 역) 사이에는 "
            f"상관계수 r={cross['correlation']:.2f}로 {cross['interpretation']}이 관측됩니다. "
            f"(고정 구간표 분류이며 인과관계를 의미하지 않습니다.)"
        )
    if not pm_rows and not tr_rows:
        findings.append("적재된 데이터가 없습니다. '데이터 업로드·관리' 탭에서 원본 엑셀을 업로드하세요.")

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "datasets": summary,
        "pm25": pm25,
        "traffic": traffic,
        "cross": cross,
        "findings": findings,
    }
