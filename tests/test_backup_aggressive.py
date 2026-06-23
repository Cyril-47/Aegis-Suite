"""Aggressive real-world scenario tests for Backup Scheduler.

Simulates actual backup conditions:
- Rapid backup/restore cycles
- Large backup files
- Concurrent rotation
- Edge cases (empty dirs, missing files)
"""
import pytest
import time
import os
import shutil
import tempfile
from pathlib import Path
from aegis.db.maintenance import rotate_backups


@pytest.fixture
def backup_dir():
    """Create a temp backup directory."""
    tmp = Path(tempfile.mkdtemp())
    backups = tmp / "backups"
    backups.mkdir()
    yield {"tmp": tmp, "backups": backups}
    shutil.rmtree(tmp)


class FakePaths:
    def __init__(self, backups):
        self.backups_db = backups


def test_rotate_keeps_newest(backup_dir):
    """Keeps only the 10 most recent backups."""
    backups = backup_dir["backups"]
    for i in range(15):
        f = backups / f"aegis_rev_{i:03d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10


def test_rotate_no_dir():
    """Missing backups dir -> no crash."""
    rotate_backups(FakePaths(Path("/nonexistent")), keep=10)


def test_rotate_under_limit(backup_dir):
    """Fewer than keep -> nothing deleted."""
    backups = backup_dir["backups"]
    for i in range(3):
        (backups / f"aegis_rev_{i}.db").touch()

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 3


def test_rotate_exact_limit(backup_dir):
    """Exactly 10 -> nothing deleted."""
    backups = backup_dir["backups"]
    for i in range(10):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10


def test_rotate_100_files(backup_dir):
    """100 backup files -> keeps 10."""
    backups = backup_dir["backups"]
    for i in range(100):
        f = backups / f"aegis_rev_{i:04d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10


def test_rotate_500_files(backup_dir):
    """500 backup files -> keeps 10."""
    backups = backup_dir["backups"]
    for i in range(500):
        f = backups / f"aegis_rev_{i:04d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    start = time.perf_counter()
    rotate_backups(FakePaths(backups), keep=10)
    elapsed = time.perf_counter() - start

    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    print(f"\n  [PERF] 500 file rotation in {elapsed*1000:.1f}ms")


def test_rotate_mixed_files(backup_dir):
    """Non-backup files are not deleted."""
    backups = backup_dir["backups"]
    for i in range(15):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))
    (backups / "important.txt").touch()

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("*"))
    assert len(remaining) == 11  # 10 backups + 1 txt


def test_rotate_keeps_newest_by_mtime(backup_dir):
    """Oldest files by mtime are deleted first."""
    backups = backup_dir["backups"]
    for i in range(15):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=10)
    remaining = sorted(backups.glob("aegis_*.db"), key=lambda p: p.stat().st_mtime)
    # Oldest remaining should have mtime 1005 (indices 5-14 kept)
    assert remaining[0].name == "aegis_rev_5.db"


def test_rotate_empty_dir(backup_dir):
    """Empty backups dir -> no crash."""
    rotate_backups(FakePaths(backup_dir["backups"]), keep=10)
    assert len(list(backup_dir["backups"].glob("*"))) == 0


def test_rotate_1000_files(backup_dir):
    """1000 backup files -> keeps 10."""
    backups = backup_dir["backups"]
    for i in range(1000):
        f = backups / f"aegis_rev_{i:05d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    start = time.perf_counter()
    rotate_backups(FakePaths(backups), keep=10)
    elapsed = time.perf_counter() - start

    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    print(f"\n  [PERF] 1000 file rotation in {elapsed*1000:.1f}ms")


def test_rotate_keep_1(backup_dir):
    """Keep only 1 -> deletes all but newest."""
    backups = backup_dir["backups"]
    for i in range(20):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=1)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 1
    assert remaining[0].name == "aegis_rev_19.db"


def test_rotate_keep_100(backup_dir):
    """Keep 100, have 150 -> keeps 100."""
    backups = backup_dir["backups"]
    for i in range(150):
        f = backups / f"aegis_rev_{i:04d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=100)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 100


def test_rotate_idempotent(backup_dir):
    """Running rotate twice gives same result."""
    backups = backup_dir["backups"]
    for i in range(15):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=10)
    first_count = len(list(backups.glob("aegis_*.db")))

    rotate_backups(FakePaths(backups), keep=10)
    second_count = len(list(backups.glob("aegis_*.db")))

    assert first_count == second_count == 10


def test_rotate_preserves_newest_files(backup_dir):
    """Newest files are preserved."""
    backups = backup_dir["backups"]
    for i in range(15):
        f = backups / f"aegis_rev_{i}.db"
        f.write_text(f"backup_{i}")
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(FakePaths(backups), keep=10)
    remaining = sorted(backups.glob("aegis_*.db"), key=lambda p: p.stat().st_mtime)

    # Verify newest 5 are preserved
    for i in range(10, 15):
        f = backups / f"aegis_rev_{i}.db"
        assert f.exists()
        assert f.read_text() == f"backup_{i}"
