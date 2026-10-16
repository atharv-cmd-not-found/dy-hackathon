"""
FastAPI Monolith Backend for NeuroScope 3D.
Implements asynchronous streaming uploads, single-worker GPU queue,
concurrency lock, canonical JSON schema, and binary GLB / NIfTI file serving.
"""
import uuid
import hashlib
import json
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import CASES_DIR, MAX_BYTES, SLOTS, EVAL_DIR
from app.db import init_db, create_case, get_case, get_recent_cases, delete_case
from app.cleanup import cleanup_loop, purge_case_files
from app.pipeline import run_case_pipeline
from app.validation import ValidationError, validate_set
from app.report import generate_html_report
from ml.predict import Segmenter

from typing import Optional

# Global worker & inference lock (ensures single-case GPU execution)
worker_executor = ThreadPoolExecutor(max_workers=1)
gpu_inference_lock = asyncio.Lock()
segmenter_instance: Optional[Segmenter] = None
git_commit_hash: str = "local"


def get_git_commit() -> str:
    """Attempts to read current git commit hash."""
    try:
        import subprocess
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode().strip()[:10]
    except Exception:
        return "local-dev"


def ensure_initialized():
    """Guarantees database and model segmenter are initialized."""
    global segmenter_instance, git_commit_hash
    if segmenter_instance is None:
        init_db()
        git_commit_hash = get_git_commit()
        segmenter_instance = Segmenter()
        if hasattr(segmenter_instance, "warmup"):
            segmenter_instance.warmup()


# Initialize immediately for test client & direct imports
ensure_initialized()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_initialized()
    cleanup_task = asyncio.create_task(cleanup_loop(interval_seconds=600))
    yield
    # Shutdown
    cleanup_task.cancel()
    worker_executor.shutdown(wait=False)


app = FastAPI(
    title="NeuroScope 3D",
    description="Brain MRI Segmentation, Volumetrics & 3D Reconstruction Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def save_upload_stream(upload_file: UploadFile, dest_path: Path) -> str:
    """
    Streams uploaded file to disk in 1 MB chunks and computes SHA-256 hash on the fly.
    Enforces a strict 1 GB hard limit.
    """
    hasher = hashlib.sha256()
    bytes_written = 0
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(dest_path, "wb") as f:
        while chunk := await upload_file.read(1024 * 1024):  # 1 MB chunk
            bytes_written += len(chunk)
            if bytes_written > MAX_BYTES:
                f.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"{upload_file.filename} exceeds the 1 GB maximum file size limit."
                )
            f.write(chunk)
            hasher.update(chunk)
            
    return hasher.hexdigest()


# =====================================================================
# API ROUTES
# =====================================================================

@app.get("/api/health")
async def health_check():
    """Healthcheck endpoint for container monitoring."""
    return {
        "status": "healthy",
        "model_loaded": segmenter_instance is not None,
        "commit": git_commit_hash
    }


@app.post("/api/cases/demo", status_code=status.HTTP_202_ACCEPTED)
async def submit_demo_case():
    """
    1-Click Demo endpoint: Uses real BraTS 2021 patient scans if available,
    otherwise falls back to synthetic fixtures, and launches the end-to-end analysis pipeline.
    """
    import shutil
    fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    kuruk_dir = Path(__file__).resolve().parent.parent.parent
    
    brats_map = {
        "t1": kuruk_dir / "BraTS2021_00012_t1.nii.gz",
        "t1gd": kuruk_dir / "BraTS2021_00012_t1ce.nii.gz",
        "t2": kuruk_dir / "BraTS2021_00012_t2.nii.gz",
        "flair": kuruk_dir / "BraTS2021_00012_flair.nii.gz",
    }
    use_brats = all(p.exists() for p in brats_map.values())

    case_id = f"demo-{uuid.uuid4().hex[:8]}"
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    
    if use_brats:
        for slot, src in brats_map.items():
            dst = case_dir / f"{slot}.nii.gz"
            shutil.copyfile(src, dst)
        create_case(case_id, sha256_map={"t1": "brats2021-00012", "t1gd": "brats2021-00012", "t2": "brats2021-00012", "flair": "brats2021-00012"}, has_expert=False)
        message = "Real BraTS 2021 Case #00012 queued for analysis."
    else:
        for slot in ["t1", "t1gd", "t2", "flair"]:
            src = fixtures_dir / f"base_{slot}.nii.gz"
            dst = case_dir / f"{slot}.nii.gz"
            if src.exists():
                shutil.copyfile(src, dst)
            else:
                raise HTTPException(status_code=500, detail="Demo base fixtures not found on server.")
        create_case(case_id, sha256_map={"t1": "demo-base", "t1gd": "demo-base", "t2": "demo-base", "flair": "demo-base"}, has_expert=False)
        message = "Demo synthetic scan queued for analysis."
        
    def worker_task():
        run_case_pipeline(case_id, segmenter_instance, git_commit=git_commit_hash)
        
    worker_executor.submit(worker_task)
    
    return {
        "status": "queued",
        "case_id": case_id,
        "message": message
    }


