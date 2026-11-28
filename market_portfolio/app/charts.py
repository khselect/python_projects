"""Plotly 차트 (V. 종목 상세). 색: 상승 파랑 / 하락 빨강 (색각 이상에도 구분되는 발산 쌍), 범위는 단일 파랑 계열."""

from __future__ import annotations

import plotly.graph_objects as go

UP = "#257de0"
DOWN = "#ec4647"
BAND_OUTER = "#cce3fd"
BAND_INNER = "#84b9f3"
MEDIAN = "#1757ac"
INK = "#191919"
INK_2 = "#666666"
GRID = "#e6e6e6"
FONT = "Pretendard, 'Noto Sans KR', sans-serif"


def _layout(fig: go.Figure, height: int, xtitle: str, ytitle: str) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(family=FONT, size=12, color=INK_2),
        showlegend=True,
        legend=dict(orientation="h", y=1.0, x=0, yanchor="bottom", font=dict(color=INK)),
        hoverlabel=dict(bgcolor="#ffffff", font=dict(color=INK)),
        bargap=0.08,
    )
    fig.update_xaxes(title=xtitle, gridcolor=GRID, zeroline=False, ticksuffix="%", showline=False)
    fig.update_yaxes(title=ytitle, gridcolor=GRID, zeroline=False)
    return fig


def reaction_histogram(hist: dict, p5: float, p95: float, height: int = 300) -> go.Figure:
    edges = [e * 100 for e in hist["edges"]]
    mids = [(a + b) / 2 for a, b in zip(edges[:-1], edges[1:])]
    width = edges[1] - edges[0]
    dens = [d * 100 for d in hist["density"]]
    fig = go.Figure()
    for name, color, keep in (("하락", DOWN, lambda m: m < 0), ("상승", UP, lambda m: m >= 0)):
        xs = [m for m in mids if keep(m)]
        ys = [d for m, d in zip(mids, dens) if keep(m)]
        fig.add_bar(
            x=xs, y=ys, width=width * 0.92, name=name, marker=dict(color=color, line=dict(width=0)),
            hovertemplate="초과수익 %{x:.1f}%<br>비중 %{y:.2f}%<extra></extra>",
        )
    for v, label in ((p5, "5%"), (p95, "95%")):
        fig.add_vline(x=v * 100, line=dict(color=INK_2, width=1, dash="dot"),
                      annotation_text=f"{label} {v * 100:+.1f}%", annotation_font_color=INK_2,
                      annotation_position="top right" if label == "95%" else "top left",
                      annotation_yshift=-4)
    fig.add_vline(x=0, line=dict(color=INK, width=1))
    return _layout(fig, height, "다음 날 초과수익률", "시뮬레이션 비중(%)")


def fan_chart(fan: dict, height: int = 300) -> go.Figure:
    d = fan["days"]
    pc = lambda k: [v * 100 for v in fan[k]]  # noqa: E731
    fig = go.Figure()
    fig.add_scatter(x=d, y=pc("p95"), line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=d, y=pc("p5"), fill="tonexty", fillcolor=BAND_OUTER, line=dict(width=0),
                    name="5~95% 범위", hoverinfo="skip")
    fig.add_scatter(x=d, y=pc("p75"), line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=d, y=pc("p25"), fill="tonexty", fillcolor=BAND_INNER, line=dict(width=0),
                    name="25~75% 범위", hoverinfo="skip")
    fig.add_scatter(
        x=d, y=pc("p50"), line=dict(color=MEDIAN, width=2), name="중앙값",
        customdata=list(zip(pc("p5"), pc("p25"), pc("p75"), pc("p95"))),
        hovertemplate=("%{x}거래일<br>중앙값 %{y:+.1f}%<br>25~75%: %{customdata[1]:+.1f} ~ %{customdata[2]:+.1f}%"
                       "<br>5~95%: %{customdata[0]:+.1f} ~ %{customdata[3]:+.1f}%<extra></extra>"),
    )
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    fig = _layout(fig, height, "반응일부터 거래일", "누적 초과수익률")
    fig.update_xaxes(ticksuffix="", tickvals=[1, 5, 21, 42, 63])
    fig.update_yaxes(ticksuffix="%")
    fig.update_layout(hovermode="x")
    return fig


