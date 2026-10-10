#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for image in python:3.12-slim-bookworm node:24-bookworm-slim maven:3.9-eclipse-temurin-21; do docker pull "$image"; done
for runtime in python node java; do DOCKER_BUILDKIT=0 docker build -f sandbox.Dockerfile --target "$runtime" -t "traceforge-$runtime:1" .; done
