# dtOO/enroot auf bwUniCluster 3.0 — Befund v2

**Stand:** 2026-09-03, HEAD `1a2b75a` (feat(cluster): stable path for the second window)
**Zweck:** Vollständige, korrigierte Befundlage als Basis für einen Fix-Plan. Löst `docs/cluster-dtoo-enroot-befund.md` (v1) ab, wo v1 veraltet ist — v1 bleibt als Messdaten-Archiv stehen (Abschnitt 5 nennt die Korrekturen).

---

## 1. Constraints: Third-party-Grenzen

Folgendes wird **nie** geändert (alle nachfolgenden Fixes landen daher in `cluster/*` und `cluster/configs/*`):

| Komponente | Warum | Konsequenz für Fixes |
|---|---|---|
| dtOO-Container (`atismer/dtoo-opensuse`) | Third party | Keine Änderungen am Image, an `/dtOO`-Pfaden oder in Container-Scripts. Kein `mpiexec` nachrüstbar, kein `OMPI_ALLOW_RUN_AS_ROOT` ins Image baken → muss über Config-Umgebung laufen. |
| `hydroflow-opt` (`github.com/thomasisensee/hydroflow-opt`, venv-Dependency, pyproject: `hydroflow = ["hydroflow-opt"]`) | Third party | Optimizer-Paket unangetastet. Dieses Repo liefert nur Case-Plugins via Entry-Points `hydroflow_opt.cases`. |
| `turbine_runner/` (aus dtOO übernommen) | Third party (vendored) | Unangetastet. Insbesondere `turbine_runner/cfd/tistos_files/sbatch.tistos_ru_of.sh` mit Default `${MPI_LAUNCHER:-mpiexec}` bleibt so — Umstellung nur über `MPI_LAUNCHER`-Env. |

**Eigener, editierbarer Code:** `cluster/*` (Submit-Scripts, Configs, Env) und `src/eigenfrequencies/hydroflow/*` (Case-Plugin: `case.py`, `physics.py`).

---

## 2. Evidenzlage und ihre Grenzen

**Wichtig:** Alle `*.out`-Logs im Repo-Root haben als mtime den **Kopierzeitpunkt ins Repo** (Schübe am 30.08.2026: 21:03, 21:08, 21:38, 22:22), nicht die Laufzeit der Jobs. Reihenfolge nur über SLURM-Job-IDs.

Alle Logs stammen vom 30.08.2026 21:03–22:22. Danach folgten bis 01.09. ca. 15 Fix-Commits — **Log-Befunde sind deshalb nur historisch** und dürfen nicht 1:1 als aktuelle Bugs gelesen werden.

Log-Generationen (chronologisch nach Job-ID):

| Generation | Job-IDs | Symptom | Code-Stand damals |
|---|---|---|---|
| A (instant fail) | 6743778, 6743794, 6743806 | „run complete 0/2" nach 15 s wall (Gen-A-1), bzw. ~15 min CPU mit 0/2 (6743806) | vor `6e0d629` |
| B (staging tot) | 6743849, 6743874, 6743902–04 | 9–27 min im Image-Staging (5,4–8 GB ≈ 5–10 MB/s auf Lustre), 6743902–04 gleichzeitig gecancelt | alte Version mit `.sqsh`-Kopie nach `$TMPDIR/enroot-images` (`714fdcf`) |
| C (run dir) | 6743938–940 | „optimization run directory is not empty" | Scratch lag im Run-Dir; 1 Minute später von `6e0d629` gefixt |
| Smokes | 6743814, 6743828, 6743829 | hostname/`WM_PROJECT_SITE` unbound; 5-min-Timeout; dolfinx-Image „NOT FOUND" | vor `f436da2`/`decd004` |