@app.post("/api/cases", status_code=status.HTTP_202_ACCEPTED)
async def submit_case(
    t1: UploadFile = File(...),
    t1gd: UploadFile = File(...),
    t2: UploadFile = File(...),
    flair: UploadFile = File(...),
    expert: UploadFile = File(None)
):
    """
    Accepts 4 multi-sequence MRI files (+ optional expert mask).
    Saves via streaming guard, creates case record, and enqueues in background worker.
    """
    case_id = str(uuid.uuid4())
    case_dir = CASES_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    
    sha256_map = {}
    
    # Save sequences
    try:
        sha256_map["t1"] = await save_upload_stream(t1, case_dir / "t1.nii.gz")
        sha256_map["t1gd"] = await save_upload_stream(t1gd, case_dir / "t1gd.nii.gz")
        sha256_map["t2"] = await save_upload_stream(t2, case_dir / "t2.nii.gz")
        sha256_map["flair"] = await save_upload_stream(flair, case_dir / "flair.nii.gz")
        
        has_expert = False
        if expert and expert.filename:
            sha256_map["expert"] = await save_upload_stream(expert, case_dir / "expert.nii.gz")
            has_expert = True
            
        create_case(case_id, sha256_map=sha256_map, has_expert=has_expert)
        
        # Enqueue background pipeline into single-worker thread pool
        def worker_task():
            run_case_pipeline(case_id, segmenter_instance, git_commit=git_commit_hash)
            
        worker_executor.submit(worker_task)
        
        return {
            "status": "queued",
            "case_id": case_id,
            "message": "Scans uploaded successfully and queued for analysis."
        }
        
    except HTTPException:
        purge_case_files(case_id)
        raise
    except Exception as e:
        purge_case_files(case_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload processing failed: {str(e)}"
        )


@app.get("/api/cases")
async def list_cases():
    """Returns a list of recent cases."""
    return get_recent_cases(limit=25)


@app.get("/api/cases/{case_id}")
async def get_case_status(case_id: str):
    """
    Returns full canonical JSON response for a case (Section 1.1 contract).
    """
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
        
    res_status = case["status"]
    
    # If failed, return structured error response
    if res_status == "failed":
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "failed",
                "case_id": case_id,
                "error": {
                    "code": case.get("error_code") or "VALIDATION_FAILED",
                    "message": case.get("error_message") or "Input scans failed validation.",
                    "failed_slot": case.get("failed_slot")
                },
                "stage_seconds": case.get("stage_seconds", {})
            }
        )
        
    # Build Canonical Response
    case_dir = CASES_DIR / case_id
    mesh_dir = case_dir / "meshes"
    
    files_dict = {
        "t1": f"/api/cases/{case_id}/files/t1.nii.gz",
        "t1gd": f"/api/cases/{case_id}/files/t1gd.nii.gz",
        "t2": f"/api/cases/{case_id}/files/t2.nii.gz",
        "flair": f"/api/cases/{case_id}/files/flair.nii.gz",
    }
    if (case_dir / "pred.nii.gz").exists():
        files_dict["pred_nii"] = f"/api/cases/{case_id}/files/pred.nii.gz"
    if (case_dir / "expert.nii.gz").exists():
        files_dict["expert_nii"] = f"/api/cases/{case_id}/files/expert.nii.gz"
        
    meshes_dict = {}
    for region in ["brain", "wt", "tc", "et"]:
        glb_file = mesh_dir / f"{region}.glb"
        if glb_file.exists():
            meshes_dict[region] = f"/api/cases/{case_id}/meshes/{region}.glb"
            
    results_data = case.get("results") or {}
    
    response_payload = {
        "status": res_status,
        "stage": case.get("stage"),
        "case_id": case_id,
        "created_at": case["created_at"],
        "expires_at": case["expires_at"],
        "model": results_data.get("model_info") or {
            "name": "MONAI SegResNet (BraTS 2021)",
            "version": "1.0",
            "license": "Apache-2.0"
        },
        "files": files_dict,
        "meshes": meshes_dict,
        "volumes": results_data.get("volumes", {}),
        "laterality": results_data.get("laterality", {}),
        "expert_volumes": results_data.get("expert_volumes"),
        "agreement": results_data.get("agreement"),
        "stage_seconds": case.get("stage_seconds", {}),
        "warnings": case.get("warnings", []),
        "disclaimer": "Research and teaching prototype. Suspected tumour regions predicted by the model; estimated volumes. Not a clinical diagnosis."
    }
    return response_payload


