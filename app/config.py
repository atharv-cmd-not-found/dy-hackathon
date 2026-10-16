import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
CASES_DIR = DATA_DIR / "cases"
MODELS_DIR = BASE_DIR / "models"
EVAL_DIR = BASE_DIR / "eval"

# Ensure directories exist
CASES_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
EVAL_DIR.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = DATA_DIR / "neuroscope.db"

# Validation & Upload limits
MAX_BYTES = 1 * 1024 * 1024 * 1024          # 1 GB per file limit
MAX_DECLARED_BYTES = 1_500_000_000          # 1.5 GB memory bomb guard
SLOTS = ["t1", "t1gd", "t2", "flair"]

# BraTS 2021 Region Mapping
BRATS_CODES = {0, 1, 2, 4}                  # 0: BG, 1: NCR, 2: ED, 4: ET
TTL_HOURS = 24
