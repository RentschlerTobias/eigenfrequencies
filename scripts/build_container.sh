#!/bin/bash
# Build the FEniCSx Docker container

cd "$(dirname "$0")/.."

docker build -f docker/fenicsx.Dockerfile -t eigenfrequencies-fenicsx:latest .