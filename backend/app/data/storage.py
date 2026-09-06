"""
Storage abstraction for uploaded datasets and derived Parquet files.

`LocalStorage` is used for local development and for the default Docker
Compose setup (backed by a bind-mounted volume, so it survives container
restarts). The interface is deliberately storage-engine-agnostic so a
production deployment (e.g. Render, where the filesystem is ephemeral) can
swap in an S3-compatible backend without touching any calling code --
only `get_storage()` needs to change.

To add a new backend later:
    class S3Storage(StorageBackend): ...
and switch it in `get_storage()` based on an environment variable
(e.g. QP_STORAGE_BACKEND=s3). No other module should construct a
storage backend directly.
"""
from __future__ import annotations

import abc
import os
import re
import uuid
from pathlib import Path

from app.config import DATA_DIR

UPLOADS_DIR = DATA_DIR / "uploads"
DATASETS_DIR = DATA_DIR / "datasets"  # converted, validated Parquet files
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
DATASETS_DIR.mkdir(parents=True, exist_ok=True)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_filename(filename: str) -> str:
    """Strip any path components and disallowed characters. Prevents path
    traversal (`../../etc/passwd`) and keeps only a safe basename."""
    base = os.path.basename(filename or "upload.csv")
    base = _SAFE_NAME_RE.sub("_", base)
    if not base or base in (".", ".."):
        base = "upload.csv"
    return base[:200]


def new_dataset_id() -> str:
    return f"ds_{uuid.uuid4().hex[:12]}"


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def save_bytes(self, key: str, data: bytes) -> str:
        """Persist raw bytes under `key`. Returns a storage-backend-specific
        locator (a local path today; an S3 URI for a future backend)."""

    @abc.abstractmethod
    def read_bytes(self, key: str) -> bytes:
        ...

    @abc.abstractmethod
    def path_for(self, key: str) -> Path:
        """Local filesystem path usable by pandas/pyarrow. For remote
        backends this would need to download to a temp file first --
        acceptable for this project's scope, documented here for clarity."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        ...


class LocalStorage(StorageBackend):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # sanitize_filename already strips path traversal; belt-and-suspenders
        # re-check here since this is the actual filesystem boundary.
        safe_key = sanitize_filename(key)
        resolved = (self.root / safe_key).resolve()
        if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
            raise ValueError("Invalid storage key (path traversal attempt).")
        return resolved

    def save_bytes(self, key: str, data: bytes) -> str:
        path = self._resolve(key)
        path.write_bytes(data)
        return str(path)

    def read_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def path_for(self, key: str) -> Path:
        return self._resolve(key)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()


_uploads_storage: StorageBackend | None = None
_datasets_storage: StorageBackend | None = None


def get_uploads_storage() -> StorageBackend:
    global _uploads_storage
    if _uploads_storage is None:
        _uploads_storage = LocalStorage(UPLOADS_DIR)
    return _uploads_storage


def get_datasets_storage() -> StorageBackend:
    """Return the single canonical storage backend for registered datasets."""
    global _datasets_storage
    if _datasets_storage is None:
        _datasets_storage = LocalStorage(DATASETS_DIR)
    return _datasets_storage


def resolve_dataset_path(storage_key: str) -> Path:
    """Resolve a registry storage key to the canonical dataset location.

    Registry records intentionally store only a portable key (normally
    ``<dataset_id>.parquet``), never an environment-specific absolute path.
    Older records may contain an absolute/relative path; only the basename is
    retained so it is still resolved under the canonical datasets directory.
    """
    if not storage_key:
        raise ValueError("Dataset registry entry has no storage key.")
    path = get_datasets_storage().path_for(storage_key)
    return path


def require_dataset_path(storage_key: str) -> Path:
    """Resolve and verify that a registered dataset file actually exists."""
    path = resolve_dataset_path(storage_key)
    if not path.is_file():
        raise FileNotFoundError(
            f"registered dataset file is unavailable for storage key "
            f"'{sanitize_filename(storage_key)}'. Re-import the dataset to restore it."
        )
    if path.stat().st_size <= 0:
        raise FileNotFoundError(
            f"Registered dataset file is empty for storage key "
            f"'{sanitize_filename(storage_key)}'. Re-import the dataset to restore it."
        )
    return path