def regime_history(dates: list[str], scores: list[int], hi: int = 4, lo: int = -4, height: int = 280,
                   macro: list[int] | None = None, market: list[int] | None = None,
                   stress: list[bool] | None = None, rng: int = 10) -> go.Figure:
    """국면 점수 추이. 층별 점수(매크로·시장)를 막대로 쌓고 합계를 선으로. 급변 주는 진한 빨강 배경."""
    top = rng + 0.5
    fig = go.Figure()
    fig.add_hrect(y0=hi - 0.5, y1=top, fillcolor="#e6f0fc", line_width=0, layer="below")
    fig.add_hrect(y0=-top, y1=lo + 0.5, fillcolor="#fde8e8", line_width=0, layer="below")
    for a, b in _runs(dates, stress or []):
        fig.add_vrect(x0=a, x1=b, fillcolor="#f4b4b4", line_width=0, layer="below", opacity=0.7)
    fig.add_annotation(x=0, xref="paper", y=top - 0.4, text=f"확장 (≥ +{hi})", showarrow=False, xanchor="left",
                       font=dict(color=INK_2, size=11))
    fig.add_annotation(x=0, xref="paper", y=-top + 0.4, text=f"위험회피 (≤ {lo})", showarrow=False, xanchor="left",
                       font=dict(color=INK_2, size=11))
    if macro is not None and market is not None:
        fig.add_bar(x=dates, y=macro, name="매크로 층", marker_color="#9cc3ef",
                    hovertemplate="%{x}<br>매크로 층 %{y:+d}<extra></extra>")
        fig.add_bar(x=dates, y=market, name="시장 층", marker_color="#f6a96f",
                    hovertemplate="%{x}<br>시장 층 %{y:+d}<extra></extra>")
    fig.add_scatter(
        x=dates, y=scores, mode="lines", line=dict(color=MEDIAN, width=2, shape="hv"), name="국면 점수(합)",
        hovertemplate="%{x}<br>국면 점수 %{y:+d}<extra></extra>",
    )
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    fig = _layout(fig, height, "", "국면 점수")
    fig.update_layout(showlegend=macro is not None, barmode="relative", bargap=0.1,
                      margin=dict(l=8, r=64, t=28 if macro is not None else 8, b=8), hovermode="x unified")
    fig.update_xaxes(ticksuffix="", tickformat="%y.%m", range=[dates[0], dates[-1]])
    step = 5 if rng >= 10 else 3
    fig.update_yaxes(range=[-top, top], tickvals=list(range(-rng, rng + 1, step)))
    return fig


def regime_long(h: dict, hi: int = 4, lo: int = -4, rng: int = 10, show_spx: bool = True,
                default_years: int = 2, height: int = 380) -> go.Figure:
    """2007년 이후 국면 점수 (주간) — 기간 버튼(2년·5년·10년·전체) + 아래 드래그 스크롤바, 오른쪽 축에 S&P 500.
    처음에는 최근 default_years년만 보인다. 막대 = 층별 점수, 선 = 합계, 진한 빨강 = 급변 규칙 발동 주."""
    import pandas as pd

    dates = h["dates"]
    fig = regime_history(dates, h["score"], hi, lo, height=height, macro=h.get("macro"), market=h.get("market"),
                         stress=h.get("stress"), rng=rng)
    if show_spx and h.get("spx"):
        fig.add_scatter(x=dates, y=h["spx"], mode="lines", name="S&P 500 (오른쪽, 로그)", yaxis="y2",
                        line=dict(color="#191919", width=1.2), opacity=0.55,
                        hovertemplate="%{x}<br>S&P 500 %{y:,.0f}<extra></extra>")
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", type="log", showgrid=False, title="", tickformat=",.0f"))
    end = pd.Timestamp(dates[-1])
    start = max(pd.Timestamp(dates[0]), end - pd.DateOffset(years=default_years))
    fig.update_xaxes(
        range=[start.date().isoformat(), dates[-1]],
        rangeslider=dict(visible=True, thickness=0.08),
        rangeselector=dict(buttons=[
            dict(count=2, label="2년", step="year", stepmode="backward"),
            dict(count=5, label="5년", step="year", stepmode="backward"),
            dict(count=10, label="10년", step="year", stepmode="backward"),
            dict(step="all", label="전체"),
        ], x=0, y=1.12, font=dict(size=11)),
        tickformat="%y.%m",
    )
    fig.update_layout(margin=dict(l=8, r=56, t=56, b=8), legend=dict(orientation="h", y=1.12, x=1, xanchor="right"),
                      bargap=0.05)
    return fig


