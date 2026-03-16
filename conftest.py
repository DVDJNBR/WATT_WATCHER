import sys
from pathlib import Path

# Make `shared` importable from tests (mirrors the deployed functions/ root)
sys.path.insert(0, str(Path(__file__).parent / "functions"))
