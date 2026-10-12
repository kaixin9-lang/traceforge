FROM python:3.12-slim-bookworm AS python
RUN useradd -u 10001 -m runner
WORKDIR /workspace
USER runner
CMD ["python", "--version"]

FROM node:24-bookworm-slim AS node
RUN useradd -u 10001 -m runner
WORKDIR /workspace
USER runner
CMD ["node", "--version"]

FROM maven:3.9-eclipse-temurin-21 AS java
RUN useradd -u 10001 -m runner
WORKDIR /workspace
USER runner
CMD ["java", "--version"]
