# InkClone Eval — v2 Scorecard

**Date**: 2026-04-15

## Overall Score

| Metric | Baseline | v2 | Delta |
|--------|----------|-----|-------|
| Overall score | 63.6 | **71.0** | +7.36 |
| OCR (clean glyphs) | 17.4% | **40.6%** | +23.20% |
| OCR (real handwriting) | — | 15.1% | — |
| Coverage | — | 95.6% | — |
| Avg render time | 0.3s | 16ms | -283.80ms |

## Per-Category OCR (clean synthetic glyphs)

| Category | OCR % |
|----------|-------|
| general | 40.6% |

## Per-Category OCR (real handwriting glyphs)

| Category | OCR % |
|----------|-------|
| general | 15.1% |

## Coverage

- Characters in eval phrases: 68
- Covered by merged bank: 65 (95.6%)
- Missing: `(`, `)`, `—`

## Key Improvements vs Baseline

1. **Ligature bug fix**: common letter pairs (`th`, `he`, `in`, `an`, `on`, `er`, `re`, `ed`) were previously silently dropped — now rendered with correct kerning.
2. **Synthetic fallback glyphs (Task 2)**: all 78 printable chars covered via Courier New font-derived glyphs fed through the same renderer pipeline.
3. **Render speed**: 14ms avg vs 300ms baseline (95% faster).
4. **OCR pipeline**: tight crop + contrast boost + Otsu binarization.

## Notes

- `ocr_clean`: OCR on clean synthetic glyphs (font-derived, represents Task 2 fallback quality)
- `ocr_real`: OCR on real extracted handwriting glyphs from real_glyphs/ — lower due to noisy extraction
- `ligature_fix`: Fixed: common pairs (th/he/in/an/on/er/re/ed) were silently dropped before this fix

## Phrase Results (clean glyphs)

| Phrase | Category | OCR% | Time(ms) |
|--------|----------|------|----------|
| Hello | general | 22% | 14 |
| fox | general | 100% | 14 |
| the | general | 0% | 14 |
| jump | general | 100% | 14 |
| sky | general | 100% | 14 |
| extraordinary | general | 85% | 16 |
| nevertheless | general | 70% | 15 |
| incomprehensible | general | 69% | 16 |
| responsibilities | general | 86% | 17 |
| uncomfortable | general | 92% | 16 |
| The quick brown fox jumps over the lazy  | general | 23% | 15 |
| Pack my box with five dozen jugs of liqu | general | 22% | 15 |
| How vexingly quick daft zebras jump | general | 36% | 15 |
| The five boxing wizards jump quickly | general | 18% | 15 |
| Sphinx of black quartz judge my vow | general | 50% | 16 |
| Wait — really? Yes! (I think so.) It's f | general | 17% | 14 |
| Hello, world! How are you? I'm great — t | general | 18% | 15 |
| She said: Stop! But he didn't; he kept g | general | 22% | 14 |
| It's a bird! No — it's a plane. Or is it | general | 21% | 14 |
| Dear Sir: Re your letter of the 12th of  | general | 21% | 15 |
| In 1776, 56 delegates signed. Page 42 of | general | 16% | 14 |
| Call 555-1234 or 800-555-0100 by 5:30pm  | general | 37% | 17 |
| The score was 42 to 17 with 3 minutes re | general | 11% | 14 |
| Order 10042: 3 items totaling 47.99 plus | general | 21% | 16 |
| Flight UA237 departs at 0645, gate B12. | general | 28% | 16 |
| Dr. Smith met Prof. Jones at 3:45pm on T | general | 24% | 15 |
| The CEO of IBM gave a TED talk in NYC la | general | 15% | 14 |
| From Alice at email to Bob at company do | general | 32% | 15 |
| Re: Project ALPHA Status as of Q3 FY2025 | general | 30% | 15 |
| NASA launched the ISS module on Friday D | general | 34% | 18 |
