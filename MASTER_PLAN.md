# NeuroScope 3D — Master Technical Architecture & Phase-Wise Execution Plan

**Project:** NeuroScope 3D (Brain MRI Segmentation, 3D Mesh Reconstruction & Volumetric Analysis Platform)  
**Hackathon Target:** 24-Hour Monolithic Platform Deliverable (`docker compose up`)  
**Core Rules & Invariants:**
- Zero third-party cloud/serverless dependencies (100% local execution, SQLite, local disk).
- Strict Medical Disclaimer across all UI and reports: *"Research and teaching prototype. Suspected tumour regions predicted by the model; estimated volumes. Not a clinical diagnosis."*
- Single source of truth: World Coordinates (RAS+ mm) via NIfTI Affine Matrix.
- 24-hour file Time-To-Live (TTL) with secure background cleanup.

---

## 1. System Architecture & Concurrency Lock

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Browser Client                                   │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────────┐  │
│  │  Multi-Slot Dropzone  │  │   NiiVue 2D Slices    │  │  Three.js 3D    │  │
│  │   (Clear Stale State) │  │ (Axial/Coronal/Sagit) │  │  (GLB Meshes)   │  │
│  └───────────────────────┘  └───────────────────────┘  └─────────────────┘  │
│                                      │                          │           │
│                                      └────────────┬─────────────┘           │
│                                           2D Click Syncs 3D                 │
│                                        (World RAS+ mm State)                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / REST
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                   FastAPI Monolith Backend (Port 8000)                      │
│                                                                             │
│  Endpoints:                                                                 │
│   • POST /api/cases                 (Multipart upload + stream limit)       │
│   • GET  /api/cases/{id}            (Poll stages, volumes, file & mesh URLs)│
│   • GET  /api/cases/{id}/files/{f}  (Serve original & predicted NIfTIs)     │
│   • GET  /api/cases/{id}/meshes/{m} (Serve binary GLB 3D meshes)            │
│   • GET  /api/cases/{id}/report     (HTML Report with @media print)         │
│   • POST /api/predict               (Judges CLI/endpoint - SHARES GPU LOCK) │
│   • GET  /api/eval                  (Model benchmark metrics table)         │
│                                       │                                     │
│  ┌────────────────────────────────────▼──────────────────────────────────┐  │
│  │ Unified GPU / Inference Queue: asyncio.Lock / ThreadPoolExecutor(1)   │  │
│  │ (Prevents T4 GPU Out-Of-Memory from concurrent /api/predict & UI)     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│               │                                          │                  │
│  ┌────────────▼────────────┐               ┌─────────────▼───────────────┐  │
│  │ SQLite DB (Built-in)    │               │ Local Storage (/data)       │  │
│  │  • cases, results table │               │  • cases/{id}/... (24h TTL) │  │
│  └─────────────────────────┘               └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 1.1 ML-to-Backend-to-Frontend Data Flow & Artifact Contract

To ensure 100% alignment between ML, Backend, and Frontend:

```
[ML INFERENCE]
  │  Input: paths dict {"t1", "t1gd", "t2", "flair"}
  ▼
  Output: "pred.nii.gz" (Raw uint8 NIfTI on disk with BraTS labels {0, 1, 2, 4})
  │
[BACKEND PIPELINE]
  ├─ 1. Volume & Laterality Engine: Computes WT, TC, ET volumes (mL) + formulas
  ├─ 2. Meshing Engine (Marching Cubes): Converts pred.nii.gz & T1 into 4 binary .glb files:
  │     • brain.glb, wt.glb, tc.glb, et.glb
  └─ 3. Serves REST API for Frontend & Judges
  │
[FRONTEND CLIENT]
  ├─ Automatic Background Fetch:
  │   • NiiVue 2D Viewer automatically fetches "pred.nii.gz" & "t1.nii.gz" to render 3 slice views
  │   • Three.js 3D Viewer automatically fetches .glb meshes to render 3D rotating brain & tumour
  └─ Explicit Manual Downloads (For Radiologists / Judges):
      • "Download Predicted NIfTI (.nii.gz)" button
      • "Download Case Report" button
```