@app.get("/api/cases/{case_id}/report", response_class=HTMLResponse)
async def get_case_report(case_id: str):
    """
    Renders and serves a publication-grade printable clinical dossier for a case.
    Includes @media print CSS for 1-click browser printing or PDF saving.
    """
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case record not found.")
        
    results_data = case.get("results") or {}
    case_payload = {
        "status": case.get("status"),
        "case_id": case_id,
        "created_at": case.get("created_at"),
        "expires_at": case.get("expires_at"),
        "sha256": case.get("sha256"),
        "spatial_meta": {
            "shape": case.get("shape"),
            "zooms": case.get("zooms"),
            "voxel_volume_mm3": case.get("voxel_volume_mm3", 1.0)
        },
        "model": results_data.get("model_info") or {
            "name": "MONAI SegResNet (BraTS 2021)",
            "version": "1.0",
            "license": "Apache-2.0",
            "framework": "PyTorch / MONAI"
        },
        "volumes": results_data.get("volumes", {}),
        "laterality": results_data.get("laterality", {}),
        "expert_volumes": results_data.get("expert_volumes"),
        "agreement": results_data.get("agreement"),
        "stage_seconds": case.get("stage_seconds", {}),
        "warnings": case.get("warnings", []),
        "commit_hash": results_data.get("commit_hash") or git_commit_hash
    }
    
    html_content = generate_html_report(case_payload)
    return HTMLResponse(content=html_content)


@app.get("/api/cases/{case_id}/files/{slot}")
async def serve_nifti_file(case_id: str, slot: str):
    """
    Serves NIfTI scans and predicted segmentation masks.
    Supports both /files/t1 and /files/t1.nii.gz URL forms.
    Returns inline (not attachment) so NiiVue can stream without download prompt.
    """
    case_dir = CASES_DIR / case_id
    if not case_dir.exists():
        raise HTTPException(status_code=404, detail="Case directory not found.")
        
    clean_slot = slot.lower().replace(".nii.gz", "").replace(".nii", "")
    filename = f"{clean_slot}.nii.gz"
    file_path = case_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found for case.")
        
    return FileResponse(
        path=str(file_path),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        }
    )


@app.get("/api/cases/{case_id}/meshes/{mesh_name}")
async def serve_glb_mesh(case_id: str, mesh_name: str):
    """Serves binary GLB 3D meshes for Three.js."""
    case_dir = CASES_DIR / case_id
    mesh_path = case_dir / "meshes" / mesh_name
    if not mesh_path.exists():
        raise HTTPException(status_code=404, detail=f"3D mesh '{mesh_name}' not found.")
        
    return FileResponse(
        path=str(mesh_path),
        media_type="model/gltf-binary",
        filename=mesh_name
    )


@app.delete("/api/cases/{case_id}")
async def remove_case(case_id: str):
    """Manually purges a case and its files on demand."""
    purge_case_files(case_id)
    deleted = delete_case(case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Case not found.")
    return {"status": "deleted", "case_id": case_id}


@app.post("/api/predict")
async def direct_predict(
    t1: UploadFile = File(...),
    t1gd: UploadFile = File(...),
    t2: UploadFile = File(...),
    flair: UploadFile = File(...)
):
    """
    Synchronous direct prediction endpoint for judges and external evaluation scripts.
    Guarantees zero GPU collisions by acquiring gpu_inference_lock.
    Returns the predicted .nii.gz mask directly.
    """
    temp_id = f"predict_{uuid.uuid4().hex[:8]}"
    temp_dir = CASES_DIR / temp_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    paths = {
        "t1": temp_dir / "t1.nii.gz",
        "t1gd": temp_dir / "t1gd.nii.gz",
        "t2": temp_dir / "t2.nii.gz",
        "flair": temp_dir / "flair.nii.gz"
    }
    out_pred = temp_dir / "pred.nii.gz"
    
    try:
        await save_upload_stream(t1, paths["t1"])
        await save_upload_stream(t1gd, paths["t1gd"])
        await save_upload_stream(t2, paths["t2"])
        await save_upload_stream(flair, paths["flair"])
        
        # Validation
        validate_set(paths)
        
        # Inference with GPU Lock
        async with gpu_inference_lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, segmenter_instance.predict, paths, str(out_pred))
            
        if not out_pred.exists():
            raise HTTPException(status_code=500, detail="Inference did not generate predicted mask.")
            
        return FileResponse(
            path=str(out_pred),
            media_type="application/gzip",
            filename="prediction.nii.gz"
        )
        
    except ValidationError as ve:
        purge_case_files(temp_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": ve.code, "message": ve.message, "slot": ve.slot}
        )
    except Exception as e:
        purge_case_files(temp_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/eval")
async def get_evaluation_metrics():
    """Serves held-out model evaluation metrics and train/test split info."""
    results_file = EVAL_DIR / "results.json"
    split_file = EVAL_DIR / "split.json"
    
    eval_data = {}
    if results_file.exists():
        eval_data["results"] = json.loads(results_file.read_text(encoding="utf-8"))
    else:
        eval_data["results"] = {
            "status": "pending_ml_eval",
            "message": "Held-out evaluation metrics will appear here once ML teammate submits eval/results.json"
        }
        
    if split_file.exists():
        eval_data["split"] = json.loads(split_file.read_text(encoding="utf-8"))
    else:
        eval_data["split"] = {"message": "Split metadata will be populated from eval/split.json"}
        
    eval_data["disclaimer"] = "Model evaluation conducted on de-identified BraTS validation splits."
    return eval_data


# Mount static frontend production build if present
from fastapi.staticfiles import StaticFiles
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

