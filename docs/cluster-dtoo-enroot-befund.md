# Befund: dtOO unter Enroot auf dem Cluster

> **ÜBERHOLT (2026-09-03):** Dieses Dokument liegt in seiner Hauptthese
> (squashfuse) falsch: seit Commit `f76df43` werden die Images pro Job entpackt,
> und der verbleibende Kostenpunkt ist der Lustre-Read pro Job, nicht squashfuse.
> Es bleibt als Messdaten-Archiv stehen. Maßgebliche Befundlage und Fix-Basis:
> `docs/cluster-dtoo-enroot-befund-v2.md` — dessen Abschnitt 5 listet jede
> einzelne Korrektur.

## Kurzfassung

Keiner der bisherigen Tests konnte einen dtOO-Fall innerhalb des vorgesehenen
Zeitfensters unter Enroot auf dem Cluster erfolgreich abschließen. Damit ist
OpenFOAM-MPI derzeit nicht der erste Engpass: Der Ablauf scheitert oder hängt
bereits beim Container-, OpenFOAM- oder dtOO-Schritt.

Die vorhandene Parallelisierung ist grundsätzlich funktionsfähig, kann dieses
Problem aber nicht lösen. Mehrere Kandidaten parallel zu starten beschleunigt
keinen einzelnen dtOO-Lauf und kann die Belastung des Shared Filesystems
verstärken.

## Relevanter Ausführungspfad

```text
hydroflow-opt
  -> hydroflow worker
  -> dtOO unter Enroot
  -> Mesh-Erzeugung
  -> OpenFOAM decomposePar
  -> MPI simpleFoam -parallel
  -> reconstructPar
```

Der OpenFOAM-Solver wird erst nach erfolgreichem dtOO-Meshbau gestartet.

Relevante Dateien:

- `cluster/submit_hydroflow_opt.sh`
- `cluster/submit_dtoo_enroot_smoke.sh`
- `src/eigenfrequencies/hydroflow/physics.py`
- `turbine_runner/cfd/tistos_files/sbatch.tistos_ru_of.sh`

## Beobachtete Testergebnisse

### OpenFOAM-Environment bricht im Container ab

`dtOO_enroot_smoke_6743814.out` enthält:

```text
/usr/lib/openfoam/openfoam2606/etc/config.sh/functions: line 75: hostname: command not found
/usr/lib/openfoam/openfoam2606/etc/bashrc: line 184: WM_PROJECT_SITE: unbound variable
```

Der Test erreicht damit den dtOO-Import nicht. Ursache ist mindestens eine
inkomplette Containerumgebung (`hostname` fehlt) beziehungsweise die
Inkompatibilität von `set -u` mit dem OpenFOAM-Setup (`WM_PROJECT_SITE`).

### Enroot-Test läuft in Timeout

`dtOO_enroot_smoke_6743828.out` endet mit:

```text
State: TIMEOUT
Job wall-clock time: 00:05:22
CPU Utilized: 00:00:00
```

Der Smoke-Test war in
`cluster/submit_dtoo_enroot_smoke.sh:4` allerdings nur für fünf Minuten
beantragt:

```bash
#SBATCH --time=00:05:00
```

Das Ergebnis beweist daher einen Hänger oder eine sehr langsame Initialisierung,
aber noch keinen Überschreitungsnachweis für 30 Minuten.

### Hydroflow-Smoke erreicht kein erfolgreiches Ergebnis

`hydroflow_opt_6743794.out` und `hydroflow_opt_6743806.out` enthalten:

```text
run complete: 0/2 succeeded
```

Damit konnte kein einziger der beiden dtOO/FEniCSx-Testkandidaten erfolgreich
bewertet werden.

Weitere beobachtete Clusterfehler:

- `hydroflow_opt_6743761.out`: Config forderte 64 CPUs, Allocation enthielt 40.
- `hydroflow_opt_6743938.out` und `hydroflow_opt_6743939.out`: Das
  Run-Verzeichnis war beim Start nicht leer.
- Mehrere Jobs wurden durch `SIGTERM` beendet, ohne relevante CPU-Zeit zu
  verbrauchen. Diese Logs belegen keinen zehn Stunden laufenden OpenFOAM-Solver.

## Wahrscheinliche technische Ursachen

### 1. Containerumgebung nicht vollständig kompatibel

Der Fehler `hostname: command not found` zeigt, dass das dtOO-Image nicht alle
Programme enthält, die das OpenFOAM-Setup voraussetzt.

Der Fehler `WM_PROJECT_SITE: unbound variable` zeigt zusätzlich, dass die
nounset-Shelloption (`set -u`) beim Sourcen der OpenFOAM-Dateien wirksam ist.
OpenFOAM liest diese Variable ohne sichere Initialisierung.