#### Canonical JSON API Contract (`GET /api/cases/{case_id}`):
```json
{
  "status": "done",
  "case_id": "c8f93a12-e567-48f9-b841-897c645d9e01",
  "model": {
    "name": "MONAI SegResNet (BraTS 2021)",
    "version": "1.0",
    "license": "Apache-2.0"
  },
  "files": {
    "t1": "/api/cases/c8f93a12/files/t1",
    "t1gd": "/api/cases/c8f93a12/files/t1gd",
    "t2": "/api/cases/c8f93a12/files/t2",
    "flair": "/api/cases/c8f93a12/files/flair",
    "pred_nii": "/api/cases/c8f93a12/files/pred"
  },
  "meshes": {
    "brain": "/api/cases/c8f93a12/meshes/brain.glb",
    "wt": "/api/cases/c8f93a12/meshes/wt.glb",
    "tc": "/api/cases/c8f93a12/meshes/tc.glb",
    "et": "/api/cases/c8f93a12/meshes/et.glb"
  },
  "volumes": {
    "WT": {"ml": 16.0, "voxels": 8000, "formula": "8000 voxels × 2.0 mm³ / 1000 = 16.000 mL"},
    "TC": {"ml": 0.0, "voxels": 0, "formula": "0 voxels × 2.0 mm³ / 1000 = 0.000 mL"},
    "ET": {"ml": 0.0, "voxels": 0, "formula": "0 voxels × 2.0 mm³ / 1000 = 0.000 mL"}
  },
  "laterality": {
    "side": "Right",
    "delta_x_mm": 14.2,
    "note": "image-based estimate relative to brain centroid"
  },
  "warnings": [],
  "disclaimer": "Research and teaching prototype. Suspected tumour regions predicted by the model; estimated volumes. Not a clinical diagnosis."
}
```

---

## 2. Refined Validation Pipeline (Failure Pack & Sanity)

### Fast-Fail Hierarchy:
1. **Tier 0 (Client Pre-Flight):**
   - File extension check (`.nii`, `.nii.gz`).
   - Magic bytes check for Gzip (`0x1F, 0x8B`) to catch obvious non-archive files.
   - Clear previous results in UI immediately when a new upload starts or fails.
2. **Tier 1 (Streaming Guard):**
   - Stream in 1 MB chunks; enforce 1 GB hard cap per file (`MAX_BYTES`).
3. **Tier 2 (Header-Only Fast Fail):**
   - `try/except nib.load()` to catch corrupted headers or fake NIfTIs.
   - Memory bomb check: `prod(img.shape) * itemsize > 1.5 GB` rejects before array load.
   - Missing input check: explicit errors for missing sequence slot (e.g. *"Missing sequence: FLAIR. All four are required"*).
   - Check `img.ndim == 3` and $\min(\text{shape}) \ge 16$.
   - Cross-sequence check: compare shape and affine matrix across all 4 files (`atol=1e-3`).
4. **Tier 3 (Lazy Array Validation & Non-Refusing Sanity):**
   - Check `np.asanyarray(img.dataobj)` for corrupt gzip stream.
   - Check `np.isfinite(data).all()` and `np.ptp(data) > 0` (no all-zero scans).
   - **Sanity Check Rule:** **WARN ONLY, NEVER REFUSE.** If zero fraction or brain volume is abnormal (e.g. synthetic cube tests or unusual scans), attach a visible yellow warning to the case and report, but **always proceed to compute volumes**.
5. **Expert Mask Validation:**
   - Must match T1 shape and affine matrix.
   - Values must strictly belong to $\{0, 1, 2, 4\}$. If MSD/Decathlon code `3` is detected, reject with explicit message: *"BraTS 2021 codes expected {0, 1, 2, 4}; got code 3 (MSD format)"*.
   - Expert mask volumes are **always calculated and displayed**, independent of model execution.

---

## 3. Strict ML Contract & Preprocessing Rules

### Teammate Working Areas:
- Code: `ml/predict.py`
- Model Weights: `models/` (baked into Docker image)
- Benchmark Data: `eval/results.json` and `eval/split.json`
- Model Documentation: `MODEL_CARD.md`

### Algorithmic Invariants in `Segmenter.predict(paths, out_path)`:
1. **Input Channel Ordering:**
   - Stack 4D array strictly in order: `[T1Gd, T1, T2, FLAIR]`.
2. **Standardization & Resampling:**
   - Reorient to RAS+ coordinates.
   - Resample to isotropic $1.0\text{ mm}$ spacing using the NIfTI header affine.
   - Z-score normalization computed exclusively on **non-zero voxels** ($\frac{x - \mu}{\sigma}$).
