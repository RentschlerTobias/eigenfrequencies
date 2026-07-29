HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- "ich war schon länger nicht mehr mit dem projekt beschäftigt. Ich hatte zuvor in dem repo auf dem cluster einen lauf gestartet, hier habe ich jetzt logfiles, weshalb ich auf dem cluster das .gitignore geändert habe um diese zu analysieren. nebenbei hatte ich aber eine validierungs geometrie bekommen, die ich hier local hinzugefügt habe und eine codee validierung hinzugefügt habe. Jetzt wollte ich die .gitignore von dem cluster hinzufügen und anschließend die logs um das problem zu identifiezieren, git probleme, was mache ich jetzt:" (followed by cluster terminal output showing rejected push)
- "ok ich habe es jetzt gepush. Analysiere mir die letzte optimierung"
- (Decisions on EVAL_MODE + two optimizations A=pure CFD, B=CFD+modal — see compressed history)
- "pull neue log: job 6026412 habei ich manuell gecanceld (doppelt ins queueing system gestellt"
- "ch teste geradae nur cfd, da das die probleme macht, modal analyse läuft. du kannst im ./de_framework repo nachschauen das war ein funktionierender optimerungs lauf (ohne modalanalyse auf dem cluster), achte auf die branches, es gibt einen speziell für das cluster"
- "make a pull and a handoff for a context free ai agent"

GOAL
----
Iterate the CFD-only smoke test on bwUniCluster until ok>0/24, then scale to production; the user is currently running `cluster/submit_de_cfd_only.sh` on the cluster with the latest UCX-fix commit (6fadeae) and will push logs for analysis.

WORK COMPLETED
--------------
- I resolved the diverged-branches git saga (cluster commit rebased onto origin/main, pushed clean).
- I analyzed the last available cluster run 5824899: 128 workers published Pyro URIs but the client printed 30 min of silence then SLURM TIMEOUT — walltime too short, no instrumentation.
- I added an EVAL_MODE field to ObjectiveConfig (env override EVAL_MODE, validated against combined/cfd_only/resonance_only) in turbine_runner/config.py.
- I refactored server_de.py Evaluator.evaluate() into three branches on eval_mode: cfd_only (only _run_cfd + cfd_scalar), resonance_only (dtoo + fenicsx + resonance_term), combined (both + combined_objective). CFD_ENABLED=0 forces resonance_only for legacy compat.
- I instrumented optimize_de.py: discovery timeout 120→600s with 15s poll logs, startup/config/per-gen prints all flush=True.
- I refactored submit scripts: cluster/_submit_de_common.sh (shared in-allocation body), cluster/submit_de_cfd_only.sh + cluster/submit_de_combined.sh (smoke headers: dev_cpu_il, 6 nodes × 4 tasks × 16 cpus, 30min, POP_SIZE=24 auto, MAX_GEN=1), cluster/submit_de.sh (legacy wrapper). RUN_TAG namespacing (server_logs/<tag>/, de_state_<tag>.json, de_history_<tag>.jsonl) so A/B runs don't clobber each other. DE_STATE_FILE/DE_HISTORY_FILE respect env override for resuming.
- I added a DESIGN_PRESET system to config.py with full30 (30 DoF from templateState.xml slider ranges) as default and t_midspan3 (3 DoF, the July baseline). dtoo_export.py applies {label:value} generically.
- I fixed gen-0 init in optimize_de.py from uniform-random (produced degenerate 30-DoF geometry → dtOO destroyAndCreate crash 100%) to template-centered: x0 + N(0, DE_INIT_SPREAD*span), population[0]=x0 as guaranteed-valid reference. DE_INIT_SPREAD env default 0.05.
- I widened _run_dtoo/_run_cfd error tail capture 1600→8000 chars so the dtOO eGeneral message preceding the backtrace reaches worker logs.
- I fixed two submit-script bugs: `set -euo pipefail` + `source ~/pe` (OpenFOAM bashrc references unset WM_THIRD_PARTY_DIR) → wrapped with `set +u; source ~/pe || true; set -u` (the || true because foamInit path is broken on uc3 and returns exit 1).
- I diagnosed smoke run 6026480 (cfd_only): template-centered init WORKS but ok=0/24 with `ucs_callbackq_cleanup` SIGSEGV — root cause was my UCX_TLS=sm + OMPI_MCA exports forcing UCX init in a non-MPI srun context.
- I consulted the working de_framework repo (branch `bwCl`, commit 7d16f00) via an explore agent: it has ZERO UCX/OMPI exports and runs dtOO runCurrentState() in a bare `subprocess.run(['python3', '-c', '...'])` with env inherited from the srun parent (no bash -lc, no re-source ~/pe).
- I shipped the fix in commit 6fadeae: _run_cfd build_cmd changed from `bash -lc "source ~/pe && export UCX_TLS=sm ... && python3 ..."` to `[sys.executable, CFD_BUILD, ...]` with cwd=wdir, env inherited + explicit dtOO LD_LIBRARY_PATH; removed all UCX/OMPI exports from both build and solve (of_env) steps. py_compile OK, pushed.
- I documented EVAL_MODE + submit variants + resume-chaining in cluster/env_notes.md.

