# NeuroScope 3D

NeuroScope is a local web application for brain MRI tumour segmentation,
volumetric analysis, and 2D/3D visualization. The backend runs model inference
and serves the API; the frontend is a Vite/React development app.

> **Research use only.** This project is not intended for diagnosis or clinical
> decision-making.

## Requirements

- Windows 10/11 with PowerShell (commands below use PowerShell syntax).
- Python 3.11 and pip.
- Node.js 22.12 or later and npm.
- The MONAI BraTS segmentation checkpoint at
  `models/brats_mri_segmentation/brats_mri_segmentation/models/model.pt`.
  The checkpoint is not included in the repository; obtain it from the
  project's authorized model distribution and place it at that path.
- An NVIDIA GPU with a CUDA 12.1-compatible driver is recommended. The
  application automatically uses CUDA when available and otherwise runs on
  CPU, which may be considerably slower.

## Environment setup

Run these commands from the repository root in PowerShell:

```powershell
# Create and activate a Python virtual environment
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# Install Python dependencies, including the CUDA 12.1 PyTorch wheels
python -m pip install --extra-index-url https://download.pytorch.org/whl/cu121 -r requirements.txt

# Install frontend dependencies
Set-Location frontend
npm ci
Set-Location ..
```

If PowerShell blocks virtual-environment activation, allow it for the current
terminal only and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Check that the model checkpoint exists before starting the backend:

```powershell
Test-Path .\models\brats_mri_segmentation\brats_mri_segmentation\models\model.pt
```

The command should return `True`. If you need to store case data outside the
repository, set `DATA_DIR` before launching the backend; it contains the case
uploads and SQLite database. By default, data is stored under `data\`.

```powershell
$env:DATA_DIR = 'D:\neuroscope-data'
```

## Run the application

Start the backend in one PowerShell terminal from the repository root, with the
virtual environment active:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The backend loads the model on startup. Visit
`http://127.0.0.1:8000/api/health` to check that it is running; interactive API
documentation is at `http://127.0.0.1:8000/docs`.

In a second terminal, start the frontend:

```powershell
Set-Location frontend
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5173`). The Vite
development server proxies `/api` requests to the backend on port 8000.

Upload four aligned NIfTI MRI sequences (T1, T1-Gd/T1ce, T2, and FLAIR) in the
web app to run an analysis. A ground-truth/expert segmentation can optionally
be uploaded for comparison. The app also exposes a demo action when its
required demo fixtures or scans are available.

To run inference directly from the command line instead of the web app:

```powershell
python -m app.cli predict `
  --t1 "D:\scans\case_t1.nii.gz" `
  --t1gd "D:\scans\case_t1ce.nii.gz" `
  --t2 "D:\scans\case_t2.nii.gz" `
  --flair "D:\scans\case_flair.nii.gz" `
  --out "D:\scans\case_prediction.nii.gz"
```

## Tests and frontend checks

With the Python virtual environment active, run the backend test suite from the
repository root:

```powershell
python -m pytest
```

Run the frontend production build and linter from the `frontend` directory:

```powershell
npm run build
npm run lint
```

# BraTS2021 Holdout Evaluation

The model's predicted tumour masks were compared with the ground-truth
segmentations on 10 held-out BraTS2021 MRI scans. Scores below are Dice
similarity coefficients (0 = no overlap, 1 = perfect overlap); higher is
better. TC is Tumour Core, WT is Whole Tumour, and ET is Enhancing Tumour.
Macro Dice is the unweighted mean of the three region Dice scores for each
scan.

The evaluation used frozen probability thresholds of 0.65 for TC, 0.55 for WT,
and 0.35 for ET. The holdout cases were kept separate from the threshold-tuning
cases.

| BraTS2021 scan | TC Dice | WT Dice | ET Dice | Macro Dice |
|---|---:|---:|---:|---:|
| BraTS2021_00651 | 0.9466 | 0.9297 | 0.8922 | 0.9228 |
| BraTS2021_01091 | 0.8520 | 0.6336 | 0.8746 | 0.7867 |
| BraTS2021_01100 | 0.9737 | 0.9688 | 0.9232 | 0.9553 |
| BraTS2021_01143 | 0.9166 | 0.9421 | 0.8260 | 0.8949 |
| BraTS2021_01152 | 0.3212 | 0.8450 | 0.6238 | 0.5967 |
| BraTS2021_01194 | 0.9696 | 0.9391 | 0.6962 | 0.8683 |
| BraTS2021_01402 | 0.8957 | 0.9391 | 0.8921 | 0.9090 |
| BraTS2021_01529 | 0.3748 | 0.9384 | 0.0000 | 0.4377 |
| BraTS2021_01627 | 0.9788 | 0.9737 | 0.9425 | 0.9650 |
| BraTS2021_01640 | 0.9653 | 0.8006 | 0.9620 | 0.9093 |

| Across 10 scans | TC Dice | WT Dice | ET Dice | Macro Dice |
|---|---:|---:|---:|---:|
| Mean ± sample SD | 0.8194 ± 0.2520 | 0.8910 ± 0.1056 | 0.7633 ± 0.2893 | 0.8246 ± 0.1734 |

These results are preliminary and limited to the listed 10 scans. They do not
establish clinical performance or independent generalization; the model is for
research and educational use, not diagnosis or clinical decision-making.

Per-scan evaluation output is in [`eval/holdout_results.csv`](eval/holdout_results.csv);
the holdout case list is in [`eval/splits/holdout_test_cases.txt`](eval/splits/holdout_test_cases.txt).