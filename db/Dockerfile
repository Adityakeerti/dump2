# CitySense database image: PostgreSQL 16 + PostGIS 3.4 + pgvector
FROM postgis/postgis:16-3.4

# postgis/postgis:16-3.4 is based on Debian bullseye (EOL); PGDG moved
# bullseye packages from apt.postgresql.org to apt-archive.postgresql.org,
# so repoint the repo before installing pgvector.
RUN sed -i 's#http://apt.postgresql.org/pub/repos/apt/#http://apt-archive.postgresql.org/pub/repos/apt/#' \
        /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
