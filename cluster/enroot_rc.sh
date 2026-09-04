# Command script for `enroot start --rc`, replacing the one the dtOO image ships.
#
# enroot hands the command and its arguments to the image's command script as
# positional parameters. The dtOO image's script sources OpenFOAM's
# configuration, and OpenFOAM's etc/config.sh/functions runs `eval` on those
# parameters at line 73. Two things follow, both measured on bwUniCluster
# 2026-09-04 and both fatal:
#
#   * quoting is destroyed. `bash -c 'source env.sh; checkMesh ...'` is re-read
#     as two statements at the outer level, so `checkMesh` ran before its
#     environment existed and failed with "libfiniteVolume.so: cannot open
#     shared object file" — while the second, correct execution succeeded. The
#     first one decides the exit code.
#   * everything runs twice. This is the long-standing "the shell runs its own
#     command string a SECOND time" from commit fae9a3d; sourcing OpenFOAM's
#     bashrc from a shell that had already changed directory turned the repeat
#     into an endless loop that produced no output at all.
#
# Replacing the script with this one line removes the eval, and with it both
# problems. The container environment is unaffected: it comes from the image
# configuration, not from that script — LD_LIBRARY_PATH is byte-identical with
# and without it, OpenFOAM's own libraries included.
#
# Deliberately not executable and deliberately not a #! script: enroot reads it
# as the command script, and the path has to resolve *inside* the container,
# which is why it lives in the repository — every stage mounts the repository
# root at its own path.
exec "$@"
