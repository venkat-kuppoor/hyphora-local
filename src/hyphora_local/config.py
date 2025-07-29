from dataclasses import dataclass
from pathlib import Path

# import tomllib
from typing import Literal

CONFIG_DIR_NAME = ".hyphora"
VAULT_DIR_NAME = "hyphora-vault-test"
CONFIG_FILE_NAME = "hyphora.toml"
DB_FILE_NAME = "hyphora.db"


@dataclass(frozen=True)
class HyphoraConfig:
    vault_path: Path
    db_path: Path


ConfigResult = tuple[Literal["ok"], HyphoraConfig] | tuple[Literal["error"], str]


def load_hyphora_config(project_root: Path | None = None) -> ConfigResult:
    if project_root is None:
        project_root = Path.cwd()

    config_path = project_root / CONFIG_FILE_NAME
    vault_path = project_root / VAULT_DIR_NAME
    db_path = project_root / CONFIG_DIR_NAME / DB_FILE_NAME

    if not config_path.exists():
        return ("error", f"Missing config file: {config_path}")

    if not vault_path.exists():
        return ("error", f"Missing vault folder: {vault_path}")

    if not vault_path.exists():
        return ("error", f"Missing db file: {db_path}")

    return (
        "ok",
        HyphoraConfig(
            vault_path=vault_path.resolve(),
            db_path=db_path.resolve(),
        ),
    )
    # try:
    #     with config_path.open("rb") as f:
    #         data = tomllib.load(f)
    # except (OSError, tomllib.TOMLDecodeError) as e:
    #     return ("error", f"Failed to read or parse config file: {e}")

    # relative_vault_path: object = data.get("vault_path")
    # match relative_vault_path:
    #     case path if isinstance(path, str):
    #         full_vault_path = project_root / Path(path)
    #
    #         return (
    #             "ok",
    #             HyphoraConfig(
    #                 vault_path=full_vault_path.resolve(),
    #             ),
    #         )
    #     case None:
    #         return ("error", f"Missing required 'vault_path' field in {config_path}")
    #     case other:
    #         return (
    #             "error",
    #             f"'vault_path' must be a string, got {type(other).__name__}",
    #         )
