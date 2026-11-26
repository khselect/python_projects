"""환경 변수와 경로. 모든 모듈은 여기서만 설정을 읽는다."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("PF_CONFIG_DIR", ROOT / "config"))
DATA_DIR = Path(os.environ.get("PF_DATA_DIR", ROOT / "data"))


def offline() -> bool:
    """PF_OFFLINE=1 이면 합성 데이터만 쓴다 (네트워크·API 키 불필요)."""
    return os.environ.get("PF_OFFLINE", "1") == "1"
