import os

# Base workspace directory (code root — supports Docker volume override)
DEFAULT_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_ROOT = os.environ.get("TRADOVERA_WORKSPACE_ROOT", DEFAULT_WORKSPACE_ROOT)

# Data root — can be separated from code workspace (e.g. opentick-data/ on another drive)
# Set OPENTICK_DATA_ROOT to point to your opentick-data/ folder on any machine.
# Falls back to WORKSPACE_ROOT for backward compatibility (existing setups unchanged).
DATA_ROOT = os.environ.get("OPENTICK_DATA_ROOT", WORKSPACE_ROOT)

# Centralized paths
DB_PATH = os.path.normpath(os.path.join(DATA_ROOT, "catalog.db"))
LAKE_ROOT = os.path.normpath(os.path.join(DATA_ROOT, "lake"))
LAKE_PATTERN = os.path.join(LAKE_ROOT, "ohlcv", "**", "*.parquet").replace(os.sep, "/")
BLOOMBERG_DIR = os.path.normpath(os.path.join(DATA_ROOT, "bloomberg"))
PROGRESS_FILE = os.path.normpath(os.path.join(WORKSPACE_ROOT, "ingest_progress.json"))
