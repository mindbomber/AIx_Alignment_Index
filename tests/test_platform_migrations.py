from pathlib import Path

from alembic.config import Config

from aix_platform.migrate import alembic_config


def test_packaged_migration_configuration(monkeypatch, tmp_path):
    database = tmp_path / "migration-command.db"
    monkeypatch.setenv("AIX_DATABASE_URL", f"sqlite:///{database.as_posix()}")
    from aix_platform.config import get_settings

    get_settings.cache_clear()
    config = alembic_config()
    assert isinstance(config, Config)
    assert Path(config.get_main_option("script_location")).is_dir()
    assert config.get_main_option("sqlalchemy.url").endswith(
        "migration-command.db"
    )
    get_settings.cache_clear()
