"""config/*.yaml 로드와 검증."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from pf.settings import CONFIG_DIR


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    benchmark: str
    members: tuple[str, ...]
    kind: str  # "industry" | "theme"


@dataclass(frozen=True)
class Coverage:
    industry: tuple[Group, ...]
    theme: tuple[Group, ...]
    reference_etfs: dict[str, list[str]]
    defaults: dict
    limits: dict

    @property
    def groups(self) -> tuple[Group, ...]:
        return self.industry + self.theme

    @property
    def tickers(self) -> list[str]:
        """커버리지 종목 (산업 그룹 구성 종목, 중복 제거, 순서 유지)."""
        seen: dict[str, None] = {}
        for g in self.industry:
            for t in g.members:
                seen.setdefault(t, None)
        return list(seen)

    def group(self, group_id: str) -> Group:
        for g in self.groups:
            if g.id == group_id:
                return g
        raise KeyError(group_id)


def _read(name: str, config_dir: Path | None = None) -> dict:
    path = (config_dir or CONFIG_DIR) / name
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _groups(raw: list[dict], kind: str) -> tuple[Group, ...]:
    return tuple(
        Group(g["id"], g["name"], g["benchmark"], tuple(g["members"]), kind) for g in raw
    )


def load_coverage(config_dir: Path | None = None) -> Coverage:
    raw = _read("coverage.yaml", config_dir)
    cov = Coverage(
        industry=_groups(raw["industry_groups"], "industry"),
        theme=_groups(raw.get("theme_groups", []), "theme"),
        reference_etfs=raw.get("reference_etfs", {}),
        defaults=raw.get("defaults", {}),
        limits=raw.get("limits", {}),
    )
    validate_coverage(cov)
    return cov


def validate_coverage(cov: Coverage) -> None:
    """§6.2 규칙 위반 시 ValueError."""
    ids = [g.id for g in cov.groups]
    if len(ids) != len(set(ids)):
        raise ValueError("그룹 id 중복")
    all_members = [t for g in cov.industry for t in g.members]
    if len(all_members) != len(set(all_members)):
        raise ValueError("한 종목이 여러 산업 그룹에 속함")
    universe = set(all_members)
    for g in cov.theme:
        outside = set(g.members) - universe
        if outside:
            raise ValueError(f"테마 그룹 {g.id}에 커버리지 밖 종목: {sorted(outside)}")
    for gid in cov.defaults.get("groups", []):
        if gid not in ids:
            raise ValueError(f"기본 그룹 {gid}이 정의되지 않음")


def load_model() -> dict:
    return _read("model.yaml")


def load_overview() -> dict:
    """I. 시장 개요 패널 구성."""
    return _read("overview.yaml")


def load_glossary() -> dict:
    return _read("glossary.yaml")
