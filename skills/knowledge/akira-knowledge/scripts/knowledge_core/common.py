from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Sequence


class BootstrapError(RuntimeError):
    pass


def _vault_root(vault: Path) -> Path:
    root = vault.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise BootstrapError(f"Vault does not exist or is not a directory: {vault}")
    return root


def _safe_relative(root: Path, value: str, *, must_exist: bool) -> tuple[str, Path]:
    raw = Path(value)
    if raw.is_absolute():
        raise BootstrapError(f"Vault-relative path required: {value}")
    candidate = root / raw
    try:
        resolved = candidate.resolve(strict=must_exist)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise BootstrapError(f"Path escapes Vault or cannot be resolved: {value}") from exc
    return relative.as_posix() if relative.as_posix() else ".", resolved


def _within_scope(locator: str, scopes: Sequence[str]) -> bool:
    path = Path(locator)
    for scope in scopes:
        if scope == ".":
            return True
        scope_path = Path(scope)
        if path == scope_path or scope_path in path.parents:
            return True
    return False


def _write_atomic(path: Path, text: str) -> None:
    mode = (path.stat().st_mode & 0o7777) if path.exists() else 0o644
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
