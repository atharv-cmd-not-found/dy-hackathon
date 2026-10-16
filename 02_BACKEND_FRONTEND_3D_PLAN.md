# NeuroScope 3D — BACKEND + FRONTEND + 3D KA PLAN
*(Tumhare liye: backend, DB, CRUD, Three.js, frontend, report, packaging. 24 hrs. Hinglish, layman.)*

---

## 0. Ye file kaise use karni hai

- Upar se neeche padho. **Section 5 (Bottlenecks)** sabse zaroori hai, sab layman me samjhaya hai.
- AI agent ko upload karna hai? Neeche wala **AGENT PROMPT** copy karo, aur ye poori file attach karo.
- ML guy ki file alag hai (`01_ML_GUY_PLAN.md`). Tumhara aur uska connection sirf ek function hai: `Segmenter.predict()` (Section 6.3).

### AGENT PROMPT (copy-paste)

```
Tu mera senior full-stack coding assistant hai. Hum 24-hour hackathon me "NeuroScope 3D" bana rahe hain:
user 4 brain-MRI NIfTI files (T1, T1Gd, T2, FLAIR) upload karta hai (+ optional expert mask), ML model
(mera teammate ka `ml/predict.py`, class `Segmenter`) tumour regions (WT, TC, ET) predict karta hai,
website unhe 3D me aur 3 linked slice views me dikhati hai, volumes (mL) naapti hai, accuracy metrics dikhati hai,
aur PDF/HTML report banati hai.

Meri zimmedari: FastAPI backend, SQLite, upload+validation, mesh generation, volume, report, React frontend
(NiiVue slices + Three.js 3D), Docker, README. ML teammate model/predict/evaluation karta hai.

HARD RULES:
1. Serverless / third-party cloud NAHI. Ek FastAPI monolith + ek background worker thread (ThreadPoolExecutor max_workers=1) + SQLite + local disk. Sab ek Docker container, `docker compose up` ek command.
2. Scans kisi third-party service ya LLM API ko nahi jaane chahiye. Uploads 24 hr me auto-delete.
3. Ek hi source of truth = world coordinates (mm), affine se. Voxel index sirf affine ke through nikalo.
4. Volume = voxel_count x voxel_volume (header spacing se, hardcode nahi) / 1000 mL. Formula + numbers UI/report me dikhao.
5. Validation fail ho to koi result nahi dikhana, koi crash nahi, clear message.
6. Wording: "suspected tumour region predicted by the model", "estimated volume". Kabhi "tumour detected", "diagnosis", "replaces radiologist" nahi. Disclaimer HAR screen pe.
7. Pehle saare mandatory features ek baar chalao, extra credit baad me.
8. Model ek baar startup pe load; har request pe nahi.
9. Har step ke baad test chalao. Mujhe jo samajh na aaye use simple Hinglish me explain karo.
Is file ke Section 8 (timeline) ke order me kaam karo. Pehle skeleton + validation + fixtures (Section 9), phir pipeline.
```

---

## 1. Project ek minute me (layman)

1. User 4 MRI files upload karta hai.
2. Backend check karta hai ki files theek hain (warna clear error).
3. ML wala function mask banata hai ("yahan suspected tumour region hai").
4. Hum mask se: volume (mL), 3D mesh (surface), side (left/right) nikalte hain.
5. Website pe: 3 slice views (axial, coronal, sagittal) + ek 3D brain. Ek crosshair sab me linked.
6. Report page/PDF: volumes, accuracy, provenance, limitations, disclaimer.

> ⚠️ Research/teaching prototype only. Diagnosis kabhi nahi.

---

## 2. Words ka matlab (glossary)

| Word | Simple matlab |
|---|---|
| **NIfTI (.nii/.nii.gz)** | 3D scan ka file format. `nibabel` se padhte hain. |
| **Voxel** | 3D pixel. Minecraft block. |
| **Spacing / zooms** | Ek voxel kitne mm ka. |
| **Affine (4×4 matrix)** | Voxel number -> real mm position ka "GPS map". Isme direction (left/right) bhi hai. **Sabse important concept.** |
| **World space (mm)** | Real duniya ke coordinates. Hum yahi use karenge (RAS+: +x Right, +y Anterior, +z Superior). |
| **Slice views** | Axial (upar se), Coronal (saamne se), Sagittal (side se). |
| **Crosshair** | Click kiya hua point, teeno views aur 3D me ek hi jagah dikhna chahiye. |
| **Mesh** | 3D surface (triangles ka jaal). Mask se banta hai (marching cubes). |
| **Marching cubes** | Algorithm jo mask ko 3D surface me badalta hai. |
| **GLB** | 3D model file jise Three.js seedha load karta hai. |
| **NiiVue** | JS library jo NIfTI slices + crosshair dikhati hai. Kaafi kaam bacha deti hai. |
| **Three.js** | JS 3D library (mesh dikhane ke liye). |
| **FastAPI** | Python web framework (API). |
| **SQLite** | Ek file jo database ka kaam karti hai. Server install nahi. |
| **Sanity check** | Check ki input waqai skull-stripped brain MRI lagta hai ya nahi. |
| **Provenance** | "Ye result kahan se aaya": model name/version, input hash, code commit, time. |
| **Dice / Sensitivity** | Accuracy numbers (ML guy nikalega, tum dikhaoge). |
| **Skull-stripped** | Khopdi/scalp hata hua, sirf dimaag. |

---

## 3. Serverless kyun NAHI (aur kya karna hai)

**Serverless** = cloud functions (AWS Lambda/Modal) jo request aate hi chalti hain, aur tum server nahi sambhalte.