3. **Inference & Remapping:**
   - Model outputs probability maps for regions: $TC, WT, ET$.
   - **Crucial Grid Preservation:** Interpolate probability maps back to the **original input grid/affine** before thresholding/argmax.
   - Remap predicted regions to BraTS 2021 integer codes:
     - $0 =$ Background
     - $1 =$ Necrotic Core ($NCR \in TC \setminus ET$)
     - $2 =$ Edema ($ED \in WT \setminus TC$)
     - $4 =$ Enhancing Tumor ($ET$)
4. **Deterministic & Offline:**
   - Deterministic eval mode (no random dropout/sampling) to guarantee test-retest Dice $\ge 0.99$.
   - Weights loaded locally from `models/` with CUDA acceleration and CPU fallback.

---

## 4. Phase-Wise Execution Plan

### Phase 1: Environment, Skeleton & Fixtures (Hours 0–2)
- Repo skeleton (`app/`, `ml/`, `tests/`, `models/`, `eval/`).
- Create `tests/make_fixtures.py`:
  - Synthetic 1×1×2 mm base scan.
  - Cube fixture: 20×20×20 voxel cube label 2 at 1×1×2 mm ($\implies WT = 16.0\text{ mL}$).
  - Failure pack: `fail_notnifti.nii.gz`, `fail_corrupt.nii.gz`, `fail_2d.nii.gz`, `fail_zeros.nii.gz`, `fail_nan.nii.gz`, `fail_mismatch.nii.gz`, `fail_code3.nii.gz`.
  - Bright voxel marker for linked crosshair verification.
- **Verification:** `python tests/make_fixtures.py` populates `tests/fixtures/`.

### Phase 2: Ultra-Fast Validation Engine & Unit Tests (Hours 2–4)
- Implement `app/validation.py` (Tier 0 to Tier 3 + Expert Mask check).
- Unit tests in `tests/test_validation.py` verifying all failure inputs return explicit HTTP 422 errors and zero server crashes.
- Sanity checks return warnings without halting processing.

### Phase 3: Mathematical Geometry, Volumetric & Meshing Engine (Hours 4–6)
- **Files:** `app/volumes.py`, `app/meshes.py`
- **Volume Calculation:**
  $$V_{\text{voxel}} = |\det(\text{affine}_{3\times3})|$$
  (Compare with $\prod(\text{zooms})$; warn if they diverge by $>1\%$).
  $$V_{\text{region}} = \frac{N_{\text{voxels}} \times V_{\text{voxel}}}{1000} \quad [\text{mL}]$$
  Regions: $WT = (\text{label} > 0)$, $TC = (\text{label} \in \{1, 4\})$, $ET = (\text{label} == 4)$.
- **Laterality (Side Estimation):**
  $$\Delta x = x_{\text{tumour centroid}} - x_{\text{brain centroid}}$$
  In RAS+ space: if $\Delta x > 0 \implies \text{Right}$; if $\Delta x < 0 \implies \text{Left}$.
  Add note *"near midline"* only if $|\Delta x| \le 2.0\text{ mm}$.
- **Mesh Extraction & GLB Generation (`app/meshes.py`):**
  - `marching_cubes` in pure voxel index space (no spacing argument).
  - Transform vertices to world mm: `nib.affines.apply_affine(affine, verts)`.
  - Invert normals if $\det(\text{affine}_{3\times3}) < 0$ for correct polygon winding.
  - Export 4 binary `.glb` meshes via `trimesh`: `brain.glb`, `wt.glb`, `tc.glb`, `et.glb`.
- **Verification:** Cube fixture yields exact $16.0\text{ mL} \pm 1\%$, and mesh centroid matches mask within $\le 1.5$ voxels.

### Phase 4: Real Model Integration, Concurrency Lock & REST API (Hours 6–8)
- Integrate real `Segmenter` in `ml/predict.py` using first real dev case.
- Rebuild orientation flip (`flip_same_anatomy`, `flip_mirrored`) and anisotropic `half_slices` fixtures using a **real de-identified patient scan** (since synthetic ellipsoids fail on neural networks).
- Concurrency lock in `app/main.py`: Synchronous `/api/predict` and background worker share `asyncio.Lock` to guarantee single-case GPU inference.
- Implement REST API returning canonical JSON schema (Section 1.1) with file download URLs and `.glb` mesh URLs.
- Verify judges' CLI: `python -m app.cli predict ...`.

