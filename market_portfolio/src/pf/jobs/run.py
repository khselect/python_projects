"""배치 명령.

  python -m pf.jobs.run publish [--group semis] [--cache]   그룹 실적 반응 계산·게시
  python -m pf.jobs.run record AVGO                          실적 전 예측 기록 보관
  python -m pf.jobs.run show AVGO                            게시 JSON 요약 출력 (digest)

컨테이너: docker compose exec market-app python -m pf.jobs.run publish --group semis
"""

from __future__ import annotations

import argparse
import sys
import time

from pf.publish.ticker import load_published, publish_group, record_prediction
from pf.settings import offline


def _pct(v):
    return "—" if v is None else f"{v * 100:+.1f}%"


def show(ticker: str) -> int:
    pub = load_published(ticker)
    if pub is None:
        print(f"{ticker}: 게시 JSON 없음")
        return 1
    h1 = pub["sim"]["horizons"]["1"]
    m = pub["model"]["ticker"]
    print(f"{ticker} ({pub['group']['name']}, 기준일 {pub['asof']}, 출처 {pub['source']})")
    print(f"  다음 실적: {pub['next_event']}")
    print(f"  표본: {pub['sample']['n_events']}건 ({pub['sample']['first']} ~ {pub['sample']['last']}), 그룹 {pub['sample']['group_events']}건")
    print(f"  시나리오: " + ", ".join(
        f"{lab} {w:.0%} 평균 {_pct(mu)} 척도 {s * 100:.1f}%"
        for lab, w, mu, s in zip(m["labels"], m["weights"], m["means"], m["scales"])))
    print(f"  다음 날: P(상승) {h1['p_up']:.0%} · P(하락) {h1['p_down']:.0%} · 기대값 {_pct(h1['mean'])}"
          f" · 90% 구간 {_pct(h1['pcts']['5'])} ~ {_pct(h1['pcts']['95'])} · CVaR5 {_pct(h1['cvar5'])}")
    for h in ("5", "21", "63"):
        s = pub["sim"]["horizons"][h]
        print(f"  {h:>2}일 누적: 중앙값 {_pct(s['pcts']['50'])}, 90% 구간 {_pct(s['pcts']['5'])} ~ {_pct(s['pcts']['95'])}")
    print(f"  재현: {pub['repro']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pf.jobs.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--group", default="semis")
    p.add_argument("--cache", action="store_true", help="저장된 원천 데이터 재사용 (네트워크 호출 없음)")
    r = sub.add_parser("record")
    r.add_argument("ticker")
    s = sub.add_parser("show")
    s.add_argument("ticker")
    a = ap.parse_args(argv)

    if a.cmd == "publish":
        t0 = time.perf_counter()
        paths = publish_group(a.group, use_cache=a.cache)
        mode = "합성(PF_OFFLINE=1)" if offline() else "실데이터"
        print(f"[{mode}] {a.group}: {len(paths)}종목 게시 ({time.perf_counter() - t0:.1f}s)")
        for p in paths:
            print(f"  {p} ({p.stat().st_size / 1024:.1f}KB)")
        return 0
    if a.cmd == "record":
        print(record_prediction(a.ticker.upper()))
        return 0
    return show(a.ticker.upper())


if __name__ == "__main__":
    sys.exit(main())
