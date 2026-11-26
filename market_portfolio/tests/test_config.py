import pytest

from pf.config import Coverage, Group, load_coverage, validate_coverage


def test_coverage_is_10_groups_of_5():
    cov = load_coverage()
    assert len(cov.industry) == 10
    assert all(len(g.members) == 5 for g in cov.industry)
    assert len(cov.tickers) == 50


def test_theme_members_inside_coverage():
    cov = load_coverage()
    universe = set(cov.tickers)
    for g in cov.theme:
        assert set(g.members) <= universe


def test_defaults_reference_existing_groups():
    cov = load_coverage()
    for gid in cov.defaults["groups"]:
        cov.group(gid)


def test_theme_outside_coverage_rejected():
    ind = (Group("a", "A", "SPY", ("X", "Y"), "industry"),)
    theme = (Group("t", "T", "QQQ", ("X", "Z"), "theme"),)
    with pytest.raises(ValueError, match="커버리지 밖"):
        validate_coverage(Coverage(ind, theme, {}, {}, {}))
