# Stage 1: Build
FROM eclipse-temurin:21-jdk AS builder

WORKDIR /build
COPY build.gradle settings.gradle gradle.properties ./
COPY gradle/ gradle/
COPY gradlew ./
RUN chmod +x gradlew && ./gradlew --no-daemon dependencies || true

COPY src/ src/
RUN ./gradlew --no-daemon bootJar

# Stage 2: Runtime
FROM eclipse-temurin:21-jre

LABEL org.opencontainers.image.source="https://github.com/agentspan/agentspan"
LABEL org.opencontainers.image.description="Agentspan Server — durable AI agent runtime"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY --from=builder /build/build/libs/agentspan-runtime.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
