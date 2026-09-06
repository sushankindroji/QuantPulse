import pytest

from app.data.storage import LocalStorage, sanitize_filename


def test_sanitize_filename_strips_path_components():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/absolute/path/data.csv") == "data.csv"


def test_sanitize_filename_strips_disallowed_chars():
    result = sanitize_filename("weird name!@#.csv")
    assert " " not in result
    assert "!" not in result
    assert "@" not in result


def test_sanitize_filename_handles_empty_and_dots():
    assert sanitize_filename("") == "upload.csv"
    assert sanitize_filename(".") == "upload.csv"
    assert sanitize_filename("..") == "upload.csv"


def test_local_storage_save_and_read_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.save_bytes("test.txt", b"hello world")
    assert storage.exists("test.txt")
    assert storage.read_bytes("test.txt") == b"hello world"


def test_local_storage_confines_writes_to_root_even_with_traversal_attempt(tmp_path):
    """sanitize_filename() strips path-traversal segments before the storage
    layer ever sees them, so a traversal attempt safely lands inside the
    storage root as a plain filename rather than raising -- verify that
    containment, which is the actual security property that matters."""
    storage = LocalStorage(tmp_path)
    storage.save_bytes("../outside.txt", b"data")
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].parent == tmp_path
    assert written[0].name == "outside.txt"


def test_local_storage_path_for_returns_real_path(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.save_bytes("data.parquet", b"binary-content")
    path = storage.path_for("data.parquet")
    assert path.exists()
    assert path.read_bytes() == b"binary-content"


def test_dataset_storage_resolves_absolute_legacy_key_inside_canonical_root(tmp_path):
    storage = LocalStorage(tmp_path / "datasets")
    storage.save_bytes("ds_example.parquet", b"parquet")
    # Legacy records may contain an environment-specific absolute path. The
    # resolver must discard that environment-specific location and retain only
    # the safe filename under the canonical dataset root.
    assert storage.path_for("/data/datasets/ds_example.parquet") == (tmp_path / "datasets" / "ds_example.parquet").resolve()
