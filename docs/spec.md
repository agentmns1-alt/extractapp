# ExtractApp — autonomous single-pass extraction reliability (spec)

Version 3A. Source of truth lives in this repo, versioned with the code.

## Purpose
A **standalone, autonomous** reliability layer for a meta-analysis data-extraction app. It runs
after a model returns extraction JSON and **before** serialization. It re-derives every numeric
value's trustworthiness from evidence, overwrites any model-supplied confidence, and **physically
separates trustworthy rows from untrustworthy ones**. No human in the loop.

## Core design rule — quarantine over guess
A number reaches the clean release dataset only if it is **image/second-source-confirmed** OR
**passes every hard check**. Anything that fails a hard check and cannot be confirmed is **nulled
in the release table** and written to a QUARANTINE sheet with its reason. In an autonomous
pipeline an unflagged wrong effect size silently corrupts a meta-analysis; a missing cell only
shrinks it. When in doubt: withhold + log.

## Non-negotiables
- **Autonomous** — no approval gates, no coordinator, no manual step in the run.
- **Universal** — any article / design / effect measure; never tuned to a specific paper.
  Acceptance is graded on a synthetic corpus + schema, never on a real article.
- **Single pass** — no second-reviewer / adjudication logic.
- **Deterministic core** — same input → same output, byte-stable. The VLM is optional,
  off by default, cached, never in CI, never gates anything.
- **Fail safe, not silent** — the quarantine rule above.

## Module dependency chain (build bottom-up, unit-tested, committed per module)
1. **numbers.py** — normalize to canonical form (`-0.10`, decimals preserved).
   *Safe* unifications applied directly: minus/en-dash/hyphen/U+2212 → `-`; strip footnote/reference
   superscripts glued to numbers; thousands separators; decimal-mark; intra-number spaces.
   *Lossy* glyph swaps (`×/x/9`, `O/0`, `l/1`) are **position-guarded candidate hypotheses** tested
   against the battery — never applied eagerly.
2. **battery.py** — data-type/measure self-consistency. Branches null=0 (differences) vs null=1
   (ratios, on the **log scale**).
   - **HARD** (mathematically impossible → quarantine the value): `events>total`, `ci_lower>ci_upper`,
     `point ∉ [ci_lower,ci_upper]`, `p ∉ [0,1]`, `sd<0`, `count<0`, `proportion ∉ [0,1]`.
   - **SOFT** (implausible → keep value, mark `low`, log): arm n-sums, subgroup sums,
     `point ≈ geomean(CI)` for ratios, `SE ≈ (ci_upper−ci_lower)/(2z)`, `pct ≈ 100·events/total`.
   - **Precondition-guarded**: CI-vs-p and log-geomean fire only when `ci_level`/`p_sided`/`alpha`
     are known & consistent; otherwise `not-evaluable` (never a fail).
3. **localize.py** — bind each JSON number to `(page, table, row_label, col_label, bbox)` **without
   value-matching** (circular when the value is corrupted): reconstruct the cell grid from PyMuPDF
   `find_tables()` geometry and match JSON to cells by row/column **semantics** (header + stub labels).
   In-text numerics bind to `(page, text-span)`. Unlocalizable → `unlocalized` → nulled + quarantined.
4. **readers.py** — second-source reader ladder behind `read(page, bbox) -> (value, reader_conf)`,
   cheapest-first, stop when the battery passes:
   - (a) **pdfplumber** re-read (pure-Python, Poppler-free) — recovers most dropped glyphs; winner
     stays `source_modality=text`.
   - (b) **constraint solver** — apply a correction **only if exactly one** candidate satisfies
     point-in-CI ∧ CI-vs-p(when evaluable) ∧ magnitude/decimal preservation; 0 or ≥2 → refuse →
     quarantine `ambiguous-correction`.
   - (c) **Tesseract** (charset `0-9.,()−-`, pinned) on the cell raster → `source_modality=table-image`;
     **optional** — absent binary detected at startup → rung degrades to `needs_vision` (never crash).
   - (d) **VLM stub** — off by default, cached by cell-hash, never in CI.
   Text-vs-text disagreement (pdfplumber vs primary) does **not** auto-pick pdfplumber — it escalates
   to the raster/OCR rung as tiebreak.
5. **reconcile.py** — Engine 1: text view + next ladder rung, normalize-then-compare; agree → confirmed;
   disagree → raster/second-source wins; set `source_modality=table-image` only if an image was read.
6. **grounding.py** — Engine 3: the canonical string (or a battery-confirmed preimage) must be locatable
   **within the number's own localized cell/span** (not document-wide). **Skips** computed values
   (`derivation_method ∈ {derived, From SE, From 95% CI, From t/F, Pooled SD, …}`). Ungroundable →
   quarantine `ungrounded-value`.
7. **reliability.py** — orchestrator: walk every localized number → engines → **deterministic rubric**
   → annotate or quarantine → emit telemetry.
8. **segment.py** — capture table + cell bboxes (stop discarding `find_tables()` geometry), rasterize
   referenced regions on demand, store page+bbox on provenance, emit a `missing_images` manifest.
9. **load.py + validate.py** — VALIDATION runs the full battery; **RELEASE gate**: emit `*_RELEASE.xlsx`
   only if zero hard checks fail after reliability; else `*_DRAFT.xlsx` with quarantined values nulled +
   a QUARANTINE sheet. Also RELIABILITY telemetry sheet and README A1 STATUS.

## Deterministic confidence rubric (sole authority; overwrites model confidence)
Applied mechanically, in order:
- **high** — confirmed (Engine-1 agree, or raster/second-source clear) AND passes all hard checks AND
  directly reported (`derivation_method ∈ {Reported directly, Author-provided}`).
- **medium** — text-only but passes the battery and directly reported; OR confirmed via a standard
  transform (`From 95% CI` / `From SE` / `From t/F`).
- **low** — soft-fail but hard-clean (kept in release, flagged); carries `needs_vision` when a value
  could exist in an image not supplied.
- **quarantine** — hard-fail & unconfirmable, `unlocalized`, `ambiguous-correction`, or
  `ungrounded-value` → **nulled in release**, listed in QUARANTINE.

## Release gate & sheets
- `*_RELEASE.xlsx` iff zero hard checks fail after reliability; otherwise `*_DRAFT.xlsx`.
- README cell A1: `STATUS: RELEASE` or `STATUS: DRAFT — NOT RELEASE READY (N quarantined / M hard-fail)`.
- **VALIDATION** — every hard/soft/guarded check: name / status / count / detail / ISO timestamp.
- **QUARANTINE** — every withheld number: sheet / row_id / field / reason (nulled in the data sheets).
- **RELIABILITY** — telemetry per run and per sheet: % confirmed, % each hard/soft fail, % needs_vision,
  % quarantined, confidence distribution.
- Provenance columns (three orthogonal axes) + `extractor` audit stamp carried from the v2 template.

## Determinism
Canonical, stably-ordered output; no wall-clock in the data (run_ts is injected). Two runs on the same
input produce byte-identical workbooks. Enforced by `tests/test_determinism.py` in CI.

## Non-goals
No dual-review / adjudication. No live-VLM gating. No real-paper tuning in the acceptance path.
No web UI in this layer (it is a pipeline, invoked programmatically or by CLI).
