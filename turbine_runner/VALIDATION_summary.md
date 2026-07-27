# Validierung: freie Schwingungsanalyse vs. Experiment

**Datum:** 2026-07-20 · **Status:** PASSED — alle gemessenen Moden innerhalb 5 %
**Pipeline:** `turbine_runner` (FEniCSx + SLEPc) vs. Schlagversuch an Bronze-Testscheibe (ANSYS-Referenz)

---

## Setup im Überblick

- **Material:** Bronze — E = 75.854 GPa, ρ = 8910 kg/m³, ν = 0.34
- **Randbedingung:** free-free (entspricht Experiment; 6 Starrkörpermoden verworfen)
- **Geometrie:** STL, 206.472 Dreiecke, wasserdicht · Scheibe d = 0,2 m, h = 87 mm, m ≈ 5,99 kg
- **Mesh:** 325.067 tet10, 654.958 P2-Knoten → **1.964.874 Vektor-Freiheitsgrade** (Elementgröße 0,006, Ordnung 2)
- **Solver:** SLEPc GHEP, shift-invert σ = −1, KSP preonly + LU/MUMPS, Rayleigh-Quotient-Verfeinerung
- **Container:** `eigenfrequencies-fenicsx:latest` (dolfinx 0.11, slepc4py 3.25.1)
- **Ressourcen:** Wand ≈ 3–5 min, Peak-RAM 28,6 GB (30-GB-Host)

## Warum P2 + SLEPc?

- Lineare tet4-Elemente übersteifen biegedominierte Nodaldurchmesser-(ND-)Moden.
- Mit identischer Geometrie/Material lag P1 (357.671 tets, 353k DOFs, scipy) **+14 bis +20 %** über dem Experiment.
- ANSYS (quadratische Elemente) trifft — also ist die Diskretisierung der einzige Hebel.
- Quadratische tets → ~2 Mio. DOFs → jenseits von scipy's dichter Faktorisierung → SLEPc + MUMPS.

---

## Ergebnisse (P2, tet10)

- 6 Starrkörpermoden entfernt (3,5e-4 … 9,1e-4 Hz).
- 12 elastische Moden: 192,39 · 192,51 · 223,73 · 290,12 · 290,20 · 693,92 · 693,93 · 1291,48 · 1291,52 · 1368,12 · 1368,70 · 1518,29 Hz.
- ND-Moden = entartete sin/cos-Paare (Rotationssymmetrie); Torsion = Singulet.
- Paaraufspaltung < 0,1 Hz bestätigt erhaltene Symmetrie.

### 3-Wege-Vergleich: FEniCSx vs. Experiment vs. ANSYS

Fehler vorzeichenbehaftet `(Berechnet − Referenz) / Referenz`.
`Δexp` = vs Experiment, `ΔANSYS-tbl` = vs ANSYS-Tabelle (Body-Text des .docx),
`ΔANSYS-rep` = vs ANSYS-Report (eingebettetes Bild, 20 Moden).

| Mode      | Berechnet P2 (Hz) | Experiment (Hz) | Δexp     | ANSYS Tabelle (Hz) | ΔANSYS-tbl | ANSYS Report (Hz) | ΔANSYS-rep |
|-----------|------------------:|----------------:|---------:|-------------------:|-----------:|-------------------:|-----------:|
| 1ND       |   192,39 / 192,51 |          192,80 | **−0,18 %** |          191,600  |   **+0,44 %** |          196,050 |   **−1,84 %** |
| Torsion   |   223,73 (Singulet) | nicht gemessen |     —      |          226,000  |   **−1,01 %** |          229,110 |   **−2,35 %** |
| 2ND       |   290,12 / 290,20  |         299,125 | **−3,00 %** |          293,625  |   **−1,18 %** |          291,580 |   **−0,49 %** |
| 3ND       |   693,92 / 693,93  |          712,0 | **−2,54 %** |          703,250  |   **−1,33 %** |          694,470 |   **−0,08 %** |
| 4ND       |  1291,48 / 1291,52 |          1320,0| **−2,16 %** |         1310,875  |   **−1,48 %** |         1291,500 |   **−0,00 %** |

Lesart: FEniCSx liegt auf jeder gemessenen Mode innerhalb ~3 % des Experiments
(Δexp), innerhalb ~1,5 % der ANSYS-Tabelle und innerhalb ~2,4 % des
ANSYS-Reports — letzteres über *alle* Moden inkl. der ungemessenen Torsion.

### Höhere Moden (Kreuzcheck vs. ANSYS-Report, kein Experiment)

| Berechnet (Hz)     | ANSYS-Report-Mode  | ANSYS (Hz)       | Abweichung |
|--------------------|--------------------|------------------|------------|
| 1368,12 / 1368,70  | Couronne_2ND      | 1371,2 / 1371,6  | −0,22 %    |
| 1518,29            | CompressionAxiale  | 1521,1           | −0,18 %    |

---

## P1 vs. P2 (gleiche Geometrie, gleiches Material)

| Mode    | P1 tet4 (Hz) | P1 Fehler  | P2 tet10 (Hz) | P2 Fehler  |
|---------|--------------|------------|---------------|------------|
| 1ND     | 231,26       | +19,95 %   | 192,45        | −0,18 %    |
| Torsion | 266,90       | +18,10 %*  | 223,73        | −0,99 %*   |
| 2ND     | 356,43       | +19,16 %   | 290,16        | −3,00 %    |
| 3ND     | 854,82       | +20,06 %   | 693,92        | −2,54 %    |
| 4ND     | 1510,50      | +14,43 %   | 1291,50       | −2,16 %    |

* Torsion nicht gemessen; verglichen gegen ANSYS-Tabellenwert 226,0 Hz.

- Systematische positive P1-Abweichung = klassische tet4-Biegeübersteifung (nur 2–4 lineare Elemente über dünne Features).
- P2 beseitigt das; verbleibender negativer Bias (−2 bis −3 %) konsistent mit konvergiert-von-oben-Diskretisierung plus modesten Massenidealierungs-Unterschieden zum физischen Bauteil.

---

## Reproduzierbarkeit & Tests

- **Mesh:** `stl_to_msh.py` (TESTCASE_ORDER=2, TESTCASE_ELEMENT_SIZE=0.006) → `data/testcase_volume.msh`
- **Validierung:** `python3 validate_testcase.py` (im fenicsx-Container)
- **Repo-Test (opt-in, schwer):** `RUN_TESTCASE_VALIDATION=1 python3 -m pytest test_testcase_validation.py`
  - Prüft: 6 Starrkörpermoden, ≥ 9 elastische Moden, jede gemessene Mode ≤ 5 % Fehler.
- **Solver-Unit-Tests (schnell):** `python3 -m pytest test_free_mode.py`

## Artefakte

- `output/testcase/testcase_frequencies.json` — alle Frequenzen + Vergleichsdict
- `output/testcase/modes.xdmf` / `modes.h5` — 12 elastische Mode-Shapes (ParaView)
- `output/testcase/modes.pvd`, `geometry.pvd`

## Limitierungen

- Torsion experimentell nicht gemessen — nur gegen ANSYS validiert (beide ~1–2 % von 223,73 Hz entfernt).
- Mode-Labels werden positional zugeordnet (erwartete Entartungsfolge); andere Geometrie erfordert Mode-Shape-Inspektion.
- Peak-RAM 28,6 GB lässt auf 30-GB-Host wenig Spielraum → CG+GAMG-Fallback (langsamer) greift automatisch, falls MUMPS-Vorkonditionierung scheitert.