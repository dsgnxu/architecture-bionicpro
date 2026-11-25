-- Run against an already-initialized crm_db volume (init.sql runs only on first boot):
--   docker compose exec -T crm_db psql -U crm -d crm < cdc/bootstrap-crm-replication.sql
-- Also recreate crm_db with wal_level=logical (compose command) if needed:
--   docker compose up -d --force-recreate crm_db

ALTER USER crm WITH REPLICATION;
ALTER TABLE public.clients REPLICA IDENTITY FULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'dbz_crm_publication') THEN
        CREATE PUBLICATION dbz_crm_publication FOR TABLE public.clients;
    END IF;
END $$;

SELECT name, setting FROM pg_settings WHERE name IN ('wal_level', 'max_replication_slots', 'max_wal_senders');
