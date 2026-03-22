import sys
from pathlib import Path

# Ensure imports resolve as `neveredit.*` when tests run from package dir.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