Die **wirklichen pro-Kandidat-Fehler** der Generation A liegen unverlesen in `results.jsonl` im Run-Verzeichnis auf dem Cluster (`$WS/runs/tistos-smoke/` bzw. gemäß config `run.directory`). Das ist die wichtigste noch fehlende Evidenz — zuerst dort nachsehen, bevor irgendwas gefixt wird.

---

## 3. Bereits behoben (Git-History) — nicht doppelt fixen

| Bug | Fix | Commit |
|---|---|---|
| „optimization run directory is not empty" (Scratch im Run-Dir) | Scratch alsSibling-Dir `$ABS_RUN_DIR-scratch`, `submit_hydroflow_opt.sh:174` | `6e0d629` (30.08. 22:23) |
| 64 CPUs in Config vs 40 allocated | Resource-Scaling aufs Partition-Angebot (`SCALE_RESOURCES=1`) | `49fb6d8`, `07f8dd8`, `69b7649`, `683c1ea` (22:31–22:35) |
| lzo-Squashfs, auf Compute-Node unlesbar | `ENROOT_SQUASH_OPTIONS="-comp zstd -noD"` in `cluster_env.sh:50` | `0da15fa` (21:09) |
| `WM_PROJECT_SITE: unbound variable` im Smoke (set -u im Container) | set -u aus Smoke-Scripts entfernt | `f436da2` (21:27) |
| **squashfuse-Langsamkeit (Hauptthese von v1)** | Images werden per `enroot create` einmal pro Job **unpackt** statt per squashfuse gemountet | `f76df43` (31.08. 14:13) |
| `~/`- und `$VAR`-Pfade erreichen execve unexpandiert | Expansion in `physics.py` | `e6bcd04`, `decd004` |
| dtOO-Payload lief doppelt | `exec` des Payloads | `fae9a3d` (01.09.) |
| Image-Name vs. Pfad Verwirrung | Configs nennen Container-NAME, Submit-Script unpackt nach Name | `b17d58a`, `decd004` |

---

## 4. Offene Punkte bei HEAD (verifiziert am 03.09.2026, `1a2b75a`)

### P0-1: `tistos-cfd-only.toml` — MPI-Launcher und OpenMPI-as-root fehlen

**Blockiert den geplanten ersten cfd_only-Lauf.**

- Der CFD-Solve läuft mit `sh -e` und Default `${MPI_LAUNCHER:-mpiexec}` (`turbine_runner/cfd/tistos_files/sbatch.tistos_ru_of.sh`); im dtOO-Container existiert nur `mpirun` (openmpi4). Ohne `MPI_LAUNCHER=mpirun` → instant fail.
- Der Container läuft als root (enroot kann keine Privilegien ablegen, siehe Kommentar `physics.py:269ff`); OpenMPI verweigert root-Ausführung ohne `OMPI_ALLOW_RUN_AS_ROOT=1` und `OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1`.
- Der Mechanismus existiert bereits: `src/eigenfrequencies/hydroflow/physics.py:957–967` liest `cfd_opts["mpi_launcher"]` → `MPI_LAUNCHER` und passt freies `env`-Mapping 1:1 durch. **Nur die Config nutzt es nicht.**

**Fix (nur Config, kein Code):** in `cluster/configs/tistos-cfd-only.toml` unter `[case.options.cfd]`:

```toml
mpi_launcher = "mpirun"
env = { OMPI_ALLOW_RUN_AS_ROOT = "1", OMPI_ALLOW_RUN_AS_ROOT_CONFIRM = "1" }
```

### P0-2: Image-Benennung `dtOO.sqsh` — Name-Mismatch bleibt still

- `submit_hydroflow_opt.sh:197–204` macht `enroot create --name "$(basename "$img" .sqsh)"` aus `$ENROOT_IMAGES/*.sqsh`. Die Config will `container = "dtOO"`.
- Import-Doku (`cluster/enroot_dtoo_import.md`) erzeugt aber `dtOO-opensuse.sqsh` → Container hieße `dtOO-opensuse` → `enroot start dtOO` in `physics.py` findet nichts (Name-basiert, kein `.sqsh`-Fallback). Stiller Fail erst beim ersten Kandidaten, kryptische Fehlermeldung.
- Auf dem Cluster verifizieren: `ls $WS/enroot-images/` — heißt die Datei `dtOO.sqsh`? Falls nicht: umbenennen oder Import-Doku anpassen (eigene Datei, kein Third-party-Konflikt).

