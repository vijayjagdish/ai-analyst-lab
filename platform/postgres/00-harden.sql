-- One-time hardening for the lab's DEDICATED PostgreSQL server.
--
-- Run once as a superuser, before any student is provisioned. The official
-- postgres image runs every *.sql file in /docker-entrypoint-initdb.d when it
-- initialises an empty data directory, so mounting this file there is enough
-- (docker-compose.yml and the Kubernetes manifest both do).
--
-- Why it is needed: out of the box, EVERY role may connect to the `postgres`
-- and `template1` databases. A student role could therefore connect to
-- `postgres` - not to another student's database, but still a database the
-- student has no business being in. Verified on PostgreSQL 16: before this
-- file a student login to `postgres` succeeds; after it, it is refused.
--
-- Do NOT point this lab at a PostgreSQL server that other applications use.
-- Those applications may rely on the default this file removes, and role and
-- database NAMES are visible to every login on a shared server.

REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT ON DATABASE template1 FROM PUBLIC;

-- New databases are copied from template1. Nobody but the owner gets to create
-- objects in the public schema of a database made from it. (PostgreSQL 15+
-- already defaults to this; stating it keeps older servers in line.)
\connect template1
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
