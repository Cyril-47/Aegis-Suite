import os
import time
from unittest.mock import MagicMock
from aegis.core.paths import Paths
from aegis.db.maintenance import rotate_backups
from aegis.web.routes.wizard import list_backups


def test_rotate_backups_by_mtime(tmp_path):
    """Verify that rotate_backups sorts and retains backups strictly by st_mtime.

    We create backups with mixed revision names where lexicographical sorting
    is different from chronological sorting, and explicitly set st_mtime.
    """
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    # We want to keep 2 backups
    # Create 3 files:
    # 1. aegis_revC_oldest.db - oldest by modification time (time_now - 100), but comes last alphabetically
    # 2. aegis_revA_newest.db - newest by modification time (time_now), comes first alphabetically
    # 3. aegis_revB_middle.db - middle by modification time (time_now - 50), alphabetically in the middle
    #
    # If we sorted lexicographically:
    #   Sorted: revA (newest), revB (middle), revC (oldest)
    #   With keep=2: we keep revB and revC (or revA and revB depending on asc/desc, but one of the newest is dropped/kept incorrectly)
    # With st_mtime sort:
    #   Sorted (asc): revC (oldest), revB (middle), revA (newest)
    #   With keep=2: we keep revB and revA (the newest ones), and delete revC (the oldest).
    
    now = time.time()
    
    f1 = paths.backups_db / "aegis_revC_20260601_110000.db"
    f2 = paths.backups_db / "aegis_revA_20260601_130000.db"
    f3 = paths.backups_db / "aegis_revB_20260601_120000.db"
    
    for f in (f1, f2, f3):
        f.write_text("dummy content")
        
    # Explicitly modify utime to set st_mtime
    os.utime(f1, (now - 100, now - 100)) # oldest
    os.utime(f2, (now, now))             # newest
    os.utime(f3, (now - 50, now - 50))   # middle
    
    # Run rotation keeping 2
    rotate_backups(paths, keep=2)
    
    # Verify what remains
    retained = [f.name for f in paths.backups_db.glob("aegis_*.db")]
    
    # Should keep revA (newest) and revB (middle), and delete revC (oldest)
    assert len(retained) == 2
    assert "aegis_revA_20260601_130000.db" in retained
    assert "aegis_revB_20260601_120000.db" in retained
    assert "aegis_revC_20260601_110000.db" not in retained


def test_list_backups_by_mtime(tmp_path):
    """Verify that list_backups endpoint returns files from newest to oldest by st_mtime."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    now = time.time()
    
    f1 = paths.backups_db / "aegis_revZ_20260601_100000.db"
    f2 = paths.backups_db / "aegis_revA_20260601_120000.db"
    f3 = paths.backups_db / "aegis_revM_20260601_110000.db"
    
    for f in (f1, f2, f3):
        f.write_text("dummy")
        
    # Set st_mtime:
    # f1 (revZ) -> oldest (now - 200)
    # f2 (revA) -> newest (now)
    # f3 (revM) -> middle (now - 100)
    os.utime(f1, (now - 200, now - 200))
    os.utime(f2, (now, now))
    os.utime(f3, (now - 100, now - 100))
    
    # Mock FastAPI request
    request = MagicMock()
    request.app.state.core.paths = paths
    
    result = list_backups(request)
    
    # Result must be sorted from newest to oldest: [f2, f3, f1]
    assert result == [
        "aegis_revA_20260601_120000.db",
        "aegis_revM_20260601_110000.db",
        "aegis_revZ_20260601_100000.db"
    ]
