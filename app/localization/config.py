"""
Configuration for Anatomical Localization and Report Generation.
Defines thresholds for template-space verification, component filtering,
report sentence generation, and safety disclaimers.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class LocalizationConfig:
    # Path to bundled SRI24 atlas artifacts
    atlas_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "atlas")
    atlas_nii_name: str = "sri24_tzo116plus_brats.nii.gz"
    atlas_labels_name: str = "sri24_labels.json"

    # Template space matching thresholds
    min_dice_available: float = 0.50
    min_dice_low_confidence: float = 0.25
    affine_tolerance: float = 1e-3

    # Answer cards configuration
    min_component_volume_ml: float = 0.1  # ignore blobs under 0.1 mL (noise filter)
    midline_band_mm: float = 5.0          # +/- 5mm from midline in world x considered "Midline / Bilateral"

    # Reporting thresholds for summary sentences
    pct_predominant: float = 60.0         # >= 60%: "predominantly in the <region>"
    pct_substantial: float = 30.0         # 30-60%: "substantially involves the <region>"
    pct_partial: float = 10.0             # 10-30%: "partially involves the <region>"
    secondary_min_pct: float = 10.0       # regions >= 10% listed as secondary
    table_min_pct: float = 0.5            # minimum percentage to show in table (unless outside atlas)

    # Mandatory disclaimers
    section_disclaimer: str = (
        "Anatomical localization is an approximate research-use estimate derived "
        "from model-predicted voxels and atlas overlap. It is not a clinical diagnosis "
        "and may be inaccurate."
    )
    global_banner: str = (
        "Suspected tumour regions are predicted by an AI model for research and "
        "education only. This is not a diagnosis and is not a substitute for clinical interpretation."
    )

    # Hard-coded safety prohibited phrases
    forbidden_phrases: List[str] = field(default_factory=lambda: [
        "tumour detected",
        "diagnostic system",
        "replaces the radiologist",
        "diagnosis of",
        "prognosis",
        "grade",
    ])


DEFAULT_CONFIG = LocalizationConfig()
