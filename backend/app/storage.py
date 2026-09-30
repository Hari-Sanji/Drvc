"""Secure file-storage abstraction.

Files are stored under opaque random keys (never the user-supplied filename) outside any
web-served directory. The API streams bytes only after an authorization check, so internal
paths are never exposed. Swap LocalStorage for an S3/MinIO backend by implementing the same
interface.
"""
import hashlib
import os
import secrets
from pathlib import Path

from .config import STORAGE_DIR


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Invalid storage key")
        return self.root / key[:2] / key

    def new_key(self) -> str:
        return secrets.token_hex(20)

    def save(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o440)
        except OSError:
            pass

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            try:
                os.chmod(p, 0o660)
            except OSError:
                pass
            p.unlink()

    def sha256(self, key: str) -> str:
        h = hashlib.sha256()
        with open(self._path(key), "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()


storage = LocalStorage(STORAGE_DIR)