def _runs(dates: list[str], flags: list[bool]) -> list[tuple[str, str]]:
    runs, start, prev = [], None, None
    for d, f in zip(dates, flags):
        if f and start is None:
            start = d
        if not f and start is not None:
            runs.append((start, prev))
            start = None
        prev = d
    if start is not None:
        runs.append((start, prev))
    return runs


def score_breakdown(indicators: list[dict], labels: dict[str, str]) -> go.Figure:
    """지표별 기여(+1·0·−1) 막대. 층별로 묶고 0은 회색 점으로 보이게 한다."""
    names, vals, colors, text, hover = [], [], [], [], []
    for ind in indicators:
        v = ind["signal"]
        names.append(f"{ind['name']} · {labels[ind['layer']]}")
        vals.append(0.06 if v == 0 else (0 if v is None else v))
        colors.append("#bbbbbb" if v in (0, None) else (UP if v > 0 else DOWN))
        text.append("신호 없음" if v is None else {1: "+1 우호", 0: "0 중립", -1: "−1 비우호"}[int(v)])
        hover.append(ind.get("basis", ""))
    fig = go.Figure(go.Bar(y=names, x=vals, orientation="h", marker_color=colors, text=text, textposition="outside",
                           customdata=hover, hovertemplate="%{y}<br>%{text}<br>%{customdata}<extra></extra>",
                           cliponaxis=False))
    fig = _layout(fig, 34 * len(names) + 40, "", "")
    fig.update_layout(showlegend=False, margin=dict(l=8, r=72, t=8, b=8))
    fig.update_xaxes(range=[-1.5, 1.5], tickvals=[-1, 0, 1], ticktext=["−1", "0", "+1"], ticksuffix="", zeroline=True,
                     zerolinecolor=INK)
    fig.update_yaxes(autorange="reversed", ticksuffix="")
    return fig


DIVERGING = [[0.0, DOWN], [0.5, "#efefef"], [1.0, UP]]


def yield_curve(curve: dict, height: int = 230) -> go.Figure:
    """수익률 곡선: 현재·1개월 전·1년 전. x = 만기(년, 로그 간격 대신 범주)."""
    x = [f"{m}년" for m in curve["maturities"]]
    fig = go.Figure()
    style = {"현재": (MEDIAN, "solid", 3), "1개월 전": ("#f47230", "dash", 2), "1년 전": ("#999999", "dot", 2)}
    for k, (col, dash, w) in style.items():
        if any(v is not None for v in curve.get(k, [])):
            fig.add_scatter(x=x, y=curve[k], mode="lines+markers", name=k, line=dict(color=col, dash=dash, width=w),
                            hovertemplate=f"{k} %{{x}}: %{{y:.2f}}%<extra></extra>")
    fig = _layout(fig, height, "", "금리 (%)")
    fig.update_layout(margin=dict(l=8, r=8, t=28, b=8), hovermode="x unified")
    fig.update_xaxes(ticksuffix="", type="category")
    fig.update_yaxes(ticksuffix="")
    return fig


