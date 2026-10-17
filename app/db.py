"""
SQLite database persistence layer for NeuroScope 3D.
Zero-installation standard library sqlite3 with thread-safe connection pooling.
"""
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
from app.config import DB_PATH, TTL_HOURS


def get_db_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with Row factory enabled."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initializes tables for cases and results if they do not exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT,
            stage_seconds TEXT,
            error_code TEXT,
            error_message TEXT,
            failed_slot TEXT,
            warnings TEXT,
            shape TEXT,
            zooms TEXT,
            voxel_volume_mm3 REAL,
            sha256 TEXT,
            has_expert INTEGER DEFAULT 0
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            case_id TEXT PRIMARY KEY,
            volumes TEXT,
            expert_volumes TEXT,
            agreement TEXT,
            laterality TEXT,
            model_info TEXT,
            commit_hash TEXT,
            finished_at TEXT,
            anatomy TEXT,
            localization TEXT,
            FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE
        );
        """)
        # Safe migration if table already exists without anatomy/localization column
        try:
            cursor.execute("ALTER TABLE results ADD COLUMN anatomy TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE results ADD COLUMN localization TEXT;")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def create_case(
    case_id: str,
    sha256_map: Optional[Dict[str, str]] = None,
    has_expert: bool = False
) -> Dict[str, Any]:
    """Creates a new case record with status 'queued' and a 24-hour expiration."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=TTL_HOURS)
    
    now_iso = now.isoformat()
    expires_iso = expires.isoformat()
    sha256_json = json.dumps(sha256_map or {})
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO cases (
            id, created_at, expires_at, status, stage, stage_seconds,
            sha256, has_expert, warnings
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case_id, now_iso, expires_iso, "queued", "queued", json.dumps({}),
            sha256_json, 1 if has_expert else 0, json.dumps([])
        ))
        conn.commit()
        
    return get_case(case_id)


def update_case_stage(
    case_id: str,
    status: str,
    stage: str,
    stage_seconds: Optional[Dict[str, float]] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    failed_slot: Optional[str] = None,
    warnings: Optional[List[Dict[str, str]]] = None,
    spatial_meta: Optional[Dict[str, Any]] = None
) -> None:
    """Updates progress, stage timers, errors, or spatial headers of a case."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        updates = ["status = ?", "stage = ?"]
        params = [status, stage]
        
        if stage_seconds is not None:
            updates.append("stage_seconds = ?")
            params.append(json.dumps(stage_seconds))
            
        if error_code is not None:
            updates.append("error_code = ?")
            params.append(error_code)
            
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
            
        if failed_slot is not None:
            updates.append("failed_slot = ?")
            params.append(failed_slot)
            
        if warnings is not None:
            updates.append("warnings = ?")
            params.append(json.dumps(warnings))
            
        if spatial_meta is not None:
            if "shape" in spatial_meta:
                updates.append("shape = ?")
                params.append(json.dumps(spatial_meta["shape"]))
            if "zooms" in spatial_meta:
                updates.append("zooms = ?")
                params.append(json.dumps(spatial_meta["zooms"]))
            if "voxel_volume_mm3" in spatial_meta:
                updates.append("voxel_volume_mm3 = ?")
                params.append(spatial_meta["voxel_volume_mm3"])
                
        params.append(case_id)
        query = f"UPDATE cases SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, params)
        conn.commit()


def save_case_results(
    case_id: str,
    volumes: Dict[str, Any],
    laterality: Dict[str, Any],
    model_info: Dict[str, Any],
    commit_hash: str = "local",
    expert_volumes: Optional[Dict[str, Any]] = None,
    agreement: Optional[Dict[str, Any]] = None,
    anatomy: Optional[Dict[str, Any]] = None,
    localization: Optional[Dict[str, Any]] = None
) -> None:
    """Saves completed segmentation, volumes, anatomy, and localization into the results table."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO results (
            case_id, volumes, expert_volumes, agreement, laterality,
            model_info, commit_hash, finished_at, anatomy, localization
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            case_id,
            json.dumps(volumes),
            json.dumps(expert_volumes or {}),
            json.dumps(agreement or {}),
            json.dumps(laterality),
            json.dumps(model_info),
            commit_hash,
            now_iso,
            json.dumps(anatomy or {}),
            json.dumps(localization or {})
        ))
        conn.commit()


def update_case_localization(case_id: str, localization: Dict[str, Any]) -> None:
    """Updates only the localization JSON for a case in the results table."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE results SET localization = ? WHERE case_id = ?
        """, (json.dumps(localization), case_id))
        conn.commit()


def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single case record along with results if available."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
        row = cursor.fetchone()
        if not row:
            return None
            
        case = dict(row)
        case["stage_seconds"] = json.loads(case["stage_seconds"] or "{}")
        case["sha256"] = json.loads(case["sha256"] or "{}")
        case["warnings"] = json.loads(case["warnings"] or "[]")
        case["shape"] = json.loads(case["shape"] or "[]")
        case["zooms"] = json.loads(case["zooms"] or "[]")
        
        cursor.execute("SELECT * FROM results WHERE case_id = ?", (case_id,))
        res_row = cursor.fetchone()
        if res_row:
            res = dict(res_row)
            anatomy_val = None
            if "anatomy" in res and res["anatomy"]:
                try:
                    anatomy_val = json.loads(res["anatomy"])
                except Exception:
                    anatomy_val = None
            localization_val = None
            if "localization" in res and res["localization"]:
                try:
                    localization_val = json.loads(res["localization"])
                except Exception:
                    localization_val = None
            case["results"] = {
                "volumes": json.loads(res["volumes"] or "{}"),
                "expert_volumes": json.loads(res["expert_volumes"] or "{}"),
                "agreement": json.loads(res["agreement"] or "{}"),
                "laterality": json.loads(res["laterality"] or "{}"),
                "model_info": json.loads(res["model_info"] or "{}"),
                "commit_hash": res["commit_hash"],
                "finished_at": res["finished_at"],
                "anatomy": anatomy_val,
                "localization": localization_val
            }
        else:
            case["results"] = None
            
        return case


def get_recent_cases(limit: int = 20) -> List[Dict[str, Any]]:
    """Lists recent cases ordered by creation timestamp."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, created_at, expires_at, status, stage FROM cases ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]


def delete_case(case_id: str) -> bool:
    """Deletes a case and cascades to results."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cases WHERE id = ?", (case_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_expired_cases() -> List[str]:
    """Returns list of case IDs that have exceeded their 24-hour TTL."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cases WHERE expires_at < ?", (now_iso,))
        return [r["id"] for r in cursor.fetchall()]
