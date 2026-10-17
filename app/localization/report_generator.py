"""
Deterministic Report Generator for Anatomical Localization.
Uses fixed sentence templates driven strictly by computed percentages.
Guarantees absence of clinical diagnosis, grading, prognosis, or unverified claims.
"""

from typing import Dict, Any, List, Optional
from .config import LocalizationConfig, DEFAULT_CONFIG


def validate_text_safety(text: str, config: Optional[LocalizationConfig] = None) -> List[str]:
    """
    Checks that forbidden phrases do not appear in the generated text.
    Returns a list of violations (empty if text is safe).
    """
    cfg = config or DEFAULT_CONFIG
    violations = []
    text_lower = text.lower()
    for phrase in cfg.forbidden_phrases:
        if phrase.lower() in text_lower:
            violations.append(phrase)
    return violations


def format_compartment_paragraph(
    compartment_name: str,
    table_rows: List[Dict[str, Any]],
    pct_key: str,
    ml_key: str,
    total_voxels: int,
    config: LocalizationConfig
) -> str:
    """
    Generates a deterministic summary paragraph for one tumour compartment (WT, TC, ET).
    Sentence templates:
      - >= 60%: "Suspected <compartment> predicted by the model is predominantly in the <region>."
      - 30-60%: "Suspected <compartment> predicted by the model substantially involves the <region>."
      - 10-30%: "Suspected <compartment> predicted by the model partially involves the <region>."
      - < 10%: omitted from the summary.
    """
    if total_voxels == 0:
        return f"No suspected {compartment_name.lower()} region predicted by the model."

    # Filter named regions (ignore "Outside atlas / unlabelled" for primary phrasing unless it's dominant)
    named_rows = [r for r in table_rows if r["region"] != "Outside atlas / unlabelled" and r.get(pct_key, 0) > 0]
    outside_row = next((r for r in table_rows if r["region"] == "Outside atlas / unlabelled"), None)

    if not named_rows:
        if outside_row and outside_row.get(pct_key, 0) > 0:
            return (
                f"Suspected {compartment_name.lower()} predicted by the model is located outside "
                f"the standard atlas parcellation boundaries ({outside_row[pct_key]:.1f}% of estimated volume, {outside_row[ml_key]:.2f} mL)."
            )
        return f"No suspected {compartment_name.lower()} region predicted by the model."

    named_rows_sorted = sorted(named_rows, key=lambda x: x[pct_key], reverse=True)

    predominant = [r for r in named_rows_sorted if r[pct_key] >= config.pct_predominant]
    substantial = [r for r in named_rows_sorted if config.pct_substantial <= r[pct_key] < config.pct_predominant]
    partial = [r for r in named_rows_sorted if config.pct_partial <= r[pct_key] < config.pct_substantial]

    sentences = []

    if predominant:
        top = predominant[0]
        sentences.append(
            f"Suspected {compartment_name.lower()} predicted by the model is predominantly in the {top['region']} "
            f"({top[pct_key]:.1f}% of estimated volume, {top[ml_key]:.2f} mL)."
        )
    elif substantial:
        parts = [f"{r['region']} ({r[pct_key]:.1f}%, {r[ml_key]:.2f} mL)" for r in substantial]
        sentences.append(
            f"Suspected {compartment_name.lower()} predicted by the model substantially involves the {', '.join(parts)}."
        )

    if partial:
        parts = [f"{r['region']} ({r[pct_key]:.1f}%, {r[ml_key]:.2f} mL)" for r in partial]
        sentences.append(
            f"Suspected {compartment_name.lower()} predicted by the model partially involves the {', '.join(parts)}."
        )

    if not sentences:
        top = named_rows_sorted[0]
        sentences.append(
            f"Suspected {compartment_name.lower()} predicted by the model is dispersed across multiple anatomical regions, "
            f"with the largest involvement in the {top['region']} ({top[pct_key]:.1f}%, {top[ml_key]:.2f} mL)."
        )

    # Note outside atlas share if >= 10%
    if outside_row and outside_row.get(pct_key, 0) >= 10.0:
        sentences.append(
            f"An estimated {outside_row[pct_key]:.1f}% ({outside_row[ml_key]:.2f} mL) extends outside catalogued atlas structures."
        )

    return " ".join(sentences)


