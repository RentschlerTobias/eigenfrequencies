#!/bin/bash
# Run the FEniCSx Docker container

WORKDIR=${1:-$(pwd)}

docker run --rm -it \
    -v "$WORKDIR":/workspace \
    -w /workspace \
    eigenfrequencies-fenicsx:latest