CURRENT STATE
-------------
- Local branch: main, clean tree (only graphify-out noise + demo/beam/main.py uncommitted, both unrelated and ignorable).
- HEAD: 6fadeae "fix(cfd): bare python3 subprocess for dtOO build, remove UCX exports" — pushed to origin/main.
- The user is running `sbatch cluster/submit_de_cfd_only.sh` on bwUniCluster with this commit; new logs (.out + server_logs/cfd_only/worker_*.log + de_state_cfd_only.json + de_history_cfd_only.jsonl) are expected as a push from the cluster.
- CFD has NEVER successfully completed on the cluster across all prior runs (5824899 silence, 5827851 all cfd_failed, 6026413/6026480 ok=0/24). The 6fadeae fix is the best-aligned with the proven-working de_framework pattern.
- Modal analysis (resonance_only) DOES work on cluster (July run 5827863: ok=181-224/256, 6 gens, best 5.307→5.245) — user confirmed "modal analyse läuft".
- LSP (basedpyright) is NOT installed locally and the user previously declined installation; verification is via `python3 -m py_compile` + runtime import tests.

PENDING TASKS
-------------
- Await the user's cluster push of the new cfd_only smoke run logs (with 6fadeae).
- Analyze: did the ucs_callbackq_cleanup segfault disappear? Is ok>0/24? If still failing, read the now-8000-char error tails in server_logs/cfd_only/worker_*.log for the real dtOO eGeneral message.
- If CFD works: scale to production (cpu_il partition, 72h, larger POP_SIZE/MAX_GEN, resume-chaining via DE_STATE_FILE across 30-min dev_cpu_il runs if staying on dev).
- If CFD still fails: the next suspect is the `source ~/pe` env itself (de_framework uses `source ~/de` — a different env script; user should verify whether ~/pe loads an MPI module that initializes UCX at import time, poisoning even the bare subprocess). Also possible: Gmsh meshing failures on degenerate 30-DoF designs (seen in combined 6026481 worker_4/12: "Unable to recover edge on curve" / "map2dTo3d::reparamOnFace !md.converged()") — these are geometry-quality issues, fixable by tightening DE_INIT_SPREAD or bounds.
- Combined (CFD+modal) smoke is secondary per user ("ch teste geradae nur cfd"); the enroot container path was fixed in 9ba1295 (reverted per-worker ENROOT_DATA_PATH that hid pyxis_fenicsx).
- All todos from this session are completed (last todowrite: UCX fix + py_compile + push, both done).