**Hamare liye galat kyun:**
1. Rule: **scans third-party service ko nahi**. Cloud function = third-party. Risk.
2. 2-minute compute budget **organizer ke T4 GPU** pe. Cold start, GPU quota, 1 GB upload limits sab pareshan karenge.
3. Deliverable: **"one command that starts the platform"**. Matlab `docker compose up` laptop pe chale.

**Kya karna hai:** ek **FastAPI monolith** + 1 worker thread + SQLite + disk, sab ek Docker container. "Serverless-jaisa" sirf itna: uploads auto-delete (cleanup job).

### Architecture
```
Browser (React + NiiVue slices + Three.js 3D)
        │
FastAPI (ek hi process: API + static frontend files)
   ├─ POST /api/cases  -> save (stream) -> validate -> job queue
   │                                         │
   │                              Worker thread (1): Segmenter (GPU), volumes, meshes, report
   ├─ GET  /api/cases/{id}            status + stages + results
   ├─ GET  /api/cases/{id}/files/...  original nifti, pred mask, expert mask
   ├─ GET  /api/cases/{id}/meshes/{name}.glb
   ├─ GET  /api/cases/{id}/report(.pdf)
   ├─ POST /api/predict               judges ka endpoint: 4 files in -> label NIfTI out
   └─ GET  /api/eval                  ML guy ki eval table
SQLite: cases, results     Disk: /data/cases/{case_id}/  (24 hr TTL)
```

---

## 4. Stack (kya kya lagega)

| Kaam | Tool |
|---|---|
| API | FastAPI + uvicorn |
| NIfTI I/O | nibabel, numpy, scipy |
| Mesh | scikit-image `marching_cubes`, trimesh (GLB export) |
| DB | SQLite (stdlib `sqlite3` ya SQLModel) |
| Frontend | React + Vite (+ TypeScript optional) |
| 2D slices + crosshair | **NiiVue** (`@niivue/niivue`) |
| 3D | **Three.js** (+ OrbitControls, GLTFLoader) |
| Report | Jinja2 HTML -> WeasyPrint PDF (fallback: print-friendly HTML) |
| Packaging | Docker + docker-compose, `Makefile` |
| Hash/provenance | `hashlib.sha256`, `git rev-parse HEAD` |

**Tumhari skill:** backend strong hai. Frontend/Three.js ka bulk **AI agent se** likhwao. Tum sirf **contract** (API + coordinates) strictly follow karwana.

### Folder structure
```
neuroscope/
  app/
    main.py              # FastAPI app, routes, startup
    config.py            # limits, paths
    validation.py        # validate_set(), sanity_check()
    pipeline.py          # job stages
    volumes.py           # volume + side calculations
    meshes.py            # marching cubes + GLB
    report.py            # Jinja2 + WeasyPrint
    db.py                # sqlite
    cleanup.py           # 24 hr TTL
    cli.py               # judges ka CLI
    templates/report.html
  ml/                    # ML guy ka code (predict.py)
  models/                # weights (offline)
  eval/                  # split.json, results.json (ML guy)
  frontend/              # React app (build -> frontend/dist)
  tests/
    make_fixtures.py     # judges ke tests jaise files banata hai
    test_*.py
  data/                  # runtime (gitignored)
  Dockerfile  docker-compose.yml  Makefile  README.md  MODEL_CARD.md
```

---

## 5. BOTTLENECKS (sabse important — layman me)

Har ek: **Kya hai → Kyun dikkat → Kaise solve → Test**.

### B1. Orientation / affine (sabse zyada marks yahin)
- **Kya hai:** Scan file me bas numbers ka 3D dabba hota hai. Konsi direction "left" hai, ye **affine** batata hai. Alag scanners alag tareeke se save karte hain.
- **Kyun dikkat:** Agar viewer ya mesh array-index se chale (affine ignore karke), to scan "ulta" dikhega: tumour left ki jagah right.
- **Judges ke 2 tests:**
  1. Voxels flip + affine bhi update (anatomy wahi) -> tumour **same labelled side**, WT volume ±2%.
  2. Voxels flip, affine same (anatomy asal me mirror) -> tumour **doosri side**.
- **Solve:** (1) Viewer NiiVue ko **original file** do (wo affine se world me dikhata hai). (2) Mask ko hamesha **original grid + affine** pe save karo. (3) Mesh vertices pe **full affine** lagao (B3). (4) L/R label **affine se**, voxel index se nahi. (5) Side nikalne ke liye tumour centroid ko **brain-centroid** se compare karo (scanner ka origin midline nahi hota).
- **Test:** `tests/make_fixtures.py` (Section 9) dono flipped files banata hai. Dono upload karo, dekho side + volume.

```python
import nibabel as nib, numpy as np

def centroid_world(mask, affine):
    idx = np.argwhere(mask)
    return nib.affines.apply_affine(affine, idx.mean(axis=0))      # mm

def side_label(tumour_mask, brain_mask, affine, midline_tol_mm=5):
    dx = centroid_world(tumour_mask, affine)[0] - centroid_world(brain_mask, affine)[0]
    # RAS+: +x = Right
    if abs(dx) < midline_tol_mm: return "near midline", dx
    return ("Right" if dx > 0 else "Left"), dx
# Hamesha "image-based estimate" likho, medical claim nahi
```
Aur `nib.aff2axcodes(affine)` se array ka orientation (jaise `('L','A','S')`) report me dikhao.

