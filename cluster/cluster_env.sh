#!/usr/bin/env bash
# Per-login setup on bwUniCluster. Source it, do not execute it:
#
#     source ~/eigenfrequencies/cluster/cluster_env.sh
#
# Add that one line to ~/.bashrc and every login is ready. Idempotent — sourcing
# it twice starts no second agent and appends no duplicate paths.
#
# What it sets up, in order:
#   WS                  the workspace holding the enroot images and the results
#   ENROOT_TEMP_PATH    import scratch, on LOCAL disk (see below)
#   ssh-agent           started once per login, key added if not already there
#   git identity        only if unset, so an existing config is never overwritten
#   EIGENFREQUENCIES_*  repo root and machine catalog for the case plugin
#
# ENROOT_TEMP_PATH must NOT point at the workspace. enroot flattens image layers
# through an overlayfs mount, and a parallel filesystem cannot host one: the
# import dies with "failed to mount overlay: ... Invalid argument" after the
# download has already finished.

# ── Python ────────────────────────────────────────────────────────────────
# The system python3 is 3.9; hydroflow-opt needs >=3.11,<3.14. Loaded here so
# the login shell and every sbatch job that sources this file agree.
PYTHON_MODULE="${PYTHON_MODULE:-devel/python/3.13.3-gnu-14.2}"
if command -v module >/dev/null 2>&1; then
    module load "$PYTHON_MODULE" 2>/dev/null || \
        echo "cluster_env: could not load $PYTHON_MODULE" >&2
fi

# ── Workspace ─────────────────────────────────────────────────────────────
WS_NAME="${WS_NAME:-eigenfreq}"
if [ -z "${WS:-}" ]; then
    WS="$(ws_find "$WS_NAME" 2>/dev/null)"
fi
if [ -z "$WS" ]; then
    echo "cluster_env: no workspace '$WS_NAME' — run: ws_allocate $WS_NAME 60" >&2
else
    export WS
    mkdir -p "$WS/enroot-images" "$WS/runs"
fi

# ── enroot import scratch, local disk ─────────────────────────────────────
export ENROOT_TEMP_PATH="${ENROOT_TEMP_PATH:-/tmp/$USER-enroot}"
mkdir -p "$ENROOT_TEMP_PATH"

# mksquashfs on the login node defaults to lzo, which the squashfuse on the
# compute nodes cannot read: the image imports fine and then fails at the first
# `enroot start` with "Squashfs image uses lzo compression, this version
# supports only xz, zlib, lz4, zstd". zstd is supported and just as fast.
export ENROOT_SQUASH_OPTIONS="${ENROOT_SQUASH_OPTIONS:--comp zstd -noD}"

# ── ssh-agent ─────────────────────────────────────────────────────────────
# Reuse a running agent across logins instead of starting one per shell: the
# socket is remembered in a fixed file, so a second login finds the first agent.
SSH_ENV="$HOME/.ssh/agent-env"
_agent_alive() { [ -n "${SSH_AUTH_SOCK:-}" ] && ssh-add -l >/dev/null 2>&1; }

if ! _agent_alive; then
    [ -f "$SSH_ENV" ] && . "$SSH_ENV" >/dev/null
fi
if ! _agent_alive && ! ssh-add -l 2>&1 | grep -q "no identities"; then
    # No usable agent: start one and remember where it lives.
    ssh-agent -s > "$SSH_ENV" 2>/dev/null
    chmod 600 "$SSH_ENV"
    . "$SSH_ENV" >/dev/null
fi
# Add the key only if the agent holds none — otherwise every login re-prompts.
if ssh-add -l 2>&1 | grep -q "no identities"; then
    for key in "$HOME/.ssh/id_ed25519" "$HOME/.ssh/id_rsa"; do
        [ -f "$key" ] && ssh-add "$key" 2>/dev/null && break
    done
fi

# ── git identity ──────────────────────────────────────────────────────────
# Only when unset. An existing config is left exactly as it is.
if [ -z "$(git config --global user.name 2>/dev/null)" ]; then
    git config --global user.name "Tobias Rentschler"
fi
if [ -z "$(git config --global user.email 2>/dev/null)" ]; then
    git config --global user.email "tobias-rentschler@gmx.de"
fi

# ── repo and machine catalog ──────────────────────────────────────────────
export EIGENFREQUENCIES_REPO="${EIGENFREQUENCIES_REPO:-$HOME/eigenfrequencies}"
export EIGENFREQUENCIES_MACHINES_DIR="$EIGENFREQUENCIES_REPO/adapters/machines"
export HYDROFLOW_VENV="${HYDROFLOW_VENV:-$HOME/venvs/hydroflow}"

# ── summary ───────────────────────────────────────────────────────────────
echo "WS=${WS:-<none>}  images=$(ls "$WS/enroot-images" 2>/dev/null | tr '\n' ' ')"
echo "repo=$EIGENFREQUENCIES_REPO  venv=$HYDROFLOW_VENV"
echo "ssh-agent: $(ssh-add -l 2>&1 | head -1)"
