# CHANGELOG

## v3.0.0a — autonomous single-pass reliability layer (initial build)

A standalone, deterministic, fail-safe reliability layer that runs after extraction and physically
separates trustworthy numbers from untrustworthy ones. Quarantine over guess: a value reaches the
clean release table only if it is second-source/image-confirmed or passes every hard check;
otherwise it is nulled and logged.

### Engines & battery
- **numbers.py** — canonical normalization preserving reported decimals. Safe unifications applied
  directly (dash/minus variants, footnote/reference superscripts, thousands/decimal marks,
  intra-number spaces); lossy glyph swaps (`O/0`, `l/1`, …) only as battery-tested candidates.
- **battery.py** — data-type/measure self-consistency in three tiers: **HARD** (impossible →
  quarantine), **SOFT** (implausible → keep + `low`), **GUARDED** (CI-vs-p, log-geomean; fire only
  when `ci_level`/`p_sided`/`alpha` are known). Ratios on the log scale, null = 1.
- **localize.py** — binds numbers to cells by row/column **semantics, never by value**;
  0-match → `unlocalized`, ≥2-match → ambiguous; both quarantine.
- **readers.py** — cheapest-first second-source ladder: pdfplumber → constraint solver → Tesseract
  charset OCR → VLM stub (off). Constraint solver fixes a hard-broken value only on a **unique**
  hard-clean candidate; text-vs-text disagreement escalates to the image rung; OCR/VLM absent →
  degrade to `needs_vision`, never crash.
- **reconcile.py** — Engine 1 two-view decision: confirm / correct (image wins on disagreement) /
  quarantine. `source_modality=table-image` only when an image was actually read.
- **grounding.py** — Engine 3: a value must be locatable within its **own** cell/span; computed
  derivations are exempt; ungroundable directly-reported values are quarantined.
- **reliability.py** — orchestrator + deterministic rubric (sole authority, overwrites model
  confidence). Emits per-field annotations, quarantine entries, and telemetry.

### Serializer & gate
- **segment.py** — keeps `find_tables()` geometry → grids with cell bboxes, text spans, and a
  `missing_images` manifest; `rasterize_region()` crops a cell for the OCR/VLM rungs.
- **validate.py / load.py** — VALIDATION runs the full battery; **release gate** emits
  `*_RELEASE.xlsx` iff zero hard-fail **and** nothing quarantined, else `*_DRAFT.xlsx` with
  quarantined values nulled. Workbook carries VALIDATION / QUARANTINE / RELIABILITY sheets and a
  README A1 STATUS stamp. Output is **byte-deterministic** (fixed doc timestamps + normalized zip).

### Golden corpus (acceptance gate)
`tests/golden/` — one fixture per corruption-taxonomy item (dropped minus, en-dash minus, merged
superscript/reference, thousands/decimal confusion, intra-number spaces, `O/0` & `l/1` swaps,
log-scale ratio CI, percent-inconsistency, median/IQR mislabel) + clean controls + a disagreement
(image-wins) fixture + a real `fitz`-built PDF exercising the rasterizer and pdfplumber reader.
Acceptance: catch every planted corruption, pass every control, quarantine the unconfirmable, and be
byte-deterministic across two runs. **84 tests**, all deterministic; OCR/VLM never run in CI.

### Repo & CI
Private GitHub repo, `main` protected (PR merges). GitHub Actions runs `pytest` incl. the golden
corpus and a determinism check on Python 3.11/3.12; red blocks merge. No secrets in the repo.
