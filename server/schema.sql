-- openEDM database (PostgreSQL). Applied at every start by server/store.py: every statement must be safe to re-run.
--
-- locality_id is part of the natural key for all data tables so the same source IDs can exist in different localities.

-- ── localities ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS locality (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug       text NOT NULL UNIQUE,
    name       text NOT NULL,
    country    text NOT NULL DEFAULT 'CH',
    map_config jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW()
);
ALTER TABLE locality ADD COLUMN IF NOT EXISTS demo boolean NOT NULL DEFAULT false;

-- The demo locality. First, because the upgrade below attaches the existing rows to it.
INSERT INTO locality (slug, name, map_config, demo)
VALUES ('rive-claire', 'Rive-Claire', '{"key":"rc","dir":"map-rc/"}', true)
ON CONFLICT (slug) DO UPDATE
  SET map_config = EXCLUDED.map_config,
      demo       = EXCLUDED.demo
  WHERE locality.map_config IS NULL OR locality.demo <> EXCLUDED.demo;

-- ── upgrade from the single-municipality version ──────────────────────────────
-- A database created before localities existed has the tables below without locality_id, and CREATE TABLE IF NOT
-- EXISTS leaves them as they are. This block runs once on such a database: every existing row goes to Rive-Claire
-- (the only dataset that version could hold) and the keys get locality_id in front. Nothing is deleted.
-- tools/check_upgrade.sh tests it on every pull request.
DO $$
DECLARE
    rc_id integer;
    t     text;
BEGIN
    IF to_regclass('import_run') IS NULL OR EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'import_run' AND column_name = 'locality_id') THEN
        RETURN;
    END IF;
    SELECT id INTO rc_id FROM locality WHERE slug = 'rive-claire';
    ALTER TABLE reading DROP CONSTRAINT reading_id_compteur_fkey;      -- points at the old meter key, re-added below
    FOREACH t IN ARRAY ARRAY['import_run', 'building', 'installation', 'meter', 'reference'] LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN locality_id integer REFERENCES locality ON DELETE CASCADE', t);
        EXECUTE format('UPDATE %I SET locality_id = %s', t, rc_id);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN locality_id SET NOT NULL', t);
    END LOOP;
    ALTER TABLE reading ADD COLUMN locality_id integer;
    EXECUTE format('UPDATE reading SET locality_id = %s', rc_id);
    ALTER TABLE reading ALTER COLUMN locality_id SET NOT NULL;

    ALTER TABLE building     DROP CONSTRAINT building_pkey,     ADD PRIMARY KEY (locality_id, id_batiment);
    ALTER TABLE installation DROP CONSTRAINT installation_pkey, ADD PRIMARY KEY (locality_id, id_installation);
    ALTER TABLE meter        DROP CONSTRAINT meter_pkey,        ADD PRIMARY KEY (locality_id, id_compteur);
    ALTER TABLE reference    DROP CONSTRAINT reference_pkey,    ADD PRIMARY KEY (locality_id, name, pos);
    ALTER TABLE reading      DROP CONSTRAINT reading_pkey,      ADD PRIMARY KEY (locality_id, id_compteur, mois);
    ALTER TABLE reading ADD FOREIGN KEY (locality_id, id_compteur) REFERENCES meter (locality_id, id_compteur) ON DELETE CASCADE;

    DROP INDEX building_site, installation_site, meter_site, reading_site;   -- re-created below with locality_id
END $$;

-- ── import runs ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS import_run (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    locality_id integer NOT NULL REFERENCES locality ON DELETE CASCADE,
    at          timestamptz NOT NULL DEFAULT now(),
    source      text NOT NULL,
    rows_read   integer,
    loaded      integer,
    rejected    integer,
    added       integer,
    unchanged   integer,
    changed     integer,
    report      jsonb
);

-- ── reference tables (locality-scoped natural keys) ───────────────────────────
CREATE TABLE IF NOT EXISTS building (
    locality_id         integer NOT NULL REFERENCES locality ON DELETE CASCADE,
    id_batiment         text NOT NULL,
    id_site text NOT NULL, nom_site text, quartier text, typologie text, nom_batiment text,
    annee_construction integer, annee_renovation integer, sre_m2 numeric, niveaux numeric, label text,
    logements numeric, ouverture text, x_km numeric, y_km numeric, remarque text,
    pos integer NOT NULL,
    PRIMARY KEY (locality_id, id_batiment)
);
CREATE INDEX IF NOT EXISTS building_site ON building (locality_id, id_site);

CREATE TABLE IF NOT EXISTS installation (
    locality_id      integer NOT NULL REFERENCES locality ON DELETE CASCADE,
    id_installation  text NOT NULL,
    id_site text NOT NULL, type text, libelle text, vecteur text, puissance_kw numeric,
    mise_en_service text, retrait text, remarque text,
    pos integer NOT NULL,
    PRIMARY KEY (locality_id, id_installation)
);
CREATE INDEX IF NOT EXISTS installation_site ON installation (locality_id, id_site);