def generate_localization_report_text(
    localization_data: Dict[str, Any],
    config: Optional[LocalizationConfig] = None
) -> Dict[str, Any]:
    """
    Generates deterministic text for the Anatomical Localization section.
    Returns paragraphs for WT, TC, ET, disclaimer, and Answer Cards summaries.
    """
    cfg = config or DEFAULT_CONFIG
    status = localization_data.get("status", "unavailable")
    mode = localization_data.get("mode", "Mode B (Coarse Geometric Fallback)")
    answer_cards = localization_data.get("answer_cards", {})
    table_rows = localization_data.get("table", [])

    card1 = answer_cards.get("card_one_mass_or_several", {})
    card2 = answer_cards.get("card_which_side", {})
    card3 = answer_cards.get("card_how_big", {})

    disclaimer = cfg.section_disclaimer

    # Handle Mode B / Unavailable status
    if status == "unavailable" or mode.startswith("Mode B"):
        mode_b = localization_data.get("mode_b_data") or {}
        coarse_summary = mode_b.get("summary") or "Approximate coarse position: no atlas available."
        wt_para = f"Anatomical localization unavailable: input is not in the atlas template space. {coarse_summary}"
        tc_para = "Tumour core anatomical localization unavailable (coarse mode)."
        et_para = "Enhancing tumour anatomical localization unavailable (coarse mode)."

        full_text = f"{disclaimer}\n\n{wt_para}\n\n{tc_para}\n\n{et_para}"
        violations = validate_text_safety(full_text, cfg)
        if violations:
            raise ValueError(f"Safety violation: forbidden phrases detected in generated report: {violations}")

        return {
            "disclaimer": disclaimer,
            "status": status,
            "mode": mode,
            "wt_paragraph": wt_para,
            "tc_paragraph": tc_para,
            "et_paragraph": et_para,
            "answer_cards_summary": {
                "masses": card1.get("summary", ""),
                "side": card2.get("summary", ""),
                "volume": card3.get("summary", "")
            },
            "full_text": full_text
        }

    # MODE A: Generate deterministic paragraphs for each compartment
    wt_vox = card3.get("wt_voxels", 0)
    tc_vox = card3.get("tc_voxels", 0)
    et_vox = card3.get("et_voxels", 0)

    wt_paragraph = format_compartment_paragraph(
        "Whole-tumour region", table_rows, "wt_pct", "wt_ml", wt_vox, cfg
    )
    tc_paragraph = format_compartment_paragraph(
        "Tumour core", table_rows, "tc_pct", "tc_ml", tc_vox, cfg
    )
    et_paragraph = format_compartment_paragraph(
        "Enhancing tumour", table_rows, "et_pct", "et_ml", et_vox, cfg
    )

    full_text = (
        f"{disclaimer}\n\n"
        f"{wt_paragraph}\n\n"
        f"{tc_paragraph}\n\n"
        f"{et_paragraph}"
    )

    violations = validate_text_safety(full_text, cfg)
    if violations:
        raise ValueError(f"Safety violation: forbidden phrases detected in generated report: {violations}")

    return {
        "disclaimer": disclaimer,
        "status": status,
        "mode": mode,
        "wt_paragraph": wt_paragraph,
        "tc_paragraph": tc_paragraph,
        "et_paragraph": et_paragraph,
        "answer_cards_summary": {
            "masses": card1.get("summary", ""),
            "side": card2.get("summary", ""),
            "volume": card3.get("summary", "")
        },
        "full_text": full_text
    }
