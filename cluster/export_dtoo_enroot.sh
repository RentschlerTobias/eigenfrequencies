#!/usr/bin/env bash
# Export the local dtOO Docker image to an OCI tarball for enroot import.
#
# Usage:
#   bash cluster/export_dtoo_enroot.sh [OUTPUT_DIR]
#
# Default OUTPUT_DIR: ./enroot-images (created if missing)
#
# The resulting .tar.gz can be transferred to bwUniCluster 3.0 and imported via:
#   enroot import -c dtOO-opensuse.sqsh -x dtOO-opensuse.tar.gz
# or (if enroot supports direct docker-archive import):
#   enroot import -o dtOO-opensuse.sqsh docker-archive://dtOO-opensuse.tar.gz

set -euo pipefail

IMAGE="atismer/dtoo-opensuse:stable"
TAG_SAFE="atismer_dtoo-opensuse_stable"
OUTPUT_DIR="${1:-./enroot-images}"
mkdir -p "$OUTPUT_DIR"

TAR_GZ="$OUTPUT_DIR/${TAG_SAFE}.tar.gz"
TAR="$OUTPUT_DIR/${TAG_SAFE}.tar"

echo "[export] Docker image: $IMAGE"
echo "[export] Output:      $TAR_GZ"

# Ensure image is present locally; pull if missing.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "[export] Image not found locally; pulling..."
    docker pull "$IMAGE"
fi

IMAGE_ID="$(docker images --no-trunc --quiet "$IMAGE" | head -n1)"
echo "[export] Image ID:    $IMAGE_ID"

# Remove stale tarball to avoid mixed layers.
rm -f "$TAR" "$TAR_GZ"

echo "[export] Saving Docker image to $TAR (this may take a minute)..."
docker save "$IMAGE" -o "$TAR"

echo "[export] Compressing to $TAR_GZ ..."
gzip -f "$TAR"

SIZE="$(du -h "$TAR_GZ" | cut -f1)"
echo "[export] Done. Size: $SIZE"
echo "[export]"
echo "[export] Next steps (user-dependent, cluster-side):"
echo "[export]   1. scp $TAR_GZ bwunicluster:/path/to/your/enroot-images/"
echo "[export]   2. On cluster: enroot import -o dtOO-opensuse.sqsh docker-archive://${TAG_SAFE}.tar.gz"
echo "[export]   3. Run smoke test: sbatch cluster/submit_dtoo_enroot_smoke.sh"
echo "[export]"
echo "[export] See cluster/enroot_dtoo_import.md for full bwUniCluster 3.0 instructions."
