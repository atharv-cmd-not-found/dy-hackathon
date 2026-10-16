"""
24-Hour TTL cleanup worker for NeuroScope 3D.
Periodically purges expired cases from SQLite and local disk.
"""
import shutil
import asyncio
from pathlib import Path
from app.config import CASES_DIR
from app.db import get_expired_cases, delete_case


def purge_case_files(case_id: str) -> None:
    """Removes the case directory on disk."""
    case_folder = CASES_DIR / case_id
    if case_folder.exists() and case_folder.is_dir():
        shutil.rmtree(case_folder, ignore_errors=True)


def run_cleanup_pass() -> int:
    """Runs a single cleanup pass on expired cases."""
    expired_ids = get_expired_cases()
    purged_count = 0
    for cid in expired_ids:
        purge_case_files(cid)
        delete_case(cid)
        purged_count += 1
    return purged_count


async def cleanup_loop(interval_seconds: int = 600):
    """Background coroutine that runs cleanup every 10 minutes."""
    while True:
        try:
            run_cleanup_pass()
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)