### 2. Smoke-Test nutzt nicht exakt den Produktionspfad

`cluster/submit_dtoo_enroot_smoke.sh:36` startet direkt aus der `.sqsh`-Datei:

```bash
enroot start --root "$ENROOT_IMAGE"
```

Der Produktionswrapper `cluster/submit_hydroflow_opt.sh` entpackt Images dagegen
zunächst per `enroot create` auf Node-local Storage und startet anschließend den
Container über seinen Namen.

Der Standalone-Smoke-Test kann deshalb weiterhin SquashFS-/FUSE-/Lustre-
Verzögerungen messen und ist nicht vollständig mit dem Produktionspfad
vergleichbar.

### 3. Shared-Filesystem-I/O als starker Performanceverdacht

`cluster/submit_hydroflow_opt.sh:183-192` dokumentiert eine Messung aus dem
Cluster:

- dtOO `CreateStates` aus entpacktem Image: ungefähr 8 Sekunden
- dtOO `CreateStates` über Squashfuse: nach mehr als 20 Minuten nicht fertig

Diese Messung passt direkt zum beobachteten Verhalten. Container- und
Kandidaten-Dateien müssen auf Node-local Storage liegen, nicht auf dem Shared
Filesystem.

## Parallelisierung: Was bereits möglich ist

Es gibt zwei unabhängige Ebenen.

### Kandidatenparallelität

Hydroflow startet mehrere Evaluationsprozesse gleichzeitig:

```toml
[resources]
concurrent_evaluations = 16
```

Der aktuelle Hydroflow-Submit läuft dabei auf einem Node. Mehrere Nodes werden
durch diesen Pfad nicht automatisch genutzt.

### OpenFOAM-Solverparallelität

Der CFD-Adapter führt aus:

```text
decomposePar
mpiexec -n <mpi_ranks> simpleFoam -parallel
reconstructPar
```

Beispielkonfiguration:

```toml
[resources]
concurrent_evaluations = 16
mpi_ranks = 6
threads_per_rank = 1
```

Das ergibt theoretisch 16 Kandidaten mit jeweils sechs MPI-Ranks. Diese
Parallelisierung beginnt aber erst nach dem erfolgreichen dtOO-Meshbau.

## Abgrenzung zu `tistos-opt`

Die angegebene URL
`https://github.com/thomasisensee/tistos-opt` liefert aktuell HTTP 404.
Das passende öffentliche Projekt scheint
`thomasisensee/hydroflow-opt` zu sein.

Hydroflow unterstützt parallele Kandidaten-Evaluationen und stellt die Parameter
`concurrent_evaluations`, `mpi_ranks` und `threads_per_rank` bereit. Hydroflow
startet MPI jedoch nicht selbst. Der Case-Adapter muss den MPI-Befehl liefern;
das geschieht hier im OpenFOAM-Adapter.

## Schlussfolgerung

Der aktuelle Hauptfehler ist nicht „OpenFOAM kann nicht parallel laufen“.

Der belastbare Befund lautet:

1. Kein dtOO-Enroot-Test war erfolgreich.
2. Ein Test scheiterte nachweislich an der Containerumgebung.
3. Ein weiterer Test lief in Timeout, ohne CPU-Verbrauch.
4. Der separate 30-Minuten-Hydroflow-Smoke bewertete 0 von 2 Kandidaten
   erfolgreich.
5. Die dokumentierte Squashfuse-/Lustre-Verzögerung liefert eine plausible,
   technisch passende Erklärung für sehr langsame dtOO-Läufe.
6. OpenFOAM-MPI kann erst sinnvoll untersucht werden, wenn dtOO unter Enroot
   zuverlässig ein Mesh erzeugt.

## Nächster notwendiger Test

Ein aussagekräftiger 30-Minuten-Test muss den Produktionspfad exakt nachbilden:

1. `.sqsh`-Image auf Node-local Storage kopieren.
2. Image mit `enroot create` entpacken.
3. Entpackten Container per Namen mit `enroot start` starten.
4. Innerhalb der Shell `set +u` sicherstellen, bevor OpenFOAM `bashrc`
   gesourced wird.
5. Vor und nach jedem Schritt Zeitstempel schreiben:
   - OpenFOAM `bashrc`
   - dtOO `env.sh`
   - `import dtOOPythonSWIG`
   - `CreateStates`
   - `CreateMeshes`
6. Erst nach erfolgreichem Meshbau den OpenFOAM-CFD-Test starten.

Bis dieser Test erfolgreich ist, sind Änderungen an MPI-Rankzahl oder
Optimizer-Parallelität nicht der erste sinnvolle Fix.
