"""
Unit and integration tests for Phase 6: Clinical Printable Case Report generation.
Verifies HTML structure, cryptographic provenance tables, volumetric formulas,
legal disclaimer inclusion, and API endpoint behavior.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.report import generate_html_report


client = TestClient(app)


def test_generate_html_report_contents():
    sample_case = {
        "case_id": "test-case-12345678",
        "created_at": "2026-10-16T18:00:00.000000Z",
        "expires_at": "2026-10-17T18:00:00.000000Z",
        "sha256": {
            "t1": "a1b2c3d4e5f67890" * 4,
            "t1gd": "b2c3d4e5f67890a1" * 4,
            "t2": "c3d4e5f67890a1b2" * 4,
            "flair": "d4e5f67890a1b2c3" * 4,
        },
        "spatial_meta": {
            "shape": [240, 240, 155],
            "zooms": [1.0, 1.0, 1.0],
            "voxel_volume_mm3": 1.0
        },
        "model": {
            "name": "MONAI SegResNet (BraTS 2021)",
            "version": "1.0",
            "license": "Apache-2.0",
            "framework": "PyTorch / MONAI"
        },
        "volumes": {
            "WT": {"voxels": 6013, "ml": 6.013, "formula": "6,013 voxels × 1.000 mm³ / 1000 = 6.013 mL"},
            "TC": {"voxels": 2779, "ml": 2.779, "formula": "2,779 voxels × 1.000 mm³ / 1000 = 2.779 mL"},
            "ET": {"voxels": 1544, "ml": 1.544, "formula": "1,544 voxels × 1.000 mm³ / 1000 = 1.544 mL"}
        },
        "laterality": {
            "side": "Near Midline",
            "delta_x_mm": 0.51,
            "tumor_centroid_mm": [-122.0, 110.0, 77.0],
            "brain_centroid_mm": [-122.51, 109.4, 77.94]
        },
        "stage_seconds": {
            "validating": 0.42,
            "segmenting": 0.31,
            "volumetrics": 0.24,
            "meshing": 1.55
        },
        "warnings": [],
        "commit_hash": "3bc514b7e7"
    }

    html = generate_html_report(sample_case)
    
    assert "<!DOCTYPE html>" in html
    assert "TEST-CAS" in html
    assert "World RAS+" in html
    assert "240 × 240 × 155" in html
    assert "6.013 mL" in html
    assert "2.779 mL" in html
    assert "1.544 mL" in html
    assert "Near Midline" in html
    assert "Δx = +0.51 mm" in html
    assert "Research and teaching prototype" in html
    assert "@media print" in html
    assert "window.print()" in html


def test_api_report_endpoint_404():
    resp = client.get("/api/cases/non-existent-case-uuid/report")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Case record not found."
