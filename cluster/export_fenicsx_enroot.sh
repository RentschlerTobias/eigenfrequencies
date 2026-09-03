#!/usr/bin/env bash
# Build and export the FEniCSx image for enroot import.
#
# Usage:
#   bash cluster/export_fenicsx_enroot.sh [OUTPUT_DIR]
#
# Default OUTPUT_DIR: ./enroot-images (created if missing)
#
# The counterpart to export_dtoo_enroot.sh. Unlike dtOO, this image is not
# pulled but *built* from docker/fenicsx.Dockerfile: the plain
# dolfinx/dolfinx:stable has no gmsh Python module, and without it
# eigenfrequencies.io.load cannot read a .msh at all. The Dockerfile adds gmsh,
# scipy and the package itself on top of dolfinx.
#
# Run this from the repository root — the Dockerfile copies the checkout, and
# .dockerignore keeps the meshes and history out of the context.

set -euo pipefail

IMAGE="${FENICSX_IMAGE:-eigenfrequencies-fenicsx:latest}"
TAG_SAFE="eigenfrequencies-fenicsx"
DOCKERFILE="docker/fenicsx.Dockerfile"
OUTPUT_DIR="${1:-./enroot-images}"
mkdir -p "$OUTPUT_DIR"

TAR_GZ="$OUTPUT_DIR/${TAG_SAFE}.tar.gz"
TAR="$OUTPUT_DIR/${TAG_SAFE}.tar"

if [[ ! -f "$DOCKERFILE" ]]; then
    echo "[export] ERROR: run this from the repository root ($DOCKERFILE not found)" >&2
    exit 1
fi

echo "[export] Image:  $IMAGE"
echo "[export] Output: $TAR_GZ"

# Build unless the image is already there. Force a rebuild with a fresh tag or
# `docker rmi` — a stale image would silently ship old package code.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "[export] Building from $DOCKERFILE (several minutes) ..."
    # --network=host: the build installs from PyPI, and on a host with IPv4
    # forwarding disabled the default bridge cannot resolve DNS. Pulls still
    # work in that case (the daemon fetches those), so the failure only shows
    # up at the first pip install.
    docker build --network=host -f "$DOCKERFILE" -t "$IMAGE" .
else
    echo "[export] Image already built; delete it to force a rebuild:"
    echo "[export]   docker rmi $IMAGE"
fi

IMAGE_ID="$(docker images --no-trunc --quiet "$IMAGE" | head -n1)"
echo "[export] Image ID: $IMAGE_ID"

# Verify before shipping several GB: the two imports the modal stage makes.
echo "[export] Verifying dolfinx and gmsh import ..."
docker run --rm "$IMAGE" python3 -c \
    "import dolfinx, gmsh; print('dolfinx', dolfinx.__version__, '/ gmsh ok')"

rm -f "$TAR" "$TAR_GZ"

echo "[export] Saving to $TAR ..."
docker save "$IMAGE" -o "$TAR"

# gzip -f, not --best: the dtOO export showed --best takes >10 min for a
# marginal gain (T11).
echo "[export] Compressing to $TAR_GZ ..."
gzip -f "$TAR"

SIZE="$(du -h "$TAR_GZ" | cut -f1)"
echo "[export] Done. Size: $SIZE"
echo "[export]"
echo "[export] Next steps (user-dependent, cluster-side):"
echo "[export]   1. scp $TAR_GZ bwunicluster:\"\$WS/enroot-images/\"   (\$WS from cluster_env.sh)"
echo "[export]   2. On cluster, with cluster_env.sh sourced (zstd, not lzo):"
echo "[export]      enroot import -o \"\$ENROOT_IMAGES/fenicsx.sqsh\" docker-archive://${TAG_SAFE}.tar.gz"
echo "[export]   3. Smoke test:  sbatch cluster/submit_fenicsx_enroot_smoke.sh"
echo "[export]"
echo "[export] See cluster/enroot_fenicsx_import.md for the full instructions."