### B2. Volume sahi nikaalna (cube test)
- **Kya:** Volume (mL) = voxel count × ek voxel ka size (mm³) / 1000.
- **Kyun dikkat:** Agar tum 1 mm hardcode karoge, to 1×1×2 mm scan pe volume aadha aayega.
- **Judges ka test:** 20×20×20 cube, label 2, spacing 1×1×2 -> 8000 voxels × 2 mm³ = 16000 mm³ = **WT 16.0 mL, TC 0, ET 0**.
- **Solve:**
```python
def region_masks(label):                      # BraTS 2021 codes
    return {"WT": label > 0, "TC": (label == 1) | (label == 4), "ET": label == 4}

def volumes_ml(label, zooms):
    voxel_mm3 = float(np.prod(zooms[:3]))
    out = {}
    for name, m in region_masks(label).items():
        n = int(m.sum())
        out[name] = {"voxels": n, "voxel_mm3": voxel_mm3,
                     "ml": n * voxel_mm3 / 1000.0,
                     "formula": f"{n} voxels × {voxel_mm3:g} mm³ / 1000 = {n*voxel_mm3/1000:.3f} mL"}
    return out
```
UI aur report me **formula + numbers** dikhao. Zooms `img.header.get_zooms()[:3]` se.
- **Test:** unit test: cube fixture -> WT 16.0 (±1%), TC 0, ET 0. **Expert mask ke saath 'WT' = label>0** (label 2 bhi WT me aata hai).
- Expert mask me codes **{0,1,2,4}** ke alawa kuch ho (jaise MSD ka 3) -> reject with message "BraTS 2021 codes expected".

### B3. Mesh world space me align hona
- **Kya:** Mask ko 3D surface me badalna (marching cubes), taaki Three.js me dikhe.
- **Kyun dikkat:** `marching_cubes` vertices **voxel index** space me deta hai. Agar sirf spacing lagayi aur affine nahi, to mesh slices ke saath align nahi hoga (khaaskar flipped/rotated scans pe).
- **Correction:** Pehle chat me maine kaha tha spacing bhi do aur affine bhi. **Galat — double-count hota hai.** Sahi: marching_cubes me **spacing mat do**, vertices pe seedha **poora affine** lagao (affine me spacing already hai).
- **Solve:**
```python
import numpy as np, trimesh, nibabel as nib
from skimage.measure import marching_cubes
from scipy.ndimage import gaussian_filter

def mask_to_mesh(mask, affine, smooth_sigma=1.0, step=1):
    m = gaussian_filter(mask.astype(np.float32), smooth_sigma) if smooth_sigma else mask.astype(np.float32)
    if m.max() <= 0.5: return None                                  # chhota/khaali region
    verts, faces, normals, _ = marching_cubes(m, level=0.5, step_size=step)   # NO spacing
    verts_mm = nib.affines.apply_affine(affine, verts)                          # voxel -> world mm
    mesh = trimesh.Trimesh(verts_mm, faces, process=False)
    if np.linalg.det(affine[:3, :3]) < 0:                           # mirrored affine -> winding fix
        mesh.invert()
    return mesh

# mesh.export(path)  # .glb
```
- Smoothing sirf **display** ke liye. Volume **raw mask ke voxel count** se.
- Brain surface: `brain_mask = (T1 != 0)` (skull-stripped me background 0), thoda gaussian smooth, `step=2` (kam triangles, tez).
- **Test:** Ek marker block (Section 9) ka mesh centroid mm == NiiVue crosshair mm (≤ 2 voxel).

### B4. Linked crosshair (2 voxel ke andar)
- **Kya:** Ek jagah click karo -> teeno slice views + 3D me wahi point.
- **Kyun dikkat:** Har view alag coordinate use kare to drift hota hai.
- **Solve:** **Ek hi state: `crosshairMM = [x,y,z]` (world mm).** Sab views usi se chalte hain.
  - NiiVue: location change event se mm milta hai (`onLocationChange` callback ya `locationChange` event, **NiiVue version ke docs dekho**) -> store update.
  - Three.js: ek chhota marker sphere `crosshairMM` pe.
  - Three.js me click (raycast) -> point -> mm -> NiiVue ka crosshair set (NiiVue: `nv.mm2frac(mm)` + `nv.scene.crosshairPos = ...` + redraw; API ke liye docs/demos dekho).
  - Panel me dikhao: **voxel indices (i,j,k)** aur **world mm (x,y,z)**. Voxel = `inverse(affine) @ [x,y,z,1]`, round.
- **Three.js axes ka mapping (zaroori):** world RAS (Z-up) vs Three.js (Y-up). Poore mesh group pe ek rotation: `group.rotation.x = -Math.PI/2`. Isse (x,y,z)->(x,z,-y). Marker bhi usi group me rakho. Click ka point `group.worldToLocal(point.clone())` se wapas RAS mm milta hai (manual math nahi).
- **Test:** Fixture me ek bright block known position pe. Click karo, 3 views + 3D me marker same, ≤ 2 voxel.

### B5. Failure pack (8 broken inputs)
- **Kya:** Judges 8 kharab inputs denge. Har baar **clear message, koi crash nahi, koi result nahi.**
- **Solve:** ek `validate_set()`; har fail ke liye `ValidationError(code, message)`; API usko HTTP 422 + JSON me bhejti hai; UI error card dikhata hai, viewer nahi.

