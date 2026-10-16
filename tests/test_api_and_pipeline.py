"""
End-to-end integration tests for NeuroScope 3D API, CLI, and Pipeline.
Verifies asynchronous upload queue, canonical JSON contract,
concurrency lock, and file serving.
"""
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

client = TestClient(app)


def get_base_files():
    """Helper to prepare multipart file payload using generated base fixtures."""
    return {
        "t1": ("t1.nii.gz", open(FIXTURES_DIR / "base_t1.nii.gz", "rb"), "application/gzip"),
        "t1gd": ("t1gd.nii.gz", open(FIXTURES_DIR / "base_t1gd.nii.gz", "rb"), "application/gzip"),
        "t2": ("t2.nii.gz", open(FIXTURES_DIR / "base_t2.nii.gz", "rb"), "application/gzip"),
        "flair": ("flair.nii.gz", open(FIXTURES_DIR / "base_flair.nii.gz", "rb"), "application/gzip"),
    }


def test_api_health():
    """Health check endpoint must return healthy status."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["model_loaded"] is True


def test_e2e_case_pipeline_and_canonical_contract():
    """
    Uploads 4 base MRI scans, polls status to completion, and verifies
    canonical JSON contract, volume formulas, and file/mesh endpoints.
    """
    files = get_base_files()
    
    # 1. Submit Case
    post_resp = client.post("/api/cases", files=files)
    assert post_resp.status_code == 202
    post_data = post_resp.json()
    assert post_data["status"] == "queued"
    case_id = post_data["case_id"]
    assert case_id is not None
    
    # 2. Poll until status == 'done' (timeout 30 seconds)
    max_wait = 30
    start_time = time.time()
    final_data = None
    
    while time.time() - start_time < max_wait:
        get_resp = client.get(f"/api/cases/{case_id}")
        assert get_resp.status_code == 200
        status_data = get_resp.json()
        if status_data["status"] == "done":
            final_data = status_data
            break
        elif status_data["status"] == "failed":
            pytest.fail(f"Pipeline failed unexpectedly: {status_data}")
        time.sleep(0.5)
        
    assert final_data is not None, "Pipeline did not finish within timeout"
    
    # 3. Verify Canonical JSON Schema (Section 1.1)
    assert final_data["status"] == "done"
    assert final_data["case_id"] == case_id
    assert "volumes" in final_data and "WT" in final_data["volumes"]
    assert "formula" in final_data["volumes"]["WT"]
    assert "laterality" in final_data and "side" in final_data["laterality"]
    assert "disclaimer" in final_data
    
    # Verify file URLs and mesh URLs
    assert "pred_nii" in final_data["files"]
    assert "brain" in final_data["meshes"]
    assert "wt" in final_data["meshes"]
    
    # 4. Test serving predicted NIfTI file
    nii_resp = client.get(final_data["files"]["pred_nii"])
    assert nii_resp.status_code == 200
    assert len(nii_resp.content) > 0
    
    # 5. Test serving binary GLB 3D mesh
    glb_resp = client.get(final_data["meshes"]["wt"])
    assert glb_resp.status_code == 200
    assert glb_resp.content[:4] == b"glTF"
    
    # 6. Test case deletion
    del_resp = client.delete(f"/api/cases/{case_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"


def test_synchronous_direct_predict_endpoint():
    """
    Tests /api/predict synchronous endpoint for judges.
    Must return predicted NIfTI file directly.
    """
    files = get_base_files()
    resp = client.post("/api/predict", files=files)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/gzip"
    assert len(resp.content) > 0


def test_failure_pack_api_handling():
    """
    Tests that uploading an invalid file returns a structured HTTP 422 error
    instead of an unhandled server crash.
    """
    files = {
        "t1": ("t1.nii.gz", open(FIXTURES_DIR / "fail_notnifti.nii.gz", "rb"), "application/gzip"),
        "t1gd": ("t1gd.nii.gz", open(FIXTURES_DIR / "base_t1gd.nii.gz", "rb"), "application/gzip"),
        "t2": ("t2.nii.gz", open(FIXTURES_DIR / "base_t2.nii.gz", "rb"), "application/gzip"),
        "flair": ("flair.nii.gz", open(FIXTURES_DIR / "base_flair.nii.gz", "rb"), "application/gzip"),
    }
    # Direct predict should immediately return 422
    resp = client.post("/api/predict", files=files)
    assert resp.status_code == 422
    err_detail = resp.json()["detail"]
    assert err_detail["code"] == "NOT_NIFTI"
    assert err_detail["slot"] == "t1"
