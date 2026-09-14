from __future__ import annotations

from pathlib import Path

import pytest

from teic.settings import DaemonSettings, Settings


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "teic_test.db"
    return Settings(daemon=DaemonSettings(db_path=str(db_path)))