| # | Input | Kaise pakdna | Message |
|---|---|---|---|
| 1 | `.nii.gz` naam ki non-NIfTI file | `nib.load` exception | "File is not a valid NIfTI image" |
| 2 | Corrupt gzip | **data actually load** karo (`np.asanyarray(img.dataobj)`), exception pakdo (lazy loading!) | "File is corrupt/truncated" |
| 3 | Sirf 3 sequences | missing slot check | "Missing sequence: FLAIR. All four are required" |
| 4 | Shapes/affines alag | compare shape + `np.allclose(affine, atol=1e-3)` | "Shapes/affines differ: T1 (240,240,155) vs T2 (...)" |
| 5 | 2D image | `img.ndim != 3` (ya koi dim < ~16) | "Image must be 3D" |
| 6 | All-zero / constant | `ptp == 0` | "Image is constant/blank" |
| 7 | NaN/Inf | `np.isfinite(data).all()` | "Contains NaN/Inf values" |
| 8 | > 1 GB | upload **stream** me byte count | "File exceeds 1 GB limit" |

Extra: broken affine (non-finite ya determinant 0), spacing ≤ 0, declared shape bahut bada (gzip bomb: header shape × 4 bytes > ~1.5 GB) -> reject.

```python
# app/validation.py
import numpy as np, nibabel as nib
from pathlib import Path

SLOTS = ["t1", "t1gd", "t2", "flair"]
MAX_BYTES = 1 * 1024**3
MAX_DECLARED_BYTES = 1_500_000_000

class ValidationError(Exception):
    def __init__(self, code, message, slot=None):
        super().__init__(message); self.code, self.message, self.slot = code, message, slot

def _load(path: Path, slot: str):
    try:
        img = nib.load(str(path))
    except Exception:
        raise ValidationError("NOT_NIFTI", f"{slot.upper()}: not a valid NIfTI image.", slot)
    if img.ndim != 3 or min(img.shape) < 16:
        raise ValidationError("NOT_3D", f"{slot.upper()}: image must be a 3D volume (got shape {img.shape}).", slot)
    if int(np.prod(img.shape)) * 4 > MAX_DECLARED_BYTES:
        raise ValidationError("TOO_LARGE", f"{slot.upper()}: declared volume is too large.", slot)
    aff = img.affine
    if not np.isfinite(aff).all() or abs(np.linalg.det(aff[:3, :3])) < 1e-9:
        raise ValidationError("BAD_AFFINE", f"{slot.upper()}: invalid spatial header (affine).", slot)
    try:
        data = np.asanyarray(img.dataobj).astype(np.float32)       # yahan corrupt gzip pakda jata hai
    except Exception:
        raise ValidationError("CORRUPT", f"{slot.upper()}: file is corrupt or truncated.", slot)
    if not np.isfinite(data).all():
        raise ValidationError("NOT_FINITE", f"{slot.upper()}: contains NaN or infinite values.", slot)
    if float(np.ptp(data)) == 0.0:
        raise ValidationError("CONSTANT", f"{slot.upper()}: image is constant (e.g. all zeros).", slot)
    return img, data

def validate_set(paths: dict[str, Path]):
    missing = [s for s in SLOTS if s not in paths]
    if missing:
        raise ValidationError("MISSING_SEQUENCE",
            f"Missing sequence(s): {', '.join(m.upper() for m in missing)}. All four are required.")
    loaded = {s: _load(Path(paths[s]), s) for s in SLOTS}
    ref_s = SLOTS[0]; ref_img = loaded[ref_s][0]
    for s in SLOTS[1:]:
        img = loaded[s][0]
        if img.shape != ref_img.shape or not np.allclose(img.affine, ref_img.affine, atol=1e-3):
            raise ValidationError("MISMATCH",
                f"Shape/affine mismatch: {ref_s.upper()} {ref_img.shape} vs {s.upper()} {img.shape}.", s)
    return loaded          # {slot: (img, data)}
```
- **Slot kaise pata chale:** UI me **4 alag labelled dropzones** (T1, T1Gd, T2, FLAIR). Filename se auto-assign ek helper hai: **flair -> t1gd/t1ce/t1c -> t2 -> t1** is order me check (kyunki "t1" substring "t1ce" me bhi hai).
- **Rule:** fail ho to `status="failed"`, error saved, viewer ka route result nahi deta.

### B6. 1 GB upload
- **Dikkat:** poori file RAM me read mat karo.
- **Solve:** chunks me save, bytes count, limit cross ho to delete + error. Frontend `file.size` bhi check kare (jaldi message), **par server pe zaroor** (judges API se bhi kar sakte hain).
```python
async def save_upload(up, dest: Path):
    size = 0
    with dest.open("wb") as f:
        while chunk := await up.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                f.close(); dest.unlink(missing_ok=True)
                raise ValidationError("TOO_LARGE", f"{up.filename}: exceeds the 1 GB limit.")
            f.write(chunk)
```
- Failure ke baad case folder clean up. Test: sparse file `truncate -s 1100M big.nii.gz`.

### B7. Input sanity (skull-stripped brain hai ya nahi)
- **Kya:** Ek dikha-ke-sahi-lagne wala file (valid NIfTI) par brain MRI nahi ya skull-stripped nahi. Judges: "not skull-stripped" aur "not a brain" case denge. **Warn ya refuse.**
- **Heuristics (starting thresholds, dev cases pe tune karo):**
  - **Exact-zero background fraction:** BraTS skull-stripped me background **exactly 0**, ~50–85% voxels. Skull-stripped nahi hai to background noisy (non-zero), zero fraction bahut kam. `zero_frac < 0.20` -> refuse; `< 0.40` -> warn.
  - **Brain-mask volume (mL):** `T1 != 0` voxel count × voxel vol. Typical adult ~1000–1700 mL. Bahar (`< 700` ya `> 2200`) -> warn; (`< 300` ya `> 3500`) -> refuse.
  - **Bounding box fill ratio:** non-zero region bbox ka kitna hissa bhara. Ellipsoid ~0.5, cube/full ~1.0. `> 0.85` -> warn "not brain-shaped".
  - **Cross-sequence agreement:** 4 sequences ke non-zero masks ka overlap (Dice) `> 0.9` hona chahiye.
  - **Spacing sanity:** koi spacing > 5 mm -> warn.
  - **Output sanity (prediction ke baad):** predicted WT bahut bada (jaise brain mask ka > 60%) -> warn "unreliable".
