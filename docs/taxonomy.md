# Corruption taxonomy

Every item below is a real failure mode of PDF text extraction on scientific tables. Each has at
least one golden-corpus fixture and a named detector/repair. "Detector" = what flags it; "Repair" =
which reader rung recovers it (or `quarantine` if unconfirmable).

| # | Corruption | Example (printed → text layer) | Detector | Repair |
|---|---|---|---|---|
| 1 | Dropped leading minus | `−0.10` → `0.10` | battery: CI-vs-p, point-in-CI | pdfplumber re-read; else constraint solver (unique sign flip); else raster |
| 2 | Lost `±` (mean±sd merged) | `2.59 ± 0.75` → `2.59 0.75` / `2.590.75` | numbers: intra-number space; battery: sd plausibility | numbers split on `±` preimage; raster tiebreak |
| 3 | En-dash / hyphen as minus | `–0.10` / `‑0.10` → mixed | numbers: unify to `-` | safe unification (direct) |
| 4 | Footnote/reference superscript glued | `1.33ᵃ` / `1.33[12]` → `1.3312` | numbers: strip trailing superscript/ref | safe strip (direct), battery confirms magnitude |
| 5 | Thousands-separator confusion | `1,234` → `1.234` or `1234` | numbers: thousands vs decimal; battery magnitude | safe normalize; battery range check |
| 6 | Decimal-mark confusion | `0,53` (EU) → `0.53` | numbers: decimal-mark normalize | safe normalize |
| 7 | `×/x/9` OCR/glyph swap | `×10` ↔ `x10` ↔ `910` | numbers: **lossy** candidate, battery-tested | position-guarded hypothesis → battery picks |
| 8 | `O/0`, `l/1` swaps | `l.43` → `1.43`, `O.06` → `0.06` | numbers: **lossy** candidate, battery-tested | position-guarded hypothesis → battery picks |
| 9 | Stray intra-number spaces | `- 0.21` / `0. 51` → split | numbers: collapse guarded spaces | safe collapse |
| 10 | Log-scale ratio CI (asymmetric) | OR `1.24 (0.87, 1.77)` | battery: `point ≈ geomean(CI)` on log scale, null=1 | soft check; not-evaluable if level unknown |
| 11 | Percent printed without its n | `41%` with no denominator | battery: `pct≈100·events/total` precondition fails | soft `low` + needs the n; never fabricated |
| 12 | Median/IQR mislabeled as mean/SD | `median [IQR]` stored as `mean (sd)` | battery: `iqr_low ≤ median ≤ iqr_high`, sd≥0 sanity | soft `low`, flag mislabel |

## Disagreement fixtures (force reconcile → raster to run and win)
For items 1, 2, 7, 8 the corpus includes a variant where the **text view is corrupted but the bbox
image view holds the correct value**. These force `reconcile.py` to detect disagreement and let the
raster/second-source rung win — proving the reconciliation path executes, not just clean-agreement.

## Real synthetic PDFs
A few `fitz`-built PDFs embed known values at known bboxes so the **actual** rasterizer + pdfplumber
reader + cell localization run end-to-end in CI (deterministic, no network, no real paper).

## Hard vs soft (which failures quarantine)
- **HARD** (impossible → quarantine if unconfirmable): events>total, ci_lower>ci_upper, point∉CI,
  p∉[0,1], sd<0, count<0, proportion∉[0,1].
- **SOFT** (implausible → keep, mark `low`): n-sums, subgroup sums, geomean(CI), SE↔CI-width, pct↔events/total.
- **Precondition-guarded** (never a fail when inputs unknown): CI-vs-p, log-geomean.
