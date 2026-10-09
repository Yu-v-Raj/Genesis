"""DATABASE_URL resolution: precedence and working-directory independence."""

import pytest

from backend.app.core.core_services.config.constants import PROJECT_ROOT
from backend.app.core.core_services.config.settings import Settings


def test_relative_sqlite_path_is_anchored_to_the_project_root(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: './genesis.db' must be the same file for uvicorn, Alembic, and scripts."""
    monkeypatch.chdir(tmp_path)

    url = Settings(DATABASE_URL="sqlite+aiosqlite:///./genesis.db", _env_file=None).DATABASE_URL

    assert url == f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'genesis.db').resolve()}"


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:////var/tmp/genesis.db",
        "sqlite+aiosqlite:///:memory:",
        "postgresql+asyncpg://genesis:secret@db.example.com:5432/genesis",
    ],
)
def test_absolute_memory_and_server_urls_are_unchanged(url: str) -> None:
    assert Settings(DATABASE_URL=url, _env_file=None).DATABASE_URL == url


def test_process_environment_overrides_the_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Documents precedence: an exported DATABASE_URL wins over .env, which wins over the default."""
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=sqlite+aiosqlite:////var/tmp/from-env-file.db\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings(_env_file=env_file).DATABASE_URL.endswith("from-env-file.db")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:////var/tmp/from-shell.db")
    assert Settings(_env_file=env_file).DATABASE_URL.endswith("from-shell.db")