- **Test data:** (a) non-skull-stripped: ek dev case me background me noise add karo (`x[x==0] = noise`). (b) not a brain: synthetic cube/random noise / koi aur 3D array. **Sirf public/de-identified data**.
```python
def sanity_check(loaded):
    t1_img, t1 = loaded["t1"]
    zooms = t1_img.header.get_zooms()[:3]; vox = float(np.prod(zooms))
    nz = t1 != 0
    zero_frac = 1 - nz.mean()
    brain_ml = nz.sum() * vox / 1000
    idx = np.argwhere(nz)
    fill = nz.sum() / np.prod(idx.max(0) - idx.min(0) + 1) if nz.any() else 0
    issues = []   # (severity, code, message)
    if zero_frac < 0.20: issues.append(("refuse", "NOT_SKULL_STRIPPED", "Looks like a non-skull-stripped head scan; this tool expects skull-stripped brain MRI."))
    elif zero_frac < 0.40: issues.append(("warn", "LOW_BACKGROUND", "Little empty background; input may not be skull-stripped."))
    if brain_ml < 300 or brain_ml > 3500: issues.append(("refuse", "NOT_BRAIN_SIZE", f"Head/brain volume {brain_ml:.0f} mL is implausible for an adult brain MRI."))
    elif brain_ml < 700 or brain_ml > 2200: issues.append(("warn", "ODD_BRAIN_SIZE", f"Unusual brain volume ({brain_ml:.0f} mL)."))
    if fill > 0.85: issues.append(("warn", "NOT_BRAIN_SHAPE", "Non-zero region fills its bounding box; shape is not brain-like."))
    return issues, {"zero_frac": zero_frac, "brain_ml": brain_ml, "fill": fill}
```
- "refuse" -> result nahi, clear message. "warn" -> result dikhao par har screen pe yellow warning + report me.

### B8. 2-minute limit
- **Kya:** Upload se report tak < 2 min (T4).
- **Budget (rough):** upload 2–5s, validate 3s, model prep 5–10s, inference 30–60s, postprocess 5s, meshes 5–10s, report 3–5s => ~ 80–100 s. Model hissa ML guy ka.
- **Solve:** model startup pe load + `warmup()`; **ek GPU worker** (`ThreadPoolExecutor(max_workers=1)`) taaki 2 cases GPU pe takkar na maaren; meshes `step_size=2`; PDF alag thread/lazy (pehli request pe banao, cache).
- Har stage ka time DB me likho (`stage_seconds`) => demo me dikha sakte ho.
- Judges ka direct **`/api/predict`** endpoint synchronous ho (sirf model + mapping, no meshes/report) => tez.

```python
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=1)

@app.on_event("startup")
def startup():
    global segmenter
    from ml.predict import Segmenter
    segmenter = Segmenter(); segmenter.warmup()
    cleanup.start()
```

### B9. Reproducibility (Dice ≥ 0.99)
- Same input 2 baar -> same mask. Ye mostly ML guy ke control me hai (eval mode, fixed TTA). Tum: koi randomness mat daalo (random smoothing/seed-less sampling nahi).
- Test: same case 2 baar `/api/predict`, Dice compare script.

### B10. "One command" + Docker + offline
- **Dikkat:** Judge ke machine pe `docker compose up` ek baar me chalna chahiye. Venue wifi par bharosa nahi.
- **Solve:** weights `models/` me; pip/npm dependencies image me bake; frontend pehle se build (`frontend/dist` FastAPI se serve). **NiiVue/Three.js CDN se mat lo, npm se bundle karo** (offline).
- GPU: docker-compose me nvidia device reservation; GPU na mile to CPU fallback + warning.
```yaml
services:
  app:
    build: .
    ports: ["8000:8000"]
    volumes: ["./data:/data", "./models:/app/models:ro", "./eval:/app/eval:ro"]
    environment: ["DATA_DIR=/data"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```
`Makefile`: `run: docker compose up --build`. **Fresh machine pe test (Hour 22).** WeasyPrint ko `libpango-1.0-0 libpangoft2-1.0-0` chahiye (Dockerfile me `apt-get install`).

### B11. 24 hr me delete
- `cases.expires_at = created_at + 24h`. Background loop har 10 min me expired case folder + DB rows delete. Startup pe bhi chalao. UI me "Uploads are deleted automatically within 24 hours". "Delete now" button bhi.
- **Hidden cases ko repo/logs/commit me kabhi nahi.** Logs me file contents print nahi.

### B12. Report PDF
- Jinja2 template -> WeasyPrint. Agar PDF me problem, HTML report page (`@media print` CSS) bhi theek hai.
- Report me: (1) case summary + warnings, (2) volumes with formula, (3) expert vs predicted (agar mask), (4) eval metrics table (ML ke JSON se), (5) **provenance**: model name/version/licence, preprocessing, input SHA-256 (har file), code commit, timestamp, (6) limitations, (7) disclaimer. Optional: 3D screenshot (frontend `canvas.toDataURL` -> POST).
- **Sample report** ek baar generate karke `deliverables/sample_report.pdf`.

