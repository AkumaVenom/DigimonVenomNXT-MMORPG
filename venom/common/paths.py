"""Stable external data layout for source and frozen Windows executables."""
from pathlib import Path
import os
import sys

def root_path() -> Path:
    override = os.environ.get('VENOM_ROOT')
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]

def asset_path(relative: str) -> Path:
    root = root_path()
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Asset path escapes game directory')
    return result


def mysql_data_path(root=None) -> Path:
    """The production save directory must travel with this server directory."""
    base = Path(root or root_path()).resolve()
    result = (base / "mysql" / "data").resolve()
    if not result.is_relative_to(base):
        raise ValueError("MySQL data must remain inside the Digimon Venom NXT directory.")
    return result

ROOT = root_path()
