"""Plotly 차트 (④ 종목 상세). 색: 상승 파랑 / 하락 빨강 (색각 이상에도 구분되는 발산 쌍), 범위는 단일 파랑 계열."""

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


def regime_history(dates: list[str], scores: list[int], hi: int = 3, lo: int = -3, height: int = 260) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=hi - 0.5, y1=6.5, fillcolor="#e6f0fc", line_width=0, layer="below")
    fig.add_hrect(y0=-6.5, y1=lo + 0.5, fillcolor="#fde8e8", line_width=0, layer="below")
    fig.add_annotation(x=0, xref="paper", y=6.2, text=f"확장 (≥ +{hi})", showarrow=False, xanchor="left",
                       font=dict(color=INK_2, size=11))
    fig.add_annotation(x=0, xref="paper", y=-6.2, text=f"위험회피 (≤ {lo})", showarrow=False, xanchor="left",
                       font=dict(color=INK_2, size=11))
    fig.add_scatter(
        x=dates, y=scores, mode="lines", line=dict(color=MEDIAN, width=2, shape="hv"), name="국면 점수",
        hovertemplate="%{x}<br>국면 점수 %{y:+d}<extra></extra>",
    )
    fig.add_hline(y=0, line=dict(color=INK, width=1))
    fig = _layout(fig, height, "", "국면 점수")
    fig.update_layout(showlegend=False, margin=dict(l=8, r=8, t=8, b=8), hovermode="x")
    fig.update_xaxes(ticksuffix="", tickformat="%y.%m")
    fig.update_yaxes(range=[-6.5, 6.5], tickvals=[-6, -3, 0, 3, 6])
    return fig