def sector_heatmap(items: list[dict], periods=("1D", "1W", "1M", "3M", "YTD", "1Y"), height: int = 380) -> go.Figure:
    """섹터 × 기간 수익률 히트맵. 열마다 범위가 달라 색은 열 안에서 비교한다(칸에 값 표기)."""
    items = sorted(items, key=lambda i: i.get("1M") or 0, reverse=True)
    names = [i["name"] + (" ▲" if (i.get("vs_ma200") or 0) > 0 else " ▽") for i in items]
    z, text = [], []
    for i in items:
        row = [None if i.get(p) is None else i[p] * 100 for p in periods]
        z.append(row)
        text.append(["" if v is None else f"{v:+.1f}" for v in row])
    # 열별 정규화: 열 안의 최대 절댓값으로 나눠 −1~1 (기간마다 변동 폭이 달라서)
    cols = list(zip(*z)) if z else []
    scale = [max([abs(v) for v in c if v is not None] or [1]) or 1 for c in cols]
    zn = [[None if v is None else v / scale[j] for j, v in enumerate(row)] for row in z]
    fig = go.Figure(go.Heatmap(z=zn, x=list(periods), y=names, text=text, texttemplate="%{text}", colorscale=DIVERGING,
                               zmin=-1, zmax=1, showscale=False, customdata=z, xgap=2, ygap=2,
                               hovertemplate="%{y} %{x}: %{customdata:+.1f}%<extra></extra>"))
    fig = _layout(fig, height, "", "")
    fig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
    fig.update_xaxes(ticksuffix="", side="top")
    fig.update_yaxes(ticksuffix="", autorange="reversed")
    return fig


DRAWDOWN = [[0.0, DOWN], [1.0, "#f4f4f4"]]  # 낙폭은 한 방향(0 이하)이라 단일 색 계열


def month_heatmap(
    years: list[int],
    values: list[list],
    bench: list[list] | None = None,
    mdd: list[list] | None = None,
    mode: str = "group",
    bench_name: str = "벤치마크",
) -> go.Figure:
    """연도×월 히트맵. mode: group(그룹 수익률) | excess(벤치마크 대비 차이) | mdd(월중 최대 낙폭).

    칸마다 값을 적어 색만으로 읽지 않게 한다. 마우스를 올리면 세 값을 모두 보여준다.
    """
    def grid(src):
        return [[None if v is None else v * 100 for v in row] for row in (src or [[None] * 12 for _ in years])]

    g, b, m = grid(values), grid(bench), grid(mdd)
    ex = [[None if gv is None or bv is None else gv - bv for gv, bv in zip(gr, br)] for gr, br in zip(g, b)]
    z, scale, zmin, zmax, zmid = {
        "group": (g, DIVERGING, -15, 15, 0),
        "excess": (ex, DIVERGING, -10, 10, 0),
        "mdd": (m, DRAWDOWN, -25, 0, None),
    }[mode]
    text = [["" if v is None else f"{v:+.1f}" for v in row] for row in z]
    fmt = lambda v: "—" if v is None else f"{v:+.1f}%"  # noqa: E731
    custom = [[[fmt(g[i][j]), fmt(b[i][j]), fmt(ex[i][j]), fmt(m[i][j])] for j in range(12)] for i in range(len(years))]
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"{k}월" for k in range(1, 13)], y=[str(y) for y in years], text=text, texttemplate="%{text}",
        customdata=custom, textfont=dict(size=11), colorscale=scale, zmin=zmin, zmax=zmax,
        **({"zmid": zmid} if zmid is not None else {}),
        xgap=2, ygap=2, colorbar=dict(title="%", thickness=10, len=0.8),
        hovertemplate=("<b>%{y}년 %{x}</b><br>그룹 %{customdata[0]}<br>" + bench_name +
                       " %{customdata[1]}<br>차이 %{customdata[2]}<br>월중 최대 낙폭 %{customdata[3]}<extra></extra>"),
    ))
    fig.update_layout(
        height=max(240, 26 * len(years) + 60), margin=dict(l=8, r=8, t=8, b=8),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff", font=dict(family=FONT, size=12, color=INK_2),
        hoverlabel=dict(bgcolor="#ffffff", font=dict(color=INK)),
    )
    fig.update_yaxes(autorange="reversed", type="category")
    fig.update_xaxes(side="top")
    return fig


