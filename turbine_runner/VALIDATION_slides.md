# Validierung: freie Schwingungsanalyse vs. Experiment

**2026-07-20 · Status PASSED** — alle gemessenen Moden innerhalb 5 %
Pipeline: `turbine_runner` (FEniCSx + SLEPc) vs. Schlagversuch an Bronze-Testscheibe

---

## Setup

- **Material:** Bronze — E = 75.854 GPa, ρ = 8910 kg/m³, ν = 0.34
- **Randbedingung:** free-free (entspricht Experiment); 6 Starrkörpermoden verworfen
- **Geometrie:** STL, 206.472 Dreiecke, wasserdicht · Scheibe d = 0,2 m, h = 87 mm · m ≈ 5,99 kg
- **Mesh:** 325.067 tet10, 654.958 P2-Knoten → **1.964.874 Vektor-DOFs** (Elementgröße 0,006, Ordnung 2)
- **Solver:** SLEPc GHEP, shift-invert σ = −1, LU/MUMPS, Rayleigh-Quotient-Verfeinerung
- **Container:** `eigenfrequencies-fenicsx:latest` (dolfinx 0.11, slepc4py 3.25.1)
- **Ressourcen:** Wand ≈ 3–5 min · Peak-RAM 28,6 GB (30-GB-Host)

---

## Warum P2 + SLEPc?

- Lineare tet4-Elemente übersteifen biegedominierte ND-Moden.
- P1 (identische Geometrie/Material) lag **+14 bis +20 %** über dem Experiment.
- ANSYS (quadratisch) trifft → Diskretisierung ist der einzige Hebel.
- Quadratische tets → ~2 Mio. DOFs → jenseits scipy's dichter Faktorisierung → SLEPc + MUMPS.

---

## Ergebnisse — 3-Wege-Vergleich

| Mode    | Berechnet P2 (Hz) | Experiment (Hz) | Δexp     | ANSYS Tab. (Hz) | ΔANSYS-tbl | ANSYS Rep. (Hz) | ΔANSYS-rep |
|---------|------------------:|----------------:|---------:|----------------:|-----------:|----------------:|-----------:|
| 1ND     | 192,39 / 192,51   | 192,8           | **−0,18 %** | 191,6       |   **+0,44 %** | 196,05      |   **−1,84 %** |
| Torsion | 223,73 (Singulet) | nicht gem.      |     —      | 226,0       |   **−1,01 %** | 229,11      |   **−2,35 %** |
| 2ND     | 290,12 / 290,20   | 299,125         | **−3,00 %** | 293,625     |   **−1,18 %** | 291,58      |   **−0,49 %** |
| 3ND     | 693,92 / 693,93   | 712,0           | **−2,54 %** | 703,25      |   **−1,33 %** | 694,47      |   **−0,08 %** |
| 4ND     | 1291,48 / 1291,52 | 1320,0          | **−2,16 %** | 1310,875    |   **−1,48 %** | 1291,50     |   **−0,00 %** |

- ND-Moden = entartete sin/cos-Paare · Torsion = Singulet
- Paaraufspaltung < 0,1 Hz → erhaltene Rotationssymmetrie
- Alle Δexp ≤ 3 % · alle ΔANSYS-tbl ≤ 1,5 % · alle ΔANSYS-rep ≤ 2,4 %

---

## Ergebnisse — höhere Moden (nur vs. ANSYS-Report)

| Berechnet (Hz)     | ANSYS-Report-Mode  | ANSYS (Hz)       | Abweichung |
|--------------------|--------------------|------------------|------------|
| 1368,12 / 1368,70  | Couronne_2ND      | 1371,2 / 1371,6  | −0,22 %    |
| 1518,29            | CompressionAxiale  | 1521,1           | −0,18 %    |

---

## P1 vs. P2 (gleiche Geometrie/Material)

| Mode    | P1 tet4 (Hz) | P1 Fehler  | P2 tet10 (Hz) | P2 Fehler  |
|---------|--------------|------------|---------------|------------|
| 1ND     | 231,26       | +19,95 %   | 192,45        | −0,18 %    |
| Torsion | 266,90       | +18,10 %*  | 223,73        | −0,99 %*   |
| 2ND     | 356,43       | +19,16 %   | 290,16        | −3,00 %    |
| 3ND     | 854,82       | +20,06 %   | 693,92        | −2,54 %    |
| 4ND     | 1510,50      | +14,43 %   | 1291,50       | −2,16 %    |

*Torsion nicht gemessen — verglichen gegen ANSYS-Tabellenwert 226,0 Hz.

- P1-Bias = klassische tet4-Biegeübersteifung (nur 2–4 lineare Elemente über dünne Features)
- P2 beseitigt es; verbleibender negativer Bias (−2 bis −3 %) = Diskretisierungskonvergenz + Massenidealierung

---

## Reproduzierbarkeit

- **Mesh:** `stl_to_msh.py` (TESTCASE_ORDER=2, TESTCASE_ELEMENT_SIZE=0.006)
- **Validierung:** `python3 validate_testcase.py` (im fenicsx-Container)
- **Tests:** `RUN_TESTCASE_VALIDATION=1 pytest test_testcase_validation.py` (opt-in, schwer)
  - prüft: 6 Starrkörpermoden, ≥ 9 elastische Moden, jede gemessene Mode ≤ 5 % Fehler
- **Unit-Tests:** `pytest test_free_mode.py` (beide Backends, free BC)

**Artefakte:** `testcase_frequencies.json`, `modes.xdmf`/`modes.h5` (12 elastische Mode-Shapes, ParaView)

---

## Limitierungen

- Torsion experimentell nicht gemessen — nur gegen ANSYS validiert.
- Mode-Labels positional zugeordnet; andere Geometrie erfordert Mode-Shape-Inspektion.
- Peak-RAM 28,6 GB → wenig Spielraum auf 30-GB-Host → CG+GAMG-Fallback greift automatisch bei MUMPS-Versagen.