# Combi-Optimizer-Lauf: 100 Generationen Differential Evolution

**Ziel:** dtOO → CFD (simpleFoam) + Modal (FEniCSx) kombiniert optimieren
**Setup:** Pop 16 · 30 Design-Parameter · 100 Gen · ~9,8 h Wallclock (35314 s, ~345 s/Gen)
**Status:** CFD-Pfad mehrheitlich fehlgeschlagen → nur **Modal-/Resonanz-Optimierung** wirkungsvoll gelaufen

---

## Was gelaufen ist

- **Algorithmus:** Differential Evolution (pop 16, mutation 0.8, crossover 0.9, max 100 Gen)
- **Design-Variablen:** 30 dtOO-Runner-Parameter
  - `alpha_1/2` (3 Spannweiten je), `offsetM`, `ratio`, `offsetPhiR`, `bladeLength`, `t_le/t_mid/t_te`, `u_mid`
- **Skalarzielfunktion (minimiert):**
  `f = w_eta·tanh(η-term) + w_cav·tanh(V_cav·1e6) + w_head·tanh(dH-term) + w_resonance·resonance_penalty`
- **Verbotband:** um Blattdurchgangsfrequenz f_bp = Z·n/60 = 18·n_rpm/60 und Harmonische 1–6 · ±5 Hz oder ±5 % Halbwertsbreite
- **Ressourcen:** 16 Cluster-Worker (`server_logs/combined/worker_*.log`), PyRO dispatch, dtOO-Container `atismer/dtoo-opensuse:stable`, FEniCSx-Container `eigenfrequencies-fenicsx:latest`

---

## CFD / Geometriebau – Failures

| Fehlerquelle | Count | Ursache |
|---|---|---|
| `dtOO build FAILED` (geometrischer Bau) | 39 | `Exception: map2dTo3d::reparamOnFace()` — `!md.converged()` in `map2dTo3d.cpp:250` (dtGmshFace kann Surface nicht reparametrisieren) |
| `CFD solve FAILED` (simpleFoam) | 29 (nur worker 8) | nach `CreateMeshes` abgebrochen |
| `CreateStates FAILED` | 2 | Folgefehler aus geometrischer Bau-Exception |
| `CFD build FAILED` | 2 | s. o. |

- CFD-Zielanteil gefriert deshalb auf **f_cfd = 2.336** (η=0.821, V_cav=0.00139, dH=−1.992) – defensive Ersatzstrafe: jeder Candidate bekommt denselben CFD-Anteil, sobald die OF-Eval scheitert.
- **Konsequenz:** Zielfunktionsbewegung während des gesamten Laufs kam praktisch nur aus `f_resonance`.

---

## Konvergenz (best & mean pro Generation)

| Gen | Best f | Mean f | f_resonance | f_cfd | η | V_cav | dH | ok/n |
|------:|------:|------:|------:|------:|------:|------:|------:|------:|
| 0    | 8.477 | 9.313 | 6.005 | 2.471 | 0.924 | 0.00183 | −1.833 | 16/16 |
| 10   | 5.108 | 5.549 | 2.615 | 2.494 | 0.922 | 0.00189 | −1.802 | 16/16 |
| 20   | 4.772 | 5.227 | 2.436 | 2.336 | 0.821 | 0.00139 | −1.992 | 16/16 |
| 40   | 4.473 | 4.876 | 2.137 | 2.336 | 0.821 | 0.00139 | −1.992 | 16/16 |
| 50   | 4.399 | 4.771 | 2.063 | 2.336 | 0.821 | 0.00139 | −1.992 | 16/16 |
| 75   | 4.212 | 4.484 | 1.741 | 2.471 | 0.924 | 0.00183 | −1.833 | 16/16 |
| 100  | **3.872** | 4.144 | **1.536** | 2.336 | 0.821 | 0.00139 | −1.992 | 16/16 |

- **Gesamtverbesserung:** best 8.477 → 3.872 (−54 %, Δ = 4.60)
- **Resonanzanteil allein:** 6.005 → 1.536 (−74 %) → **der eigentliche Optimierungserfolg**
- **CFD-Anteil fix ab Gen 20:** surrogate eingefroren, keine echte CFD-Optimierung mehr
- 16/16 ok in jeder Generation bedeutet nur, dass der Worker ein Ergebnis (auch Fallback) zurückgab — nicht, dass CFD wirklich durchlief.

---

## Bester Entwurf (selected Parameter)

- `alpha_1_ex_0.5/1.0` = −0.01 (untere Schranke)
- `alpha_2_ex_0.0/0.5` = +0.10 (obere Schranke), `alpha_2_ex_1.0` = −0.08 (untere Schranke)
- `bladeLength_0.0/0.5/1.0` = 0.80 / 1.00 / **1.293** → Spannweite tendiert nach oben
- `t_mid_a_0.5` = 0.052 (verjüngt), `t_te_a_0` = **0.00754** (dünne Hinterkante an der Wurzel)
- `ratio_1.0` = 0.566 (größte Auslegung), `offsetPhiR_ex_0.0` = +0.00286, restliche offsetPhiR an Schranken ±0.15
- `u_mid` = 0.40 an allen Spannweiten (untere Schranke)

> 30/30 Parameter `→ best_design.json`. Viele Variablen kleben an den Schranken → DE hat Konvergenzzone noch nicht erreicht.

---

## Offene Resonanzverletzung — bester Entwurf

> **`resonance`: VIOLATION: mode 3 = 105.7 Hz**

- Bester Entwurf liegt mit einer Mode im verbotenem Band (um f_bp oder Harmonische).
- CFD wurde nie wiederhergestellt, also konnte der kombinierte Zielfunktionsanteil nicht absteigen.
- Für einen vollständigen Lauf nötig: dtOO `map2dTo3d`-Konvergenz beheben (Design-Space-Einschränkung oder Scaffolding-XML prüfen) **und** simpleFoam-Löser-Settings / Anfangsbedingungen stabilisieren.

---

## Limitierungen & Reproduktion

- **Nur Modal wirklich optimiert** — CFD-Zielanteil surrogate-konstant → keine Aussage über η/V_cav/dH im Optimum möglich.
- **Begrenzte Konvergenz:** Viele Parameter an Schranken → weder DE-Konvergenztoleranz (1e-2) noch `f_resonance = 0` wurde erreicht.
- **Vor einem Combi-Lauf zwingend:** intakter CFD-Pfad; empfohlene inkrementelle Strategie — erst `resonance_only` stabil, dann `combined` sobald OF durchläuft.
- **Reproduktion:** `de_state_combined.json` (gen 100, Population, RNG-State) + `de_history_combined.jsonl` (101-Einträge Verlauf) in `turbine_runner/`; Worker-Logs in `server_logs/combined/`.

**Artifacts**
- `turbine_runner/de_state_combined.json` (Population 16 × 30, best_vec, best_obj=3.872)
- `turbine_runner/de_history_combined.jsonl` (101-Genverlauf)
- `turbine_runner/best_design.json` (beste Parameterkonfiguration)
- `server_logs/combined/worker_*.log` (Worker-Fehlerverfolgung)