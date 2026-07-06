# ExtractApp — autonomous extraction reliability (v3A)

A **standalone, autonomous, deterministic** reliability layer for meta-analysis data extraction.
It runs after a model returns extraction JSON and before serialization, re-derives every number's
trustworthiness from evidence, and **physically separates trustworthy rows from untrustworthy ones**.

> **Quarantine over guess.** A number reaches the clean release table only if it is
> second-source/image-confirmed or passes every hard check. Otherwise it is **nulled and logged**,
> never emitted as if clean. In an autonomous pipeline a wrong effect size silently corrupts the
> meta-analysis; a missing cell only shrinks it.

- **No human in the loop.** The run self-certifies; the release gate is physical, not an approval step.
- **Universal.** Any article / design / effect measure. Graded on a synthetic corpus, never a real paper.
- **Deterministic.** Same input → byte-identical output. The VLM rung is optional, off by default,
  and never runs in CI.

## Layout
```
pipeline/     the reliability chain: numbers → battery → localize → readers →
              reconcile → grounding → reliability → segment → load/validate
tests/        unit tests + tests/golden/ (the acceptance corpus)
docs/         spec.md (source of truth), taxonomy.md, CHANGELOG.md
```

## Run the tests (the acceptance gate)
```
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pytest -q
```
Tesseract and the VLM are optional rungs — absent → they degrade to `needs_vision`, never crash.

## Output
`extract(...)` writes `*_RELEASE.xlsx` when zero hard checks fail, else `*_DRAFT.xlsx` with quarantined
values nulled and a QUARANTINE sheet. Every workbook carries VALIDATION, QUARANTINE, and RELIABILITY
sheets plus a `STATUS:` stamp in README cell A1.

See [docs/spec.md](docs/spec.md) for the full architecture and [docs/taxonomy.md](docs/taxonomy.md)
for the corruption catalogue.