### B13. Wording + disclaimer
- Disclaimer **har screen pe** (persistent footer component): *"Research and teaching prototype. Model output is not a diagnosis and must not be used for clinical decisions."*
- Use: "suspected tumour region predicted by the model", "estimated volume".
- Mat likho: "tumour detected", "diagnosis", "AI diagnoses", "replaces the radiologist". UI strings ka grep karo (`grep -ri "detected\|diagnos" frontend/src app/templates`).

### B14. Rules jinse disqualify ho sakte ho
- Inference me stored dataset image/label read -> disqualification. **Koi lookup/cache by filename nahi.**
- "Backup precomputed case" allowed hai **sirf clearly "BACKUP (precomputed)" label ke saath**.
- Hidden cases pe train/tune/save nahi.

---

## 6. Build details

### 6.1 DB schema (SQLite)
```sql
CREATE TABLE cases (
  id TEXT PRIMARY KEY,                -- uuid
  created_at TEXT, expires_at TEXT,
  status TEXT,                        -- queued|validating|segmenting|postprocess|meshing|report|done|failed
  stage_seconds TEXT,                 -- json
  error_code TEXT, error_message TEXT,
  warnings TEXT,                      -- json list
  shape TEXT, zooms TEXT, orientation TEXT,
  sha256 TEXT,                        -- json {slot: hash}
  has_expert INTEGER DEFAULT 0
);
CREATE TABLE results (
  case_id TEXT PRIMARY KEY, volumes TEXT, expert_volumes TEXT, agreement TEXT,
  side TEXT, model_info TEXT, commit_hash TEXT, finished_at TEXT
);
```
"CRUD of MRI" = cases create (upload), read (status/results), delete (manual + TTL), list (history page).

### 6.2 API
| Method | Path | Kaam |
|---|---|---|
| POST | `/api/cases` | multipart: `t1,t1gd,t2,flair` (+ optional `label`). Returns `{case_id}` (202) |
| GET | `/api/cases` | recent cases |
| GET | `/api/cases/{id}` | status, stage, error, warnings, results |
| GET | `/api/cases/{id}/files/{name}` | `t1, t1gd, t2, flair, pred, expert` (original grid) |
| GET | `/api/cases/{id}/meshes/{name}.glb` | `brain, wt, tc, et, expert_wt...` |
| GET | `/api/cases/{id}/report` / `report.pdf` | report |
| DELETE | `/api/cases/{id}` | delete |
| POST | `/api/predict` | **judges**: 4 files -> label NIfTI response (BraTS codes, input grid/affine) |
| GET | `/api/eval` | `eval/results.json` + split |

Error JSON: `{"error": {"code": "MISMATCH", "message": "..."}}` (HTTP 422). Files serve karne ke liye `FileResponse` (range support ke liye Starlette static ok).

### 6.3 ML se connection (ek hi jagah)
```python
# app/pipeline.py (sketch)
def run_case(case_id):
    paths = case_paths(case_id)
    loaded = validate_set(paths)                         # B5
    issues, stats = sanity_check(loaded)                 # B7
    if any(s == "refuse" for s, *_ in issues): fail(case_id, issues); return
    res = segmenter.predict(paths, out_path=pred_path)   # ML guy ka function
    label = np.asarray(nib.load(pred_path).dataobj).astype(np.uint8)
    img = loaded["t1"][0]
    vols = volumes_ml(label, img.header.get_zooms())     # B2
    side = side_label(region_masks(label)["WT"], loaded["t1"][1] != 0, img.affine)  # B1
    save_meshes(label, loaded, img.affine)               # B3
    # expert mask: validate same shape/affine, codes in {0,1,2,4}; volumes + Dice/agreement
    write_results(...); make_report(...)
```
**Contract (ML guy se):** `Segmenter.predict({"t1","t1gd","t2","flair"} paths, out_path)` -> NIfTI uint8 {0,1,2,4} input-grid. Wo signature badle to turant batao.

### 6.4 Judges ka CLI + endpoint
```bash
python -m app.cli predict --t1 ... --t1gd ... --t2 ... --flair ... --out pred.nii.gz
```
README me exact command likho. `/api/predict` bhi wahi call karta hai (validate -> predict -> NIfTI download).

### 6.5 Frontend (screens)
1. **Upload page:** 4 labelled dropzones (T1, T1Gd, T2, FLAIR) + optional expert mask; filename se auto-assign; error card (clear message).
2. **Processing page:** stages ke saath progress (poll `GET /api/cases/{id}` har 1s).
3. **Viewer page:**
   - Left: NiiVue multiplanar (axial/coronal/sagittal), L/R, A/P, S/I labels, mask overlay, opacity.
   - Right: Three.js 3D: brain surface + WT/TC/ET meshes, toggles, opacity sliders, rotate/zoom, crosshair marker.
   - Side panel: crosshair as **voxel (i,j,k) + world mm (x,y,z)**, volumes table with formula, side estimate, warnings, expert-vs-predicted (agar mask), "Download label NIfTI", "Report".
4. **Evaluation page:** `/api/eval` ki table (Dice/sensitivity per region per case + mean), **split list**, **overlap disclosure**.
5. **Persistent footer:** disclaimer (har page).

**NiiVue notes:** `loadVolumes` me `name` ko `.nii.gz` se end karo (URL me extension na ho to). Mask ko label colormap (1 red, 2 yellow/green, 4 blue) + opacity. **Latest docs/demos (niivue.com) agent se padhwao**, API versions me badalti hai. L/R/A/P/S/I labels check karo ki dikh rahe hain (NiiVue ke options); na dikhe to affine se custom overlay.

