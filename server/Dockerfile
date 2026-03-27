# ─── Stage 1: Build the UI ────────────────────────────────────────────────────
# Build context must be the repo root so both ui/ and server/ are accessible.
#   docker build -f server/Dockerfile -t agentspan/server:latest .
FROM node:22-alpine AS ui-builder

WORKDIR /ui
RUN corepack enable && corepack prepare pnpm@latest --activate

# Layer-cache dependencies separately from source
COPY ui/package.json ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY ui/ .
# Empty VITE_WF_SERVER → all /api calls are relative to the same origin,
# which Spring Boot serves from the same port.
ENV VITE_WF_SERVER=""
RUN pnpm build

# ─── Stage 2: Build the server (embed UI into static resources) ───────────────
FROM eclipse-temurin:21-jdk AS builder

WORKDIR /build
COPY server/build.gradle server/settings.gradle server/gradle.properties ./
COPY server/gradle/ gradle/
COPY server/gradlew ./
RUN chmod +x gradlew && ./gradlew --no-daemon dependencies || true

COPY server/src/ src/

# Spring Boot automatically serves everything under classpath:/static/ at /
# Copy the Vite dist output there before building the JAR so it gets packaged in.
COPY --from=ui-builder /ui/dist/ src/main/resources/static/

ARG GRADLE_TASK=bootJar
ARG RUNTIME_JAR=agentspan-runtime.jar
RUN ./gradlew --no-daemon "${GRADLE_TASK}"
RUN cp "build/libs/${RUNTIME_JAR}" /build/runtime.jar

# ─── Stage 3: Runtime image ───────────────────────────────────────────────────
FROM eclipse-temurin:21-jre

LABEL org.opencontainers.image.source="https://github.com/agentspan/agentspan"
LABEL org.opencontainers.image.description="Agentspan — durable AI agent runtime with embedded UI"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY --from=builder /build/runtime.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