KEY FILES
---------
- turbine_runner/optimize.py — _run_dtoo (modal build), _run_fenicsx (enroot container), _run_cfd (dtoo_cfd_build + sbatch.tistos_ru_of.sh). The 6fadeae fix lives here in _run_cfd (lines ~142-165).
- turbine_runner/server_de.py — Pyro5 daemon, Evaluator.evaluate() with three eval_mode branches. Writes URI to DE_URI_DIR/worker_<id>.uri atomically.
- turbine_runner/optimize_de.py — DE client. _discover_servers (600s timeout, 15s polls), main() with instrumentation prints. Template-centered gen-0 init (x0 + N(0, DE_INIT_SPREAD*span), population[0]=x0).
- turbine_runner/config.py — OptimizationConfig (Z=18, 90rpm, f_bp=27Hz, harmonics 1-6, margin max(5Hz,5%)), DEConfig (env-overridable), CFDConfig, ObjectiveConfig (eval_mode + env override + validation), DesignConfig with _DESIGN_PRESETS (full30 default, t_midspan3).
- turbine_runner/dtoo_cfd_build.py — writes <state>.xml from templateState.xml with design const-values, then createStatesAndMeshes.CreateStates + CreateMeshes (runCurrentState). Prints "CFD_CASE_DIR <path>".
- turbine_runner/cfd/createStatesAndMeshes.py — dtOO geometry + mesh creation. CreateMeshes calls dC.get(caseName+'_n').runCurrentState() (the segfault site when run in wrong context).
- cluster/_submit_de_common.sh — shared in-allocation body (no #SBATCH). Sources ~/pe with set +u guard, POP_SIZE/MAX_GEN/SEED env calc, per-variant namespacing, TMPDIR copy, worker srun loop, client run.
- cluster/submit_de_cfd_only.sh — smoke #SBATCH header (dev_cpu_il, 6 nodes × 4 × 16, 30min), RUN_TAG=cfd_only, EVAL_MODE=cfd_only, W_RESONANCE=0.0. Production override example in header.
- cluster/env_notes.md — documents EVAL_MODE table, submit variants, resume-chaining, bwUniCluster partition reference.
- /home/t1dde/Duty/projects/de_framework (branch bwCl, commit 7d16f00) — the PROVEN-WORKING CFD-only cluster optimization repo. Reference for how dtOO+CFD should be invoked. Key: sim_tistos.py:mesh() uses subprocess.run(['python3', '-c', '...']) for runCurrentState, no UCX exports, source ~/de (not ~/pe).

IMPORTANT DECISIONS
-------------------
- EVAL_MODE as ObjectiveConfig field + env override (not a separate code path) — user decision.
- Two separate submit scripts (not one parameterized) — user decision, so A/B runs are independent sbatch submissions.
- dev_cpu_il only for now (other partitions have days of queueing) — user decision.
- full30 (30 DoF) as default DESIGN_PRESET — user decision, matches the 30-DOF optimization the user remembered.
- Template-centered DE init (not uniform-random) — my decision after uniform-random produced 100% degenerate geometry; x0 is the known-valid template baseline from July.
- Mirror de_framework's bare-subprocess pattern for dtOO — my decision after explore agent confirmed it works and identified UCX-forcing as the segfault cause.
- Run A/B in parallel without singleton dependency — my decision (legacy submit_de.sh had --dependency=singleton, new variants don't).

EXPLICIT CONSTRAINTS
--------------------
- "Du (Sisyphus, OpenCode, Claude, egal welcher Agent-Name) erwähnst dich NIE selbst in irgendeinem Artefakt, das ein Online-Repo, ein Commit, eine PR-Beschreibung, Code, ein Kommentar, ein Doc oder eine andere outward-facing Datei wird." — from ~/.config/opencode/AGENTS.md. No Co-Authored-By, no AI attribution, no agent signatures anywhere.
- User comment-policy (m0151, strict): "Kommentare aufs Allermindeste — bei 1-Variablen-Änderung KEINEN Kommentarblock mitziehen; nicht-essenzielle Kommentare löschen. Das ist alles AI slop." Keep comments minimal; section markers matching existing file style are OK if they carry load-bearing info (e.g. regression guards).
- Workflow agreement (m0128): 1. I commit+push lokal → 2. user starts on cluster, commits+pushes logs → 3. I analyze+fix → iterate. Do NOT run anything on the cluster myself.
- "ch teste geradae nur cfd" — focus on CFD-only for now; modal runs separately and works.

CONTEXT FOR CONTINUATION
------------------------
- The iteration loop is: (1) I ship a fix commit+push, (2) the user does `git pull` + `rm -f turbine_runner/de_state_*.json turbine_runner/de_history_*.jsonl` + `sbatch cluster/submit_de_cfd_only.sh` on the cluster, (3) the user commits+pushes the resulting logs, (4) I pull and analyze. We are between step 1 and step 2 of the latest iteration (6fadeae).
- When analyzing a new run: read `de_cfd_only_<jobid>.out` first (the client log — shows banner, discovery, gen dispatch, ok count), then `server_logs/cfd_only/worker_*.log` for per-worker failures (now 8000-char error tails), then `turbine_runner/de_state_cfd_only.json` (checkpoint) and `de_history_cfd_only.jsonl` (per-gen best).
- The segfault signature to watch for: `Caught signal 11 (Segmentation fault: invalid permissions for mapped object)` in `ucs_callbackq_cleanup()`. If gone → 6fadeae worked. If present → the bare-subprocess approach isn't enough and `source ~/pe` itself poisons the env; investigate ~/pe vs ~/de with the user.
- The "bash: Agent: command not found" lines in worker logs are NOISE (ssh-agent output eval'd wrong in bash -lc) — ignore.
- dev_cpu_il is capped at 30 min — production needs cpu_il (72h) or resume-chaining via DE_STATE_FILE across multiple 30-min runs.
- bwUniCluster 3.0: dev_cpu_il max 8 nodes × 64 tasks, 30 min, singleton; cpu_il max 30 nodes × 64 tasks, 72h; login nodes auto-kill heavy compute; $TMPDIR = local NVMe per node; Workspaces on Lustre for non-permanent data.
- graphify-out/ is a knowledge-graph artifact dir; its dirty state is expected and ignorable (per project AGENTS.md). demo/beam/main.py modified is unrelated to this work.
- Pull requires `git stash push -m tmp && git pull --ff-only && git stash pop` because pull.rebase=true blocks on dirty tree (graphify-out noise).