def car_chart(car: dict, height: int = 300) -> go.Figure:
    d = car["days"]
    pc = lambda k: [None if v is None else v * 100 for v in car[k]]  # noqa: E731
    fig = go.Figure()
    fig.add_scatter(x=d, y=pc("p75"), line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=d, y=pc("p25"), fill="tonexty", fillcolor=BAND_OUTER, line=dict(width=0),
                    name="이벤트 25~75%", hoverinfo="skip")
    fig.add_scatter(
        x=d, y=pc("mean"), line=dict(color=MEDIAN, width=2), name="평균",
        customdata=list(zip(pc("p25"), pc("p75"))),
        hovertemplate="%{x:+d}일<br>평균 %{y:+.1f}%<br>25~75%: %{customdata[0]:+.1f} ~ %{customdata[1]:+.1f}%<extra></extra>",
    )
    fig.add_vline(x=0, line=dict(color=INK_2, width=1, dash="dot"), annotation_text="반응일",
                  annotation_position="bottom right", annotation_font_color=INK_2)
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    fig = _layout(fig, height, "반응일 기준 거래일", "누적 초과수익률")
    fig.update_layout(legend=dict(x=1, xanchor="right", y=1.0, yanchor="bottom"))
    fig.update_xaxes(ticksuffix="", tickvals=[-5, 0, 5, 21, 42, 63])
    fig.update_yaxes(ticksuffix="%")
    fig.update_layout(hovermode="x")
    return fig


SERIES_2 = {"QQQ": "#257de0", "OEF": "#f47230"}  # 범주형 1·2번 슬롯 (파랑·주황)


def _regime_runs(dates: list[str], scores: list[int], hi: int, lo: int) -> list[tuple[str, str, str]]:
    """연속된 확장·위험회피 주를 (시작, 끝, 종류) 구간으로."""
    runs, cur, start = [], None, None
    for d, s in zip(dates, scores):
        r = "up" if s >= hi else ("down" if s <= lo else None)
        if r != cur:
            if cur:
                runs.append((start, prev, cur))
            cur, start = r, d
        prev = d
    if cur:
        runs.append((start, prev, cur))
    return runs


def market_compare(m: dict, hist_dates: list[str], hist_scores: list[int], hi: int = 4, lo: int = -4,
                   height: int = 280) -> go.Figure:
    """Nasdaq-100·S&P 100 지수 비교 (시작 주 = 100, 한 축). 배경 = 국면 점수의 확장·위험회피 구간."""
    fig = go.Figure()
    for a, b, kind in _regime_runs(hist_dates, hist_scores, hi, lo):
        fig.add_vrect(x0=a, x1=b, fillcolor=BAND_OUTER if kind == "up" else "#fde8e8", line_width=0, layer="below", opacity=0.8)
    for t, ys in m["series"].items():
        fig.add_scatter(x=m["dates"], y=ys, mode="lines", name=m["names"][t], line=dict(color=SERIES_2.get(t, MEDIAN), width=2),
                        hovertemplate=f"{m['names'][t]}<br>%{{x}}: %{{y:.1f}}<extra></extra>")
        fig.add_annotation(x=m["dates"][-1], y=ys[-1], text=f"{t} {ys[-1] - 100:+.0f}%", showarrow=False, xanchor="left",
                           xshift=4, font=dict(size=11, color=INK))
    fig.add_hline(y=100, line=dict(color=INK_2, width=1, dash="dot"))
    fig = _layout(fig, height, "", "지수 (시작 = 100)")
    fig.update_layout(margin=dict(l=8, r=64, t=36, b=8), hovermode="x unified")
    fig.update_xaxes(ticksuffix="", tickformat="%y.%m", range=[hist_dates[0], hist_dates[-1]])  # 국면 점수 추이와 같은 기간
    return fig


def ratio_chart(m: dict, height: int = 180) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=m["dates"], y=m["ratio"], mode="lines", name="QQQ/OEF", line=dict(color=MEDIAN, width=2),
                    hovertemplate="%{x}: %{y:.1f}<extra></extra>")
    fig.add_hline(y=100, line=dict(color=INK_2, width=1, dash="dot"))
    fig = _layout(fig, height, "", "QQQ/OEF")
    fig.update_layout(showlegend=False, margin=dict(l=8, r=64, t=8, b=8))
    fig.update_xaxes(ticksuffix="", tickformat="%y.%m", range=[m["dates"][0], m["dates"][-1]])
    return fig


