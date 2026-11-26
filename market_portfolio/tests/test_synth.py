from pf.synth.rules import check_wording, synthesize


def macro(score):
    return {"score": score, "regime": "확장" if score >= 3 else ("위험회피" if score <= -3 else "중립·전환"), "regime_since": "2026-10-01"}


def group(median):
    return {"group": {"name": "반도체"}, "car": {"car21": {"median": median, "p5": -0.15, "p95": 0.18, "n": 278}}}


def ticker(p_down, p5):
    return {"ticker": "AVGO", "next_event": {"date": "2026-12-09"}, "gate": {"status": "참고용"},
            "sim": {"horizons": {"1": {"p_down": p_down, "p_up": 1 - p_down, "pcts": {"5": p5}}}}}


def test_layer_mapping():
    v = synthesize(macro(3), group(0.006), ticker(0.35, -0.07))
    assert [l.value for l in v.layers] == [1, 1, 1] and v.code == "agree_pos"
    v = synthesize(macro(-3), group(-0.01), ticker(0.65, -0.05))
    assert [l.value for l in v.layers] == [-1, -1, -1] and v.code == "agree_neg"


def test_ticker_tail_rule_overrides_probability():
    v = synthesize(None, None, ticker(0.30, -0.16))  # 하락 확률 낮아도 꼬리가 −15% 이하면 비우호
    assert v.layers[2].value == -1


def test_conflict_upper_layer_first():
    v = synthesize(macro(-4), group(0.02), ticker(0.4, -0.08))
    assert v.code == "conflict" and "매크로" in v.title


def test_partial_and_neutral():
    assert synthesize(macro(4), group(0.001), ticker(0.5, -0.08)).code == "partial"
    assert synthesize(macro(1), group(0.0), ticker(0.5, -0.08)).code == "neutral"


def test_missing_data():
    v = synthesize(None, None, None)
    assert v.code == "none"
    v = synthesize(macro(-3), None, None)
    assert v.code == "agree_neg"  # 자료 있는 층만으로 판단


def test_all_templates_pass_wording_check():
    cases = [(3, 0.01, (0.3, -0.05)), (-3, -0.01, (0.7, -0.2)), (-4, 0.02, (0.4, -0.08)), (4, 0.0, (0.5, -0.08)), (0, 0, (0.5, -0.08))]
    for s, g, t in cases:
        v = synthesize(macro(s), group(g), ticker(*t))
        for txt in [v.title, v.text, *[l.basis for l in v.layers]]:
            assert check_wording(txt) == [], txt
