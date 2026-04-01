# ─── Stage 1: Build the UI ────────────────────────────────────────────────────
# Build context must be the repo root so both ui/ and server/ are accessible.
#   docker build -f server/Dockerfile -t agentspan/server:latest .
# The UI output is static and architecture-independent, so build it on the
# native build host rather than under per-target emulation in multi-arch builds.
FROM --platform=$BUILDPLATFORM node:22-alpine AS ui-builder

WORKDIR /ui
RUN corepack enable && corepack prepare pnpm@latest --activate
ENV NODE_OPTIONS=--max-old-space-size=4096

# Layer-cache dependencies separately from source
COPY ui/package.json ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY ui/ .
# Empty VITE_WF_SERVER → all /api calls are relative to the same origin,
# which Spring Boot serves from the same port.
ENV VITE_WF_SERVER=""
RUN pnpm build

# ─── Stage 2: Build the server (embed UI into static resources) ───────────────
# The Spring Boot jar is also architecture-independent, so keep this on the
# native build host and only vary the final runtime image per target platform.
FROM --platform=$BUILDPLATFORM eclipse-temurin:21-jdk AS builder

WORKDIR /build
COPY server/build.gradle server/settings.gradle server/gradle.properties ./
COPY server/gradle/ gradle/
COPY server/gradlew ./
RUN chmod +x gradlew && ./gradlew --no-daemon dependencies || true

COPY server/src/ src/

# Spring Boot automatically serves everything under classpath:/static/ at /
# Copy the Vite dist output there before building the JAR so it gets packaged in.
COPY --from=ui-builder /ui/dist/ src/main/resources/static/

RUN ./gradlew --no-daemon bootJar
RUN cp build/libs/agentspan-runtime.jar /build/runtime.jar

# ─── Stage 3: Runtime image ───────────────────────────────────────────────────
FROM eclipse-temurin:21-jre

LABEL org.opencontainers.image.source="https://github.com/agentspan-ai/agentspan"
LABEL org.opencontainers.image.description="Agentspan — durable AI agent runtime with embedded UI"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY --from=builder /build/runtime.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
