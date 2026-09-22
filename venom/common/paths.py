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

ROOT = root_path()
