import os
from pathlib import Path

# Data directory for JSON files (long-term memory)
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DEFAULT = _BACKEND_DIR / "data"
_data_dir = os.getenv("STYLEPAL_DATA_DIR", str(_DEFAULT))
DATA_DIR = Path(_data_dir)
if not DATA_DIR.is_absolute():
    # Resolve relative to project root (parent of backend)
    DATA_DIR = (_BACKEND_DIR.parent / _data_dir).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