### P0-3: dtOO-Build/Mesh überschreitet sein 1800-s-Timeout — der eigentliche Blocker

**Nachgetragen am 2026-09-04.** Dieser Punkt fehlte in v2, obwohl `cluster/diagnose_cfd_build.sh` (12 Commits, letzter = HEAD `1a2b75a`) unmittelbar vor dem Schreiben dieses Dokuments die aktive Arbeitslinie war. Die Fix-Planung lief deshalb an ihm vorbei.

- **Messung 2026-09-04:** `cluster/configs/tistos-smoke-cfd.toml` interaktiv auf uc2n601, Allocation 128 Kerne, 2 Kandidaten nebenläufig mit je 6 Ranks, 19:08–19:25:50. Ergebnis nach 17 Minuten: beide Kandidatenverzeichnisse enthalten ausschließlich `request.json` (Zeitstempel 19:08), kein `results.jsonl`, kein Artefakt. Beide Evaluationen hingen die volle Zeit in der dtOO-Phase.
- **Referenz de_framework:** derselbe tistos-Fall (3D, 30 Parameter) läuft dort Mesh **und** Solve für mehrere Individuen gleichzeitig innerhalb eines 30-Minuten-Fensters auf `dev_cpu_il` (Angabe Tobias Rentschler, 2026-09-04). Dimensionierung: 2 Kerne pro CFD, viele CFDs nebeneinander — `hydroFoil_bwRSE4HPC/start.sh` (`--ntasks-per-node=32`, `--cpus-per-task=2`, `--time=00:25:00`), `hydroFoil.py:1045` setzt `numberOfSubdomains = cpus_per_task`.
- Der frühere Vergleichswert „~15 min auf einem Kern, `start_de.py: cores_per_cfd = 1`" im Kopf des Diagnose-Scripts war falsch zugeordnet: jene Datei instanziiert `hydroFoil_problem()`, den 2D-Vorläufer mit 3 Parametern. Korrigiert am 2026-09-04.
- **Mehr MPI-Ranks helfen nicht.** Die dtOO-Phase (`CreateStates`/`CreateMeshes`) ist einfädiges gmsh; die Rankzahl wirkt erst im simpleFoam-Solve dahinter.
- **Konsequenz für die Produktion:** der `dtoo`-Timeout in allen drei Produktions-Configs steht auf 1800 s. Ungebremst eingereicht wären alle 3120 Evaluationen dort hineingelaufen — 48 h Rechenzeit nach 5–7 Tagen Queue, ohne ein einziges verwertbares Ergebnis. Der Smoke-Gate vor der Produktion hat genau das abgefangen.

**Nächster Schritt:** `cluster/diagnose_cfd_build.sh` in einer Allocation laufen lassen. Es zerlegt den Build in Phasen mit Zeitstempeln (`env ready`, `state written`, `CreateStates done`, `CreateMeshes done`) und sagt damit, welche Phase die Zeit frisst. Erst danach lohnt jede weitere Fix-Diskussion.

### P1-1: Glob-Miss im Staging bleibt still

- `submit_hydroflow_opt.sh:197–198`: matcht `$ENROOT_IMAGES/*.sqsh` nichts (leeres/falsches Verzeichnis), überspringt `[[ -f "$img" ]] || continue` die Literal-Glob-Zeile lautlos — es entsteht **kein** Container, kein Fehler. Erster `enroot start` failt dann kryptisch.
- `enroot create`-Fehler selbst failt inzwischen laut (Zeile 201–202). Nur der Glob-Miss nicht.