**Three.js:** `GLTFLoader` se GLB, `OrbitControls`, `MeshStandardMaterial({transparent:true, opacity})`, har region ko `visible` toggle. Group rotation `-Math.PI/2` about X (B4).

---

## 7. Extra credit (sirf core ke baad)
- **Colour-coded agreement** (expert vs prediction): TP/FP/FN overlay (green/red/blue). NIfTI me alag "agreement" mask banao.
- **Uncertainty** (ML guy ka TTA): uncertainty map overlay.
- **Quality warning** jab ek sequence missing ho (reject ki jagah): zero-fill + warning (risky, sirf agar time ho).
- **HD95** (mm), DICOM input, 2 scans compare.
Pehle mandatory sab pakka.

---

## 8. 24 hr timeline (checkpoints ke saath)

| Hour | Tum | ML guy | Checkpoint |
|---|---|---|---|
| 0–1 | Repo, Docker skeleton, FastAPI "hello", **ek sawal organizers se** (Section 11) | Starter kit notebook chalaye | repo push |
| 1–3 | Upload (stream) + `validate_set()` + DB + `tests/make_fixtures.py` | `predict()` bundle as-is | **"predict ready"** |
| 3–6 | Pipeline: predict -> label -> volumes -> side. Cube + flip tests. `/api/predict` + CLI | label/channel tests | end-to-end API se NIfTI aaye |
| 6–10 | Meshes + GLB, frontend skeleton, NiiVue 3 views + overlay | Eval 10 cases | Viewer me slices dikhe |
| 10–14 | Three.js 3D, toggles, opacity, **linked crosshair** + voxel/mm panel | Speed tuning | Linked-views test pass |
| 14–18 | Sanity check (B7), failure pack saare 8 pass, report + PDF, disclaimer, eval page | Model card, optional TTA | **Saare mandatory features ek baar kaam** |
| 18–22 | Extra credit, UI polish, README, sample report, model-card merge | Eval table final | feature freeze @ Hour 20 |
| 22–24 | **Fresh machine pe `docker compose up`**, saare judges' tests dohrao, demo practice | Same | demo ready |

**Mantra:** Extra credit se pehle sab mandatory ek baar kaam karwa lo.

---

## 9. Test fixtures (judges ke tests khud banao) — `tests/make_fixtures.py`

Ye script judges ke scenarios jaisi files banati hai. Isse **Hour 1–3** me banao taaki pura build in pe test ho.

```python
import numpy as np, nibabel as nib, gzip, shutil
from pathlib import Path

OUT = Path("tests/fixtures"); OUT.mkdir(parents=True, exist_ok=True)
SLOTS = ["t1", "t1gd", "t2", "flair"]

def fake_brain(shape=(96, 96, 80), seed=0):
    rng = np.random.RandomState(seed)
    x, y, z = np.meshgrid(*[np.linspace(-1, 1, s) for s in shape], indexing="ij")
    inside = (x**2 / .8**2 + y**2 / .9**2 + z**2 / .8**2) < 1
    vol = np.where(inside, 100 + 30 * rng.randn(*shape), 0).astype(np.float32).clip(0)
    vol[~inside] = 0.0
    return vol

def save(data, affine, name): nib.save(nib.Nifti1Image(data, affine), OUT / name)
def save_set(prefix, datas, affine):
    for s in SLOTS: save(datas[s], affine, f"{prefix}_{s}.nii.gz")

aff = np.diag([1., 1., 2., 1.])                      # 1x1x2 mm
base = {s: fake_brain(seed=i) for i, s in enumerate(SLOTS)}
save_set("base", base, aff)

# 1) Volume test: 20x20x20 cube label=2 at spacing 1x1x2 -> expect WT 16.0 mL
shape = base["t1"].shape
cube = np.zeros(shape, np.uint8); cube[30:50, 30:50, 30:50] = 2
save(cube, aff, "cube_label.nii.gz")

# 2) Orientation SAME anatomy: flip voxels (axis 0) AND fix affine
def flip_with_affine(data, affine, axis=0):
    d2 = np.flip(data, axis).copy()
    a2 = affine.copy()
    a2[:3, axis] = -affine[:3, axis]
    a2[:3, 3] = affine[:3, 3] + affine[:3, axis] * (data.shape[axis] - 1)
    return d2, a2
fa = {}; 
for s in SLOTS: d2, a2 = flip_with_affine(base[s], aff); fa[s] = d2
save_set("flip_same_anatomy", fa, a2)

# 3) Orientation MIRRORED anatomy: flip voxels, affine unchanged
save_set("flip_mirrored", {s: np.flip(base[s], 0).copy() for s in SLOTS}, aff)

# 4) Anisotropic: remove every 2nd axial slice (axis 2) -> spacing z doubles
aff_h = aff.copy(); aff_h[:3, 2] *= 2
save_set("half_slices", {s: base[s][:, :, ::2].copy() for s in SLOTS}, aff_h)

# 5) Linked views: bright marker block at known voxel
mk = {s: base[s].copy() for s in SLOTS}; mk["t1gd"][60:64, 40:44, 30:34] = 2000
save_set("marker", mk, aff)           # marker center ~ voxel (61.5, 41.5, 31.5)

# 6) Failure pack
(OUT / "fail_notnifti.nii.gz").write_text("this is not a nifti")
good = (OUT / "base_t1.nii.gz").read_bytes()
(OUT / "fail_corrupt_gzip.nii.gz").write_bytes(good[: len(good) // 2])        # truncated gzip
save(np.random.rand(64, 64).astype(np.float32), np.eye(4), "fail_2d.nii.gz")
save(np.zeros_like(base["t1"]), aff, "fail_zeros.nii.gz")
nan = base["t1"].copy(); nan[10, 10, 10] = np.nan; save(nan, aff, "fail_nan.nii.gz")
save(np.random.rand(50, 50, 40).astype(np.float32), aff, "fail_shape_mismatch.nii.gz")
# fail_three_sequences = base set se flair na bhejo
# fail_over_1gb: shell me ->  truncate -s 1100M tests/fixtures/fail_big.nii.gz
```
Note: `fake_brain` ek synthetic ellipsoid hai (real model pe meaningful mask nahi dega). **Sanity/orientation/volume/failure** tests ke liye kaafi hai; mask-side tests ke liye ek real dev-subset case me `data[::-1]` flip karke bhi karo.

