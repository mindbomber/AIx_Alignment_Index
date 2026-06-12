from __future__ import annotations

import argparse

from alembic import command
from alembic.config import Config

from aix.io import data_directory

from .config import get_settings


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(data_directory("migrations")))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the AIx platform database")
    subparsers = parser.add_subparsers(dest="command", required=True)
    upgrade = subparsers.add_parser("upgrade")
    upgrade.add_argument("revision", nargs="?", default="head")
    downgrade = subparsers.add_parser("downgrade")
    downgrade.add_argument("revision", nargs="?", default="-1")
    subparsers.add_parser("check")
    subparsers.add_parser("current")
    args = parser.parse_args()
    config = alembic_config()
    if args.command == "upgrade":
        command.upgrade(config, args.revision)
    elif args.command == "downgrade":
        command.downgrade(config, args.revision)
    elif args.command == "check":
        command.check(config)
    else:
        command.current(config)
