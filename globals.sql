--
-- PostgreSQL database cluster dump
--

SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

--
-- Roles
--

CREATE ROLE postgres;
ALTER ROLE postgres WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS PASSWORD 'SCRAM-SHA-256$4096:GdrzTeJulyj+Wf10XNktTw==$5zKoQ7fpfgwsjXKynu4OeC3JCD3g6NcOMSZXaVNRyEA=:CEEXVjwaw7MYKbEHr+lJRUI+9R77zjZUBxEn1ncqK8Y=';

--
-- User Configurations
--








--
-- PostgreSQL database cluster dump complete
--

