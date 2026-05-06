# syntax=docker/dockerfile:1.7
# ---- build stage ----
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
RUN --mount=type=cache,target=/root/.m2 mvn -B -q dependency:go-offline
COPY src ./src
RUN --mount=type=cache,target=/root/.m2 mvn -B -q -DskipTests package \
    && cp target/gateway-*.jar /workspace/app.jar \
    && cd /workspace && java -Djarmode=tools -jar app.jar extract --layers --launcher --destination layers

# ---- runtime stage ----
FROM eclipse-temurin:21-jre-alpine AS runtime
RUN addgroup -S app && adduser -S -G app app \
    && apk add --no-cache curl
WORKDIR /app
COPY --from=build /workspace/layers/dependencies/ ./
COPY --from=build /workspace/layers/spring-boot-loader/ ./
COPY --from=build /workspace/layers/snapshot-dependencies/ ./
COPY --from=build /workspace/layers/application/ ./
USER app
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8080/actuator/health || exit 1
ENV SPRING_PROFILES_ACTIVE=prod
ENTRYPOINT ["java", "-XX:+UseContainerSupport", "-XX:MaxRAMPercentage=75", "org.springframework.boot.loader.launch.JarLauncher"]
