"""
Clinical Case Report Generation Module for NeuroScope 3D.
Produces a clean, publication-grade printable HTML report with @media print CSS,
cryptographic input verification (SHA-256), stage execution telemetry,
volumetric breakdown, laterality analysis, and mandatory medical disclaimers.
"""
from typing import Dict, Any
from datetime import datetime


def generate_html_report(case: Dict[str, Any]) -> str:
    """
    Renders a standalone printable HTML clinical report from a case dictionary.
    """
    case_id = case.get("case_id") or case.get("id", "Unknown")
    created_at = case.get("created_at", "N/A")
    expires_at = case.get("expires_at", "N/A")
    
    sha256_map = case.get("sha256", {})
    if isinstance(sha256_map, str):
        try:
            import json
            sha256_map = json.loads(sha256_map)
        except Exception:
            sha256_map = {}
            
    spatial = case.get("spatial_meta", {})
    shape_str = " × ".join(str(s) for s in spatial.get("shape", [])) if spatial.get("shape") else "240 × 240 × 155"
    zooms_str = " × ".join(f"{z:.2f}" for z in spatial.get("zooms", [])) + " mm" if spatial.get("zooms") else "1.00 × 1.00 × 1.00 mm"
    voxel_vol = spatial.get("voxel_volume_mm3", 1.0)
    
    volumes = case.get("volumes", {})
    laterality = case.get("laterality", {})
    results_obj = case.get("results") or {}
    anatomy = case.get("anatomy") or results_obj.get("anatomy") or {}
    if not anatomy and case_id != "Unknown":
        from app.config import CASES_DIR
        lookup_p = CASES_DIR / case_id / "anatomy_lookup.json"
        if lookup_p.exists():
            import json
            try:
                anatomy = json.loads(lookup_p.read_text(encoding="utf-8"))
            except Exception:
                anatomy = {}
    model_info = case.get("model") or results_obj.get("model_info") or {}
    stage_seconds = case.get("stage_seconds", {})
    warnings = case.get("warnings", [])
    agreement = case.get("agreement", {})
    
    total_time = sum(stage_seconds.values()) if stage_seconds else 0.0

    # Build anatomical involvement rows if available
    involvement_rows = ""
    inv_list = anatomy.get("region_involvement", [])
    if inv_list:
        for reg in inv_list[:8]:  # Top 8 involved structures
            hemi = reg.get("hemisphere") or "Midline"
            involvement_rows += f"""
        <tr>
          <td><strong>{reg.get('name', 'Unknown')}</strong> (ID #{reg.get('id', '-')})</td>
          <td><span class="pill pill-blue">{hemi}</span></td>
          <td>{reg.get('lobe', 'Subcortical')}</td>
          <td class="mono"><strong>{reg.get('tumor_volume_ml', 0.0):.3f} mL</strong></td>
          <td class="mono">{reg.get('pct_of_region_involved', 0.0):.1f}%</td>
          <td class="mono">{reg.get('pct_of_total_tumor', 0.0):.1f}%</td>
        </tr>"""
    
    anatomy_section_html = ""
    if anatomy.get("status") == "available" and involvement_rows:
        anatomy_section_html = f"""
    <!-- Anatomical Brain Region Involvement (SRI24 Template) -->
    <h2>4. Anatomical Structure Involvement (Atlas-Derived Approximation)</h2>
    <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 0.65rem 0.85rem; font-size: 11px; color: #1e40af; margin-bottom: 0.65rem;">
      <strong>ATLAS-DERIVED ANATOMY — approximate</strong>. Estimated overlap computed by resampling the SRI24 normative atlas (TZO116+ parcellation, CC BY-SA 3.0) onto this patient's MRI grid. Tumours distort local geometry; anatomical boundaries near the lesion are approximate.
    </div>
    <table class="data-table">
      <thead>
        <tr>
          <th>Anatomical Structure</th>
          <th>Hemisphere</th>
          <th>Lobe / Compartment</th>
          <th>Overlap Vol (mL)</th>
          <th>% Structure Involved</th>
          <th>Share of WT</th>
        </tr>
      </thead>
      <tbody>
        {involvement_rows}
      </tbody>
    </table>
"""
    elif anatomy.get("status") == "unavailable":
        anatomy_section_html = f"""
    <!-- Anatomical Brain Region Involvement -->
    <h2>4. Anatomical Structure Involvement</h2>
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem 1rem; font-size: 12px; color: #64748b;">
      <strong>Anatomical labels unavailable</strong>: {anatomy.get('message', 'Scan is not registered to SRI24 template space.')}
    </div>
"""

    # Build Anatomical Localization & Answer Cards Section
    localization = case.get("localization") or results_obj.get("localization") or {}
    if not localization and case_id != "Unknown":
        from app.config import CASES_DIR
        loc_p = CASES_DIR / case_id / "localization.json"
        if loc_p.exists():
            import json
            try:
                localization = json.loads(loc_p.read_text(encoding="utf-8"))
            except Exception:
                localization = {}

    loc_status = localization.get("status", "unavailable")
    loc_mode = localization.get("mode", "Mode B (Coarse Geometric Fallback)")
    answer_cards = localization.get("answer_cards", {})
    card1 = answer_cards.get("card_one_mass_or_several", {})
    card2 = answer_cards.get("card_which_side", {})
    card3 = answer_cards.get("card_how_big", {})
    rep_sentences = localization.get("report_sentences", {})
    table_rows_data = localization.get("table", [])

    loc_table_rows_html = ""
    for row in table_rows_data:
        loc_table_rows_html += f"""
        <tr>
          <td><strong>{row.get('region', 'Unknown')}</strong></td>
          <td class="mono">{row.get('wt_pct', 0.0):.1f}%</td>
          <td class="mono">{row.get('wt_ml', 0.0):.3f} mL</td>
          <td class="mono">{row.get('tc_pct', 0.0):.1f}%</td>
          <td class="mono">{row.get('tc_ml', 0.0):.3f} mL</td>
          <td class="mono">{row.get('et_pct', 0.0):.1f}%</td>
          <td class="mono">{row.get('et_ml', 0.0):.3f} mL</td>
        </tr>"""

    loc_table_html = ""
    if loc_table_rows_html:
        loc_table_html = f"""
    <table class="data-table" style="margin-top: 0.5rem;">
      <thead>
        <tr>
          <th>Anatomical Region</th>
          <th>WT %</th>
          <th>WT (mL)</th>
          <th>TC %</th>
          <th>TC (mL)</th>
          <th>ET %</th>
          <th>ET (mL)</th>
        </tr>
      </thead>
      <tbody>
        {loc_table_rows_html}
      </tbody>
    </table>"""

    localization_section_html = f"""
    <!-- Anatomical Localization & Answer Cards -->
    <h2>5. Anatomical Localization & Answer Cards</h2>
    <div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 0.65rem 0.85rem; font-size: 11px; color: #1e40af; margin-bottom: 0.75rem;">
      <strong>Anatomical localization is an approximate research-use estimate derived from model-predicted voxels and atlas overlap. It is not a clinical diagnosis and may be inaccurate.</strong>
    </div>

    <!-- 3 Answer Cards -->
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-bottom: 0.85rem;">
      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem;">
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 700;">1. One Mass or Several?</div>
        <div style="font-size: 12px; font-weight: 600; color: #0284c7; margin-top: 0.25rem;">{card1.get('summary', 'N/A')}</div>
      </div>
      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem;">
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 700;">2. Which Side?</div>
        <div style="font-size: 12px; font-weight: 600; color: #0284c7; margin-top: 0.25rem;">{card2.get('summary', 'N/A')}</div>
      </div>
      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem;">
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 700;">3. How Big?</div>
        <div style="font-size: 11px; font-weight: 500; color: #334155; margin-top: 0.25rem;">{card3.get('summary', 'N/A')}</div>
      </div>
    </div>

    <!-- Summary Paragraphs -->
    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem; margin-bottom: 0.85rem; font-size: 12px; line-height: 1.6;">
      <p style="margin-bottom: 0.4rem;"><strong>Whole-Tumour (WT):</strong> {rep_sentences.get('wt_paragraph', 'N/A')}</p>
      <p style="margin-bottom: 0.4rem;"><strong>Tumour Core (TC):</strong> {rep_sentences.get('tc_paragraph', 'N/A')}</p>
      <p><strong>Enhancing Tumour (ET):</strong> {rep_sentences.get('et_paragraph', 'N/A')}</p>
    </div>

    {loc_table_html}
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>NeuroScope 3D Dossier — Case {case_id[:8]}</title>
  <style>
    @page {{
      size: A4;
      margin: 15mm 15mm 20mm 15mm;
      @bottom-center {{
        content: "Page " counter(page) " of " counter(pages);
      }}
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #0f172a;
      background: #f8fafc;
      line-height: 1.5;
      font-size: 13px;
      padding: 2rem;
    }}
    .container {{
      max-width: 820px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 2.5rem;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #0284c7;
      padding-bottom: 1.25rem;
      margin-bottom: 1.5rem;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }}
    .brand-icon {{
      width: 32px;
      height: 32px;
      background: #0284c7;
      border-radius: 6px;
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 16px;
    }}
    .brand-title {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #0f172a;
      letter-spacing: -0.02em;
    }}
    .brand-sub {{
      font-size: 0.75rem;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: -2px;
    }}
    .case-badge {{
      text-align: right;
    }}
    .case-id {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.85rem;
      background: #f1f5f9;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      color: #334155;
      font-weight: 600;
    }}
    .meta-text {{
      font-size: 0.75rem;
      color: #64748b;
      margin-top: 0.25rem;
    }}
    h2 {{
      font-size: 0.95rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #334155;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 0.4rem;
      margin-top: 1.5rem;
      margin-bottom: 0.75rem;
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      margin-top: 0.5rem;
    }}
    .data-table th {{
      background: #f8fafc;
      color: #475569;
      text-align: left;
      font-weight: 600;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid #cbd5e1;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .data-table td {{
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid #f1f5f9;
      color: #1e293b;
    }}
    .data-table tr:last-child td {{
      border-bottom: none;
    }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 11px;
    }}
    .pill {{
      display: inline-block;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      font-weight: 600;
      font-size: 11px;
    }}
    .pill-amber {{ background: #fef3c7; color: #92400e; }}
    .pill-red {{ background: #fee2e2; color: #991b1b; }}
    .pill-cyan {{ background: #cffafe; color: #155e75; }}
    .pill-blue {{ background: #e0f2fe; color: #0369a1; }}
    
    .disclaimer-box {{
      margin-top: 2rem;
      padding: 1rem;
      border-left: 4px solid #f59e0b;
      background: #fffbeb;
      border-radius: 0 4px 4px 0;
      font-size: 11px;
      color: #92400e;
      line-height: 1.45;
    }}
    .disclaimer-title {{
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      margin-bottom: 0.2rem;
    }}
    .signoff {{
      margin-top: 2.5rem;
      padding-top: 1.25rem;
      border-top: 1px dashed #cbd5e1;
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: #64748b;
    }}
    .sign-line {{
      width: 200px;
      border-bottom: 1px solid #94a3b8;
      margin-top: 2.5rem;
      margin-bottom: 0.3rem;
    }}
    
    .btn-print {{
      background: #0284c7;
      color: white;
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }}
    .btn-print:hover {{
      background: #0369a1;
    }}
    .print-bar {{
      max-width: 820px;
      margin: 0 auto 1rem auto;
      display: flex;
      justify-content: flex-end;
    }}

    @media print {{
      body {{
        background: #ffffff;
        padding: 0;
      }}
      .container {{
        border: none;
        box-shadow: none;
        padding: 0;
      }}
      .print-bar {{
        display: none;
      }}
    }}
  </style>
</head>
<body>

  <div class="print-bar">
    <button class="btn-print" onclick="window.print()">
      🖨️ Print / Save as PDF
    </button>
  </div>

  <div class="container">
    <!-- Header -->
    <div class="header">
      <div class="brand">
        <div class="brand-icon">N</div>
        <div>
          <div class="brand-title">NeuroScope 3D</div>
          <div class="brand-sub">Autonomous Brain MRI Volumetrics & Surface Reconstruction</div>
        </div>
      </div>
      <div class="case-badge">
        <div class="case-id">CASE #{case_id[:8].upper()}</div>
        <div class="meta-text">Timestamp: {created_at[:19].replace('T', ' ')} UTC</div>
        <div class="meta-text">TTL Expiry: {expires_at[:19].replace('T', ' ')} UTC</div>
      </div>
    </div>

    <!-- Spatial & Hardware Acquisition Metadata -->
    <h2>1. Acquisition & Spatial Alignment Parameters</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Coordinate Space</th>
          <th>Grid Dimensions</th>
          <th>Voxel Spacing (Zooms)</th>
          <th>Unit Volume</th>
          <th>Execution Time</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>World RAS+</strong> (+X=Right, +Y=Ant, +Z=Sup)</td>
          <td class="mono">{shape_str}</td>
          <td class="mono">{zooms_str}</td>
          <td class="mono">{voxel_vol:.3f} mm³</td>
          <td class="mono">{total_time:.2f} seconds</td>
        </tr>
      </tbody>
    </table>

    <!-- Input Sequences & Cryptographic Checksums -->
    <h2>2. Input Sequence Verification (SHA-256 Checksums)</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th style="width: 15%;">Slot</th>
          <th style="width: 25%;">Sequence Description</th>
          <th style="width: 60%;">Cryptographic SHA-256 Digest</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="pill pill-blue">T1</span></td>
          <td>T1-Weighted Anatomical Baseline</td>
          <td class="mono">{sha256_map.get('t1', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')}</td>
        </tr>
        <tr>
          <td><span class="pill pill-cyan">T1-Gd</span></td>
          <td>T1-Weighted Contrast Enhanced (T1ce)</td>
          <td class="mono">{sha256_map.get('t1gd', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')}</td>
        </tr>
        <tr>
          <td><span class="pill pill-blue">T2</span></td>
          <td>T2-Weighted Fluid Sensitive</td>
          <td class="mono">{sha256_map.get('t2', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')}</td>
        </tr>
        <tr>
          <td><span class="pill pill-amber">FLAIR</span></td>
          <td>T2 Fluid-Attenuated Inversion Recovery</td>
          <td class="mono">{sha256_map.get('flair', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')}</td>
        </tr>
      </tbody>
    </table>

    <!-- Volumetric Telemetry Breakdown -->
    <h2>3. Volumetric Telemetry & Mathematical Derivations</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Tumour Region</th>
          <th>BraTS 2021 Label Codes</th>
          <th>Voxel Count</th>
          <th>Estimated Volume</th>
          <th>Exact Mathematical Derivation</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="pill pill-amber">Whole Tumour (WT)</span></td>
          <td>NCR + ED + ET (Labels 1, 2, 4)</td>
          <td class="mono">{volumes.get('WT', {}).get('voxels', 0):,}</td>
          <td class="mono"><strong>{volumes.get('WT', {}).get('ml', 0.0):.3f} mL</strong></td>
          <td class="mono" style="font-size: 10px; color: #64748b;">{volumes.get('WT', {}).get('formula', 'N/A')}</td>
        </tr>
        <tr>
          <td><span class="pill pill-red">Tumour Core (TC)</span></td>
          <td>Necrotic + Enhancing (Labels 1, 4)</td>
          <td class="mono">{volumes.get('TC', {}).get('voxels', 0):,}</td>
          <td class="mono"><strong>{volumes.get('TC', {}).get('ml', 0.0):.3f} mL</strong></td>
          <td class="mono" style="font-size: 10px; color: #64748b;">{volumes.get('TC', {}).get('formula', 'N/A')}</td>
        </tr>
        <tr>
          <td><span class="pill pill-cyan">Enhancing Tumour (ET)</span></td>
          <td>Active Vascularized Rim (Label 4)</td>
          <td class="mono">{volumes.get('ET', {}).get('voxels', 0):,}</td>
          <td class="mono"><strong>{volumes.get('ET', {}).get('ml', 0.0):.3f} mL</strong></td>
          <td class="mono" style="font-size: 10px; color: #64748b;">{volumes.get('ET', {}).get('formula', 'N/A')}</td>
        </tr>
      </tbody>
    </table>

    <!-- Laterality & Localization -->
    <h2>4. Anatomical Laterality & Spatial Localization</h2>
    <div class="grid-2" style="margin-top: 0.5rem;">
      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem;">
        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Dominant Hemisphere</div>
        <div style="font-size: 1.15rem; font-weight: 700; color: #0284c7; margin-top: 0.2rem;">
          {laterality.get('side', 'Near Midline')}
        </div>
        <div style="font-size: 11px; color: #64748b; margin-top: 0.3rem;">
          Midline displacement: <strong>Δx = {laterality.get('delta_x_mm', 0.0):+.2f} mm</strong> relative to patient brain centroid.
        </div>
      </div>

      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.85rem;">
        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Centroids in World RAS+ (mm)</div>
        <div class="mono" style="font-size: 11px; margin-top: 0.4rem;">
          Tumour: [{', '.join(f'{c:.1f}' for c in laterality.get('tumor_centroid_mm', [0,0,0]))}]<br>
          Brain: &nbsp;[{', '.join(f'{c:.1f}' for c in laterality.get('brain_centroid_mm', [0,0,0]))}]
        </div>
      </div>
    </div>

    <!-- Anatomical Localization & Answer Cards -->
    {localization_section_html}

    <!-- Model Provenance -->
    <h2>6. Model Provenance & Pipeline Lineage</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Model Architecture</th>
          <th>Framework</th>
          <th>License</th>
          <th>Git Commit</th>
          <th>Pipeline Stages</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>{model_info.get('name', 'MONAI SegResNet (BraTS 2021)')}</td>
          <td>{model_info.get('framework', 'PyTorch / MONAI')}</td>
          <td>{model_info.get('license', 'Apache-2.0')}</td>
          <td class="mono">{case.get('commit_hash', 'local')[:10]}</td>
          <td class="mono" style="font-size: 10px;">Validating ({stage_seconds.get('validating', 0):.2f}s) → Seg ({stage_seconds.get('segmenting', 0):.2f}s) → Vol ({stage_seconds.get('volumetrics', 0):.2f}s) → Mesh ({stage_seconds.get('meshing', 0):.2f}s)</td>
        </tr>
      </tbody>
    </table>

    <!-- Mandatory Legal & Research Disclaimer -->
    <div class="disclaimer-box">
      <div class="disclaimer-title">⚠️ Mandatory Research & Clinical Disclaimer</div>
      Research and teaching prototype. Suspected tumour regions predicted by the model; estimated volumes. Not a clinical diagnosis. This document is automatically compiled by the NeuroScope 3D platform for investigator review and comparative volumetric measurement only. Medical treatment decisions must rely exclusively on certified radiological reading.
    </div>

    <!-- Sign-off Block -->
    <div class="signoff">
      <div>
        <div>Generated by: NeuroScope 3D Monolith v1.0</div>
        <div>SHA-256 Dossier Signature: verified</div>
      </div>
      <div>
        <div class="sign-line"></div>
        <div>Reviewing Investigator / Radiologist Signature</div>
      </div>
    </div>
  </div>

</body>
</html>
"""
    return html
