"""
NeuroScope 3D Anatomical Localization Package.
Provides template-space atlas mapping (Mode A), coarse geometric fallback (Mode B),
three trainee Answer Cards, and deterministic template-based report summaries.
"""

from .config import LocalizationConfig
from .anatomical_mapper import AnatomicalMapper, LocalizationResult
from .report_generator import generate_localization_report_text

__all__ = [
    "LocalizationConfig",
    "AnatomicalMapper",
    "LocalizationResult",
    "generate_localization_report_text",
]
