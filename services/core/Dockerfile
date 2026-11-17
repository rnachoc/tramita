# Core service image. Build from the repository root (the catalog lives in data/policies):
#   docker build -f services/core/Dockerfile -t tramita-core .
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /repo
COPY data/policies/catalog.yaml data/policies/clauses.json data/policies/
COPY services/core/pom.xml services/core/
RUN cd services/core && mvn -B -q dependency:go-offline
COPY services/core/src services/core/src
RUN cd services/core && mvn -B -q -DskipTests package \
    && cp target/tramita-core-*.jar /tmp/core.jar

FROM eclipse-temurin:17-jre
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin core
COPY --from=build /tmp/core.jar /app/core.jar
USER 10001
EXPOSE 8080
# Writes only to /tmp, which Kubernetes mounts as an emptyDir (read-only root file system).
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-Djava.io.tmpdir=/tmp", "-jar", "/app/core.jar"]