**Fix-Skizze:** nach der Schleife prüfen `compgen -G "$ENROOT_IMAGES/*.sqsh"` bzw. Zähler; wenn 0 → `echo "no .sqsh in $ENROOT_IMAGES" >&2; exit 1`.

### P1-2: Per-Job-Unpack liest das `.sqsh` von Lustre

- Seit `f76df43` macht jedes Job `enroot create` direkt aus `$WS/enroot-images/*.sqsh` (Lustre) nach `$TMPDIR/enroot-data` (lokal). Gemessene Lustre-Rate aus Gen B: 5–10 MB/s → 8 GB ≈ 14–27 min **pro Job**.
- Der Kommentar im Submit-Script („costs … a couple of minutes") widerspricht der eigenen Messung.
- Alternative (Abwägung, nicht zwingend): einmaliges `enroot create` nach `$WS/enroot-data` (unpacked auf Lustre liest schnell — v1-Messung: CreateStates 8 s unpacked vs. >20 min via squashfuse) + `export ENROOT_DATA_PATH="$WS/enroot-data"` im Submit-Script → kein Per-Job-Unpack. Trade-off: ~7 GB Workspace-Quota × 2 Images. Zuerst messen, wie lange `enroot create` von Lustre real dauert (Gen-B-Zahlen gelten für die alte Kopiervariante, nicht 1:1 für `enroot create`).

### P1-3: dolfinx-Container auf Cluster verifizieren

- Der fenicsx-Smoke-Log „dolfinx.sqsh NOT FOUND" ist **stale**: Seit `decd004` (30.08. 02:06) wird das Stock-Image `dolfinx/dolfinx:stable` direkt vom Docker Hub importiert (kein eigenes Build), gmsh kommt per `pip install --target ~/pylibs` (Config: `pythonpath = ["$HOME/pylibs"]`).
- Unklar/lokal nicht prüfbar: Wurde der Import auf dem Cluster schon gemacht (`enroot list` bzw. `$WS/enroot-images/`)? Existiert `~/pylibs` mit gmsh auf dem Login-Node?

### P2-1: `set -euo pipefail` frisst die Exit-Code-Ausgabe

- `submit_hydroflow_opt.sh:235–237`: Bei Fail von `hydroflow-opt` beendet `set -e` das Script vor `EXIT_CODE=$?` — der Echo „hydroflow-opt exit code: N" erscheint nie. Kosmetisch, aber verhindert sauberes Post-Mortem im `.out`.

**Fix-Skizze:** `EXIT_CODE=0; "$VENV/bin/hydroflow-opt" "$CFG_MODE" "$RUN_CONFIG" || EXIT_CODE=$?` (beide Zweige, optimize/resume), dann Echo, dann `exit $EXIT_CODE`.

### P2-2: Diagnostik auf dem Cluster (kein Code-Fix, aber Plan-Voraussetzung)

1. `results.jsonl` im Run-Dir lesen — echte Gen-A-Fehlertexte.
2. `ls -la $WS/enroot-images/` — Image-Namen (P0-2) und dolfinx (P1-3).
3. `enroot list` + `enroot create`-Dauer einmal stoppen (P1-2-Entscheidungsgrundlage).

### P2-3: v1-Doku retiren

- `docs/cluster-dtoo-enroot-befund.md` ist in der Hauptthese (squashfuse) überholt (`f76df43`). Kennzeichnen oder Referenz auf dieses Dokument ergänzen.

---

## 5. Korrekturen gegenüber v1

| v1-Aussage | Korrektur |
|---|---|
| „squashfuse ist der Flaschenhals" (Hauptthese) | Seit `f76df43` wird unpackt; verbleibender Kostenpunkt ist der Lustre-Read pro Job (P1-2), nicht squashfuse. |
| „dolfinx.sqsh fehlt auf dem Cluster → freq-only/combined failen" | Ansatz geändert (`decd004`): Stock-Import vom Docker Hub ohne eigene Datei. Verifikation auf Cluster offen (P1-3). |
| „run directory is not empty" als offene Ursache unbekannt | Wurzel war Scratch im Run-Dir; gefixt `6e0d629` (und im Kommentar `submit_hydroflow_opt.sh:166–174` dokumentiert). |
| Gen-B-Cancels als „squashfuse langsam" | Eigentlich: 5–10 MB/s Lustre-Kopier-/Lese-Rate; Zahlen bleiben als Messgrundlage für P1-2 wertvoll. |
| hostname/`WM_PROJECT_SITE`-Fehler als Produktionsrisiko | Nur Smoke-Pfad betroffen (set -u im Smoke-Script, `f436da2`); Produktionspfad (`physics.py`) hat kein set -u. |

---

## 6. Vorgeschlagene Reihenfolge für den Fix-Plan

**Stand 2026-09-04:** Die Schritte 1–3 sind erledigt (Branch `fix/bwuni-enroot-hardening`); P0-2, P1-1, P1-2, P1-3 und P2-1 bis P2-3 sind abgeräumt oder durch Messung entschieden. Die Reihenfolge unten wird deshalb von **P0-3** angeführt: solange der dtOO-Build sein Timeout reißt, ist jeder Produktionslauf sinnlos, und alle übrigen Punkte sind bereits gelöst.

0. **P0-3 diagnostizieren** — `cluster/diagnose_cfd_build.sh`, Phasenzeiten für den dtOO-Build. Blockiert alles Weitere.
1. **Cluster-Diagnostik ohne Code-Änderung** (P2-2): `results.jsonl`, Image-Namen, dolfinx-Import, `enroot create`-Dauer. — Entscheidet über P0-2, P1-2, P1-3. *(erledigt 2026-09-04: Images korrekt benannt, `enroot create` = 8 s)*
2. **Config-Fix cfd-only** (P0-1): `mpi_launcher` + OMPI-Env. Klein, blockierend für den ersten Produktionslauf.
3. **Submit-Script-Härtung** (P1-1, P2-1, ggf. P0-2 als Namens-Check im Script: gewünschter Container-Name gegen vorhandene `.sqsh`-Namen matchen und laut failen).
4. **Staging-Entscheidung** (P1-2) erst nach Messung.
5. Danach: Smoke neu (`tistos-smoke.toml`), dann erster cfd_only-Lauf.

## 7. Anhang: Schlüssel-Referenzen

- `cluster/submit_hydroflow_opt.sh` — 27 (`set -euo pipefail`), 166–174 (Run-Dir/Scratch-Sibling + Begründung), 183–206 (Staging/Unpack, Kommentar mit „a couple of minutes"), 226–235 (resume/optimize, `EXIT_CODE=$?`), 237 (Sanity-Gate-Hinweis).
- `src/eigenfrequencies/hydroflow/physics.py` — 263–277 (`enroot start` name-basiert, Root-Begründung), 950–979 (CFD-Stage: `MPI_LAUNCHER`, `env`-Passthrough, `sh -e`).
- `cluster/cluster_env.sh` — 43–44 (`ENROOT_TEMP_PATH` lokal), 49–50 (zstd).
- `cluster/configs/tistos-cfd-only.toml` — `[case.options.cfd]` ohne `mpi_launcher`/`env`; `[case.options.dtoo]` `container = "dtOO"`.
- `cluster/configs/tistos-smoke.toml` — dolfinx Stock-Image + `pythonpath = ["$HOME/pylibs"]`.
- `turbine_runner/cfd/tistos_files/sbatch.tistos_ru_of.sh` — `${MPI_LAUNCHER:-mpiexec}`; nur `mpirun` im Container (third party, unveränderlich).
- `cluster/enroot_dtoo_import.md` — erzeugt `dtOO-opensuse.sqsh` (Name-Mismatch-Hazard, P0-2).
