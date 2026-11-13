# syntax=docker/dockerfile:1
# =============================================================================
# Apache Jena Fuseki 6.2.0 — the SHARED, READ-ONLY curriculum knowledge graph
#
# One of the three services that run OUTSIDE the student container. Every
# student queries the same graph at  http://<host>:3030/campus/sparql ; nobody
# can change it.
#
# Why this image exists at all: Apache publishes no official Fuseki image
# (checked 2026-11-12 — docker.io/apache/jena-fuseki does not exist), and the
# community ones are either stale (stain/jena-fuseki: 5.1.0, three known CVEs)
# or bundle the web UI and an admin API. This one is the server jar from Maven
# Central with its checksum pinned, started as the PLAIN server:
#
#     org.apache.jena.fuseki.main.cmds.FusekiMainCmd
#
# In Jena 6, `java -jar jena-fuseki-server.jar` starts the UI build WITH the
# /$/datasets admin API — which could add a writable dataset at runtime. The
# class above is the build without either. Verified against a local run:
# /, /$/datasets and /$/server all return 404; see ../README.md.
#
# The graph data is baked in (data/campus.ttl), so the container is stateless:
# no volume, any number of replicas, and a restart is a full reset.
#
# UNBUILT here (no docker CLI on the authoring workstation). The same jar, the
# same config.ttl and the same campus.ttl were run locally on Temurin 21.
#     docker build -t ai-analyst-fuseki:6.2.0 platform/fuseki
# =============================================================================
FROM eclipse-temurin:21-jre-alpine

# Take the security fixes Alpine has published since this base tag was built -
# the same job `apt-get upgrade -y` does in the other images of this repo. An
# image scanner flagged the bare tag (1 critical, 2 high) on 2026-11-12; scan
# the BUILT image with Trivy before rollout, as for every image here, and bump
# the base if anything is left that an upgrade cannot reach (i.e. in the JRE).
RUN apk upgrade --no-cache

# sha256 computed from the jar whose sha1 (d3490295a2b95677c1227d25bca8564d40f993a7)
# matches the one Maven Central publishes beside it. --checksum makes the build
# fail if the download is ever anything else.
ADD --checksum=sha256:2c92c598e65ab69d99820052e05f4277ed1d77980a8845f87545ad35b71a76ee \
    https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/6.2.0/jena-fuseki-server-6.2.0.jar \
    /fuseki/fuseki-server.jar

COPY config.ttl /fuseki/config.ttl
COPY data/campus.ttl /fuseki/data/campus.ttl

# Permissions are set explicitly, after the fact, and NOT with ADD --chmod.
# Docker stores a file ADDed from a URL with mode 600 (root only). The first
# version of this file relied on `ADD --chmod=644`; on the first real build
# (2026-11-12, Ubuntu, buildx docker-container builder) it did not take effect,
# the server user could not read the jar, and Java reported
#     Could not find or load main class ...FusekiMainCmd
# A plain chmod works on every builder.
RUN chmod 0755 /fuseki /fuseki/data \
    && chmod 0644 /fuseki/fuseki-server.jar /fuseki/config.ttl /fuseki/data/campus.ttl

# Non-root, and nothing under /fuseki is writable by it: the plain server with
# an in-memory dataset writes no files (confirmed - a local run left its
# working directory untouched), so the root filesystem can be read-only.
USER 1000:1000
# Fail the BUILD, with a clear message, if the server user cannot read what it
# needs - rather than a container that exits at start.
RUN for f in /fuseki/fuseki-server.jar /fuseki/config.ttl /fuseki/data/campus.ttl; do \
        test -r "$f" || { echo "UID 1000 cannot read $f" >&2; exit 1; }; \
    done
WORKDIR /fuseki
EXPOSE 3030

# The graph is ~1,500 triples; 512 MB of heap is generous. The upstream docker
# kit defaults to -Xmx4096m, which would be 4 GB reserved for nothing.
ENV JAVA_OPTIONS="-Xms128m -Xmx512m"

# `sh -c` so $JAVA_OPTIONS is expanded; `exec` so the JVM is PID 1 and receives
# SIGTERM. Extra arguments given to `docker run` are appended ("$@").
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTIONS -cp /fuseki/fuseki-server.jar org.apache.jena.fuseki.main.cmds.FusekiMainCmd --config=/fuseki/config.ttl \"$@\"", "fuseki"]

# /$/ping is enabled by `fuseki:pingEP true` in config.ttl.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD wget -q -O /dev/null 'http://localhost:3030/$/ping' || exit 1
