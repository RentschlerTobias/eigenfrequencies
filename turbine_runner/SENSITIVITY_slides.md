# Resonance-only DE — Sensitivität & Ergebnisse

**Variante:** `EVAL_MODE=resonance_only` · 30 dtOO-Design-Parameter · pop 32 · 100 Gen target
**Status:** Lauf nach 12 Gen walltime-gekillt (gen 12 partial). Best 7.358 → **4.903** (−33 %). Wall ~270 s/Gen, total ~58 min.

---

## Konvergenzverlauf (resonance-only)

| Gen | Best f | Mean f | ok/n | t_gen_s | f₁ (Hz) |
|------:|------:|------:|------:|------:|------:|
| 0    | 7.358 | 125011 | 28/32 | 268 | 25.84 |
| 3    | 6.015 | 125009 | 28/32 | 284 | 26.84 |
| 6    | 5.254 | 62508  | 30/32 | 292 | 30.94 |
| 9    | 5.041 | 31257  | 31/32 | 268 | 32.11 |
| 12   | **4.903** | 31256 | 31/32 | 99 (partial) | 30.22 |

- 3 Gen stagnierend bei 7.358 (gen-0 = init-Jitter); ab gen 3 Bruch.
- Mean-Wert drückt sich nur, weil dtoo-fails von 4 → 2 → 1 sinken (DTOO_FAIL_PENALTY=1e6 kontaminiert mean). Konvergenz also an **best** ablesen, nicht mean.
- 1× dtOO-Build-Fail pro Generation — `map2dTo3d::reparamOnFace` (auch combi-Lauf, unverändert).
- f₁ (tiefste elastische Mode) oszilliert 25,8…32,1 Hz; Sprung korreliert mit strukturellen Sprüngen in best.

---

## Sensitivitätsanalyse (31 valide Individuen, Spearman vs. `f_resonance`)

| Rang | Label | ρ | Richtung |
|----:|-------|------:|-----------|
| 1 | `cV_ru_alpha_2_ex_1.0`   | −0.732 | ↑ → besser |
| 2 | `cV_ru_offsetM_ex_0.5`  | +0.723 | ↓ → besser |
| 3 | `cV_ru_t_mid_a_0.5`     | −0.715 | ↑ → besser |
| 4 | `cV_ru_offsetPhiR_ex_0.5`| −0.625 | ↑ → besser |
| 5 | `cV_ru_offsetM_ex_1.0`  | −0.624 | ↑ → besser |
| 6 | `cV_ru_bladeLength_0.5` | −0.575 | ↑ → besser |
| 7 | `cV_ru_u_mid_a_1`       | +0.555 | ↓ → besser |
| 8 | `cV_ru_t_le_a_0.5`     | −0.552 | ↑ → besser |
| 9 | `cV_ru_alpha_2_ex_0.0`  | −0.517 | ↑ → besser |
| 10| `cV_ru_ratio_1.0`       | +0.512 | ↓ → besser |

**Ohne Einfluss** (`|ρ| < 0.06`): `ratio_0.0`, `alpha_1_ex_0.0`, `alpha_1_ex_1.0`, `t_le_a_1`, `u_mid_a_0.5`.

**Interpretation:** die alpha₂-Profile (hintere Flanke) dominieren — stärker als die alpha₁ (vordere). Mittel-Spannweiten-Effekte (`*_0.5`-Labels) wiederum stärker als Wurzel- oder Spitzen-Schnitt. dtOO-Map2dTo3dFail-Anfälligkeit, v.a. bei extremen Vorderrücken-Offsets, erklärt warum 4 von 30 als zwar sensitiv, aber auch constraints bei Trials wahrnehmbar sind.

---

## Best (idx=6) vs. Worst valid (idx=7)

| Kennzahl | Best (idx=6) | Worst (idx=7) |
|---|---|---|
| Objective f | **4.903** | 11.879 |
| Frequencies (Hz) | 30.2, 100.1, 107.5, **118.7**, 140.6, 300.0, 327.8, 481.0, 487.6, 518.8 | 21.8, 94.4, **104.8**, 108.5, 117.1, 259.2, 324.0, 478.9, 485.1, 520.0 |
| f₁ (tiefste) | 30.2 Hz (weiter vom 1×f_bp) | 21.8 Hz (doppelt so nah am 1×f_bp) |
| Mode im verbotenem Band | M3 107.5 Hz (nur in [102.6, 113.4]) | M3 104.8 Hz + M4 108.5 Hz (beide in [102.6, 113.4]) |

- **Best Entwurf** hat nur eine Mode im verbotenem Band (um h=4 BPF: 108 Hz); Penalty = 4.9 nah an Bandkante.
- **Worst Entwurf** hat zwei Moden im selben Band + nahe Bandmitte → Penalty doppelt so hoch.
- Verbotenes Band 4.bpf: [102.6, 113.4] Hz.
- 3D-Vergleich: [`assets/geometry_best.html`](assets/geometry_best.html) · [`assets/geometry_worst.html`](assets/geometry_worst.html)

---

## Reproduzierbarkeit

- Checkpoint + History: `turbine_runner/de_state_resonance_only.json` · `turbine_runner/de_history_resonance_only.jsonl`
- Sensitivitätstabelle (alle 30 Parameter): [`sensitivity_analysis.md`](sensitivity_analysis.md)
- Resume per `sbatch cluster/submit_de_resonance_only.sh` (ohne `DE_FRESH=1`) → startet ab gen+1 = 13.

## Limitierungen

- Nur 12 Gen → Sensitivitätsanalyse aus nur 31 Population-Points (asymmetrisch initial getiltet), Spearman ist n=31 robust, aber nicht long-track.
- Best unverändert über 3 letzte Generationen → Plateau nach gen 10, könnte Konvergenztoleranz oder init-Spread zu klein.
- Resonanz-Struktur-Problem: nur 1 Mode im Band, Penalty sinkt nur langsam → alternative Penaltdichte (z. B. `mode='hard'` mit multiplier 1e6) könnte Schrumpfung erzwingen.
- OpenMP/MUMPS-Env-Transfer in `_run_fenicsx` (optimize.py:82-93) noch nicht gepatched → Modal-Solver läuft single-threaded → ~270 s/Gen lassen sich vermutlich >3× beschleunigen.