PE_COLOR, PFCF_COLOR, FWD_COLOR = "#257de0", "#f47230", "#6a4ce2"  # 범주형 1·2·7번 슬롯


def _val_range(v: dict) -> list[str]:
    t, f = v["ttm"], v.get("forward_pe") or {}
    end = max([t["dates"][-1]] + (f.get("dates") or [])[-1:])
    return [t["dates"][0], end]


def _n_marks(fig: go.Figure, v: dict, label: bool = True) -> None:
    """반영 종목 수가 바뀐 주에 점선 — 그날의 계단 변화는 밸류에이션이 아니라 구성 변화."""
    for c in v.get("n_changes") or []:
        fig.add_vline(x=c["date"], line=dict(color=INK_2, width=1, dash="dot"))
        if label:
            fig.add_annotation(x=c["date"], y=1, yref="paper", text=f"{c['n']}종목", showarrow=False, yanchor="bottom",
                               font=dict(size=10, color=INK_2))


def valuation_chart(v: dict, height: int = 300) -> go.Figure:
    """그룹 후행 P/E·P/FCF (한 축, 둘 다 배수) + 선행 P/E(오늘부터 누적)."""
    t = v["ttm"]
    fig = go.Figure()
    fig.add_scatter(x=t["dates"], y=t["pe"], mode="lines", name="P/E (후행 12개월)", line=dict(color=PE_COLOR, width=2),
                    hovertemplate="%{x}<br>P/E %{y:.1f}배<extra></extra>")
    fig.add_scatter(x=t["dates"], y=t["pfcf"], mode="lines", name="P/FCF (후행 12개월)", line=dict(color=PFCF_COLOR, width=2),
                    hovertemplate="%{x}<br>P/FCF %{y:.1f}배<extra></extra>")
    f = v.get("forward_pe") or {}
    if f.get("values"):
        fig.add_scatter(x=f["dates"], y=f["values"], mode="lines+markers", name="선행 P/E (누적 중)",
                        line=dict(color=FWD_COLOR, width=2, dash="dot"), marker=dict(size=8),
                        hovertemplate="%{x}<br>선행 P/E %{y:.1f}배<extra></extra>")
    for name, ys, col in (("P/E", t["pe"], PE_COLOR), ("P/FCF", t["pfcf"], PFCF_COLOR)):
        last = next((y for y in reversed(ys) if y is not None), None)
        if last is not None:
            fig.add_annotation(x=t["dates"][-1], y=last, text=f"{name} {last:.1f}", showarrow=False, xanchor="left",
                               xshift=4, font=dict(size=11, color=col))
    _n_marks(fig, v)
    fig = _layout(fig, height, "", "배수 (배)")
    fig.update_layout(margin=dict(l=8, r=76, t=36, b=8), hovermode="x unified")
    fig.update_xaxes(ticksuffix="", tickformat="%y", range=_val_range(v))
    return fig


def valuation_gap_chart(v: dict, height: int = 200) -> go.Figure:
    """괴리 = P/FCF − P/E. 0보다 크면 이익보다 FCF가 적은 상태, 커질수록 이익과 현금의 괴리 확대."""
    t = v["ttm"]
    conv = [None if c is None else c * 100 for c in t["conv"]]
    fig = go.Figure()
    fig.add_scatter(x=t["dates"], y=t["gap"], mode="lines", name="괴리 (P/FCF − P/E)", fill="tozeroy",
                    line=dict(color=PFCF_COLOR, width=1.5), fillcolor="rgba(244,114,48,0.15)", customdata=conv,
                    hovertemplate="%{x}<br>괴리 %{y:+.1f}배<br>FCF 전환율 %{customdata:.0f}%<extra></extra>")
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    _n_marks(fig, v, label=False)
    fig = _layout(fig, height, "", "P/FCF − P/E")
    fig.update_layout(showlegend=False, margin=dict(l=8, r=76, t=8, b=8))
    fig.update_xaxes(ticksuffix="", tickformat="%y", range=_val_range(v))
    return fig
