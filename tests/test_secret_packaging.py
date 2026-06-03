import os
from utils import get_writeable_path
from aegis.core.paths import Paths

def test_secret_path_resolves_under_data_root():
    paths = Paths()
    resolved = get_writeable_path(".env.enc")
    assert resolved == str(paths.root / ".env.enc")
    
    resolved_env = get_writeable_path(".env")
    assert resolved_env == str(paths.root / ".env")

def test_build_script_and_spec_do_not_bundle_env():
    # Verify build_exe.py has no conditional inclusion of .env or .env.enc in cmd
    build_script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build_exe.py")
    if os.path.exists(build_script_path):
        with open(build_script_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check that `--add-data` with `.env` or `.env.enc` is not added to cmd
        # The old line was: cmd.extend(["--add-data", ".env.enc;."])
        assert "--add-data" not in content or ".env.enc;." not in content
        assert ".env;." not in content

    # Verify AegisOptimizer.spec datas section has no .env or .env.enc
    spec_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AegisOptimizer.spec")
    if os.path.exists(spec_path):
        with open(spec_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Parse AegisOptimizer.spec contents for datas
        # It shouldn't contain .env or .env.enc
        assert ".env.enc" not in content
        # Note: it might contain '.env' in '.environ' but let's check for '.env' inside the datas list
        # We can extract the datas block or do a simple check
        import re
        datas_match = re.search(r"datas\s*=\s*(\[.*?\])", content, re.DOTALL)
        if datas_match:
            datas_str = datas_match.group(1)
            assert ".env" not in datas_str
            assert ".env.enc" not in datas_str
