# Parametrisierung: 30 dtOO-Design-Variablen

**Runner-Geometrie:** dtOO (OpenCASCADE-basierte Parametrisierung) — pro Variable drei Spannweiten (Wurzel 0.0, Mid 0.5, Spitze 1.0) zur separaten Kontrolle der Schaufelentwicklung entlang der Spannweite.

## Parametergruppen (insgesamt 30)

| Gruppe | Variablen | bounds (min..max) | Init |
|---|---|---|---|
| **Alpha₁** (vordere Flanke: entry angle) | `cV_ru_alpha_1_ex_{0.0,0.5,1.0}` | −0.155..0.025 · −0.19..−0.01 · −0.19..−0.01 | 0.005 · −0.115 · −0.015 |
| **Alpha₂** (hintere Flanke: trailing angle) | `cV_ru_alpha_2_ex_{0.0,0.5,1.0}` | −0.08..0.1 · −0.08..0.1 · −0.08..0.07 | 0.034 · 0.039 · −0.068 |
| **OffsetM** (meridionaler Versatz) | `cV_ru_offsetM_ex_{0.0,0.5,1.0}` | 1.0..1.5 (alle 3) | 1.434 · 1.309 · 1.329 |
| **Ratio** (Verteilungs-Teilungsverhältnis) | `cV_ru_ratio_{0.0,0.5,1.0}` | 0.4..0.6 (alle 3) | 0.516 · 0.402 · 0.535 |
| **OffsetΦ_R** (azimutaler Rotationsversatz) | `cV_ru_offsetPhiR_ex_{0.0,0.5,1.0}` | −0.15..0.15 (alle 3) | 0.046 · −0.003 · 0.046 |
| **BladeLength** (Schaufellänge pro Spannweite) | `cV_ru_bladeLength_{0.0,0.5,1.0}` | 0.4..0.8 · 0.6..1.0 · 0.8..1.3 | 0.404 · 0.683 · 1.098 |
| **t_le_a** (Dicke an der Eintrittskante) | `cV_ru_t_le_a_{0,0.5,1}` | 0.005..0.06 (alle 3) | 0.043 · 0.060 · 0.027 |
| **t_mid_a** (Dicke Schaufelmitte) | `cV_ru_t_mid_a_{0,0.5,1}` | 0.005..0.06 (alle 3) | 0.015 · 0.029 · 0.048 |
| **t_te_a** (Dicke an der Austrittskante) | `cV_ru_t_te_a_{0,0.5,1}` | 0.005..0.06 (alle 3) | 0.016 · 0.019 · 0.009 |
| **u_mid_a** (Mittenumfangsposition) | `cV_ru_u_mid_a_{0,0.5,1}` | 0.4..0.6 (alle 3) | 0.428 · 0.412 · 0.467 |

## Geometrische Anordnung

```
        ┌─── Wurzel  (r = 0.0)
        │     Mid     (r = 0.5)  ← alpha_1, alpha_2, offsetM, ratio, offsetPhiR
        │     Spitze  (r = 1.0)
        ▼
        radialer Spannweiten-Abschnitt
        mit je 3 Kontroll-Spannwerten pro Variable
        ──→ Schaufel-blatt mit veränderlicher
              Dicke t_le / t_mid / t_te
              + Längen bladeLength (steigt von Wurzel→Spitze)
```

## Charakteristische Merkmale

- **10 Parametergruppen × 3 Spannweiten = 30 Freiheitsgrade** — kleine, handhabbare Dimensionalität.
- **Spannweiten-Effekte**: `*_0.5`-Labels sind meist am sensitivsten (Mitte-der-Schaufel-Kontur), vgl. Sensitivitätsanalyse (Top-10 dominiert von mid-Layern).
- **Alpha₂ (hintere Flanke)**Overall sensitiver als Alpha₁ — Trailing-Edge-Geometrie steuert die Modalformen stärker.
- **Dicken** (t_le/t_mid/t_te) sind gleich beschränkt (5 mm bis 60 mm), aber die Initial sind ungleich — Schaufel ist vorne dick, hinten dünn.
- **BladeLength** ist die einzige Variable mit ansteigenden Bounds (0.6 Spannweite → 0.8–1.3), weil die Schaufel zur Spitze länger wird.
- **OffsetΦ_R** mit ±0.15 relativ groß erlaubt deutliche azimutale Verschiebung.

## dtOO-Umsetzung

- **Konstanten-Werte** (`dtOO::constValue`): jeder der 30 Labels überschreibt einen `<constValue>`-Eintrag im XML-Case `/dtOO/test/tistos/machine.xml`.
- **dtOO-Backend:** `dtoo_export.py` liest `DTOO_DESIGN_JSON` → applyt `destroyAndCreate` → gmsh-Tetra-Volume-Mesh → `runner.msh`.
- **Container:** `atismer/dtoo-opensuse:stable` — Python3.12, OCC, gmsh.
- **Failures:** `map2dTo3d::reparamOnFace` wirft bei zu extremen Parameter-Kombinationen (1–4/32 pro Gen im combustion test).

## Verwendeter Init-Punkt

Die `*_0`-Variante ist Wurzel-position, `*_1` ist Spitze. Init-Werte sind zufällig (Teil einer vorgegebenen baseline `templateState.xml`). DE-Jitter `DE_INIT_SPREAD=0.05` per Default → init Pop = x0 + N(0, 0.05 × spanning)|clip(bounds).

## Beziehung zu Sensitivität

Siehe [`SENSITIVITY_slides.md`](SENSITIVITY_slides.md) — die Top-6 sensitiven Parameter sind alle aus den Gruppen Alpha₂, OffsetM, t_mid, offsetPhiR, bladeLength „Mid (0.5)". Die Schaufel-Mitte-Querschnitt bestimmt also maßgeblich die Modal-Resonanz.