### Phase 5: Frontend UI (React + NiiVue Multiplanar + Three.js 3D) (Hours 8–13)
- Dropzones for 4 sequences + expert mask with per-slot error highlights.
- Clear previous state immediately on new upload.
- **Dual Data Ingestion:**
  - **Automatic Background Fetch:** On completion, NiiVue fetches `pred.nii.gz` & `t1.nii.gz`; Three.js fetches `.glb` meshes directly.
  - **Manual Download Controls:** Side panel includes explicit buttons: *"Download Predicted NIfTI (.nii.gz)"* and *"Download Case Report"*.
- NiiVue 2D multiplanar viewer with slice crosshair and anatomical orientation tags ($L/R, A/P, S/I$).
- Three.js 3D viewer: GLTF loader for `.glb` files, transparent brain contour, WT/TC/ET mesh toggles, opacity sliders.
- **Linked Crosshair:** 2D slice click updates Three.js crosshair marker sphere in RAS+ space (handling Three.js Y-up transformation: `group.rotation.x = -Math.PI/2`).
- Metrics panel showing dynamic volume formula and coordinates ($x,y,z$ mm and $i,j,k$ voxels).
- Medical disclaimer footer on every screen.

### Phase 6: Provenance & Report Generation (Hours 13–16)
- File: `app/report.py` and `app/templates/report.html`.
- Printable HTML report (`@media print` CSS) displaying:
  - Input file SHA-256 hashes, Git commit hash, UTC timestamp.
  - Model info: Architecture (SegResNet/MONAI), License (Apache-2.0), Preprocessing steps.
  - Volumetric table with formula string.
  - Expert vs Predicted Dice & Sensitivity (when mask provided).
  - Prominent disclaimer and limitations statement.

### Phase 7: Held-Out Evaluation, Model Card & Dockerization (Hours 16–20)
- **Held-Out Evaluation Page (`/api/eval` & UI):**
  - Minimum 10 patient cases split by patient ID (no leak).
  - Table of per-region Dice and Sensitivity scores + mean.
  - Explicit BraTS 2018/2021 training overlap disclosure.
- **One-page `MODEL_CARD.md`:**
  - Intended use, clinical limitations, architecture, training data source (Baid et al., DOI: 10.7937/jc8x-9874).
- **Dockerization (`Dockerfile`, `docker-compose.yml`):**
  - Bake model weights directly into `models/` inside image.
  - Pass git commit via `--build-arg GIT_COMMIT=$(git rev-parse HEAD)`.
  - Multi-stage build bundling React frontend into FastAPI static assets.
  - Test single-command run: `docker compose up --build`.

---

## 5. Judges' 10 Evaluation Rubric & Pass Matrix

| # | Evaluation Test | Pass Criterion | Handling Component |
|---|---|---|---|
| 1 | **Held-out Accuracy** | Mean Dice within 0.05 of baseline; Sensitivity reported | `ml/predict.py` + `eval/results.json` |
| 2 | **Volume (Cube Test)** | 20×20×20 cube $\implies$ WT = 16.0 mL $\pm 1\%$, TC=0, ET=0 | `app/volumes.py` |
| 3 | **Anisotropic Scan** | Real scan downsampled $\implies$ WT within $\pm 10\%$ | `app/volumes.py` |
| 4 | **Orientation (Same Anatomy)** | Flipped voxel + updated affine $\implies$ same side, WT $\pm 2\%$ | `centroid_world()` in RAS+ space |
| 5 | **Orientation (Mirrored)** | Flipped voxel + fixed affine $\implies$ opposite side | `side_label()` sign check |
| 6 | **Linked Views** | 2D click aligns 3D marker within $\le 2$ voxels | NiiVue $\to$ Three.js marker coordinate map |
| 7 | **Failure Pack (8 Inputs)** | Graceful HTTP 422, clear error message, no server crash | `app/validation.py` |
| 8 | **Reproducibility** | Same case run twice yields Dice $\ge 0.99$ | Deterministic inference & worker lock |
| 9 | **Input Sanity** | Non-skull-stripped scan triggers **yellow warning** (no refusal) | `sanity_check()` in `app/validation.py` |
| 10 | **Blind Case Execution** | Any unseen case runs $< 2\text{ min}$ on T4 GPU | GPU worker lock + warmup |