**Tests jo likhne hain (pytest):**
1. `validate_set` har failure fixture pe sahi `code` raise kare.
2. Cube: `volumes_ml` -> WT 16.0, TC 0, ET 0.
3. Flip-same-anatomy vs base: tumour centroid world-mm same; WT volume ±2%.
4. Flip-mirrored: centroid x ka sign ulta.
5. half_slices vs base: WT volume ±10%.
6. Mesh centroid mm vs mask centroid mm (≤ 1–2 voxel).
7. Repro: same case 2 baar, Dice ≥ 0.99.

---

## 10. Judges ke 10 tests -> kaun kya check karega

| Test | Full marks kab | Kaun | Kahan |
|---|---|---|---|
| Held-out accuracy | Mean Dice baseline ke 0.05 ke andar | ML | pipeline + eval |
| Volume (cube) | WT 16.0 mL ±1%, TC/ET 0 | **Tum** | B2 |
| Anisotropic | 2 WT volumes ±10% | ML + tum | B2 + ML B4 |
| Orientation same anatomy | same side, WT ±2% | **Tum** + ML | B1 |
| Orientation mirrored | tumour doosri side | **Tum** | B1 |
| Linked views | crosshair ≤ 2 voxel (3 views + 3D) | **Tum** | B4 |
| Failure pack (8) | clear message, no crash, no result | **Tum** | B5, B6 |
| Reproducibility | Dice ≥ 0.99 | ML | B9 |
| Blind case | plausible mask, live viva me | Dono | pipeline |
| Input sanity | warn/refuse | **Tum** | B7 |

---

## 11. Organizers se poochne ke sawal (Hour 0–1)
1. Judges ke machine pe GPU (T4) hoga ya hum apna laptop laayenge? CPU fallback ok hai?
2. Starter-kit ka scorer kaunsa format padhta hai (`.nii.gz`, `uint8`, input grid)?
3. Fine-tuning ke liye Colab/Kaggle (public data) allowed hai? (Judges ke cases wahan kabhi nahi jaayenge.)
4. NiiVue/Three.js npm se bundle karna ok? (offline venue)

---

## 12. Demo script (5 min) + Viva cheat-sheet

**Demo:**
1. (30s) Problem: "trainee slices scroll karke tumour imagine karta hai."
2. (60s) 4 files upload -> stages -> viewer.
3. (60s) Crosshair click: 3 views + 3D linked; voxel + mm panel.
4. (45s) Volumes (formula dikha ke), side estimate, expert-mask agreement.
5. (45s) Evaluation page: held-out Dice/sensitivity + overlap disclosure.
6. (30s) Failure demo: 2 broken files -> clear message.
7. (30s) Report PDF + provenance + disclaimer.

**Viva me kya poochenge (jawaab ready rakho):**
- *Serverless kyun nahi?* -> Rule (scans third-party nahi), 2-min GPU budget, one-command deliverable.
- *Orientation kaise handle kiya?* -> Affine se world mm; model ko RAS; mask original grid pe; L/R affine se; side brain-centroid ke relative.
- *Volume kaise nikala?* -> voxel count × header spacing / 1000; formula UI me.
- *Mesh aligned kaise?* -> marching cubes (no spacing) + poora affine.
- *Failure pack?* -> validate_set; lazy-load fix; stream size check.
- *Accuracy honest hai?* -> patient-wise split; overlap with pretrained training data disclose kiya.
- *Limits?* -> adult glioma only, skull-stripped 1 mm, scanner shift, small ET, non-clinical.

---

## 13. Final checklist

- [ ] `docker compose up` fresh machine pe chalta hai (README me ek command)
- [ ] Upload -> validate -> predict -> viewer -> report end-to-end
- [ ] 8 failure inputs: clear message, no crash, no result
- [ ] Sanity: non-skull-stripped + non-brain -> warn/refuse
- [ ] Cube = 16.0 mL, TC 0, ET 0
- [ ] Flip tests (same side / opposite side) pass
- [ ] Crosshair linked (3 views + 3D) ≤ 2 voxel; voxel + mm shown
- [ ] L/R, A/P, S/I labels dikhte hain
- [ ] 3D: rotate, zoom, toggle, opacity
- [ ] `/api/predict` + CLI judges ke liye
- [ ] Report: volumes+formula, metrics, provenance (model, version, licence, preprocessing, SHA-256, commit, timestamp), limitations, disclaimer
- [ ] Disclaimer har screen pe; wording theek (grep)
- [ ] 24 hr auto-delete + delete button
- [ ] Eval page: split + overlap disclosure
- [ ] README: BraTS 2021 (Baid et al., DOI 10.7937/jc8x-9874), MSD (agar use), MONAI Apache-2.0, third-party components list
- [ ] MODEL_CARD.md, sample report, demo practice