CREATE TABLE IF NOT EXISTS meter (
    locality_id  integer NOT NULL REFERENCES locality ON DELETE CASCADE,
    id_compteur  text NOT NULL,
    id_site text NOT NULL, libelle text, fluide text, unite text, niveau text, mesure text, parent text,
    fournisseur_donnee text, releve text, debut text, fin text,
    pos integer NOT NULL,
    PRIMARY KEY (locality_id, id_compteur)
);
CREATE INDEX IF NOT EXISTS meter_site ON meter (locality_id, id_site);

-- ── readings (one row per locality+meter+month) ────────────────────────────────
CREATE TABLE IF NOT EXISTS reading (
    locality_id integer NOT NULL,
    id_compteur text NOT NULL,
    mois        text NOT NULL CHECK (mois ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    id_site text, fluide text, mesure text,
    valeur numeric, unite text, energie_kwh numeric, qualite text,
    import_id integer NOT NULL REFERENCES import_run,
    pos integer NOT NULL,
    PRIMARY KEY (locality_id, id_compteur, mois),
    FOREIGN KEY (locality_id, id_compteur) REFERENCES meter (locality_id, id_compteur) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS reading_site ON reading (locality_id, id_site, mois);

-- reading.import_id must cascade so deleting a locality cascades through import_run → reading
ALTER TABLE reading DROP CONSTRAINT IF EXISTS reading_import_id_fkey;
ALTER TABLE reading ADD CONSTRAINT reading_import_id_fkey
    FOREIGN KEY (import_id) REFERENCES import_run ON DELETE CASCADE;

-- ── rejected rows ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rejected_row (
    import_id   integer NOT NULL REFERENCES import_run ON DELETE CASCADE,
    pos         integer NOT NULL,
    reason      text NOT NULL,
    row         jsonb NOT NULL,
    PRIMARY KEY (import_id, pos)
);

-- ── reference / lookup tables ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reference (
    locality_id integer NOT NULL REFERENCES locality ON DELETE CASCADE,
    name text NOT NULL,
    pos  integer NOT NULL,
    row  jsonb NOT NULL,
    PRIMARY KEY (locality_id, name, pos)
);

-- ── accounts & sessions ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_user (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username     text NOT NULL UNIQUE,
    pw_hash      text NOT NULL,
    role         text NOT NULL,
    demo         boolean NOT NULL DEFAULT false,
    failed       integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE app_user ADD COLUMN IF NOT EXISTS demo boolean NOT NULL DEFAULT false;
ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_role_check;
UPDATE app_user SET role = 'technique' WHERE role = 'manager';
ALTER TABLE app_user ADD CONSTRAINT app_user_role_check CHECK (role IN ('admin', 'technique', 'elu', 'public'));

CREATE TABLE IF NOT EXISTS user_locality (
    user_id     integer NOT NULL REFERENCES app_user ON DELETE CASCADE,
    locality_id integer NOT NULL REFERENCES locality ON DELETE CASCADE,
    role        text NOT NULL DEFAULT 'viewer'
                     CHECK (role IN ('admin', 'manager', 'viewer')),
    granted_at  timestamptz NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, locality_id)
);

CREATE TABLE IF NOT EXISTS session (
    token_hash text PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES app_user ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);

-- ── staging (sas de chargement) — after app_user so the FK is valid ───────────
CREATE TABLE IF NOT EXISTS staged_import (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    locality_id integer NOT NULL REFERENCES locality ON DELETE CASCADE,
    uploaded_at timestamptz NOT NULL DEFAULT NOW(),
    uploaded_by integer REFERENCES app_user,
    source      text NOT NULL,
    status      text NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'committed', 'discarded')),
    quality     jsonb
);

CREATE TABLE IF NOT EXISTS staged_file (
    id               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staged_import_id integer NOT NULL REFERENCES staged_import ON DELETE CASCADE,
    table_name       text NOT NULL,
    filename         text NOT NULL,
    confidence       numeric(4,2),
    row_count        integer NOT NULL,
    rows             jsonb NOT NULL,
    UNIQUE (staged_import_id, table_name)
);
CREATE INDEX IF NOT EXISTS staged_file_import ON staged_file (staged_import_id);

-- ── seed ──────────────────────────────────────────────────────────────────────
-- Grant all existing (non-demo) users access to Rive-Claire.
-- Demo accounts are granted in cli.py AFTER auth.reset_demo() creates them.
INSERT INTO user_locality (user_id, locality_id, role)
SELECT u.id, l.id,
    CASE u.role WHEN 'admin' THEN 'admin' WHEN 'technique' THEN 'manager' ELSE 'viewer' END
FROM app_user u CROSS JOIN locality l
WHERE l.slug = 'rive-claire' AND u.demo = false
ON CONFLICT DO NOTHING;
