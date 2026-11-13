-- openEDM database (PostgreSQL). Applied at every start by server/store.py: every statement must be safe to re-run.
--
-- The reference tables and the readings keep the column names of the Rive-Claire dataset (its dictionary documents
-- them: rive-claire/csv/rive-claire-dictionnaire.csv). Months are 'YYYY-MM' text, as in the source.
-- Reference data (buildings, installations, meters) is kept apart from the monthly readings.
-- An empty cell in the source is NULL here. "pos" is the row's position in the imported file.

CREATE TABLE IF NOT EXISTS import_run (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    source      text NOT NULL,
    rows_read   integer,                -- readings in the file
    loaded      integer,
    rejected    integer,
    added       integer,                -- new (meter, month)
    unchanged   integer,                -- already there with the same value: a re-import gives added = 0
    changed     integer,                -- already there with another value: updated
    report      jsonb                   -- the quality report of this import (tools/rc_quality.py)
);

CREATE TABLE IF NOT EXISTS building (
    id_batiment text PRIMARY KEY,
    id_site text NOT NULL, nom_site text, quartier text, typologie text, nom_batiment text,
    annee_construction integer, annee_renovation integer, sre_m2 numeric, niveaux numeric, label text,
    logements numeric, ouverture text, x_km numeric, y_km numeric, remarque text,
    pos integer NOT NULL
);
CREATE INDEX IF NOT EXISTS building_site ON building (id_site);

CREATE TABLE IF NOT EXISTS installation (
    id_installation text PRIMARY KEY,
    id_site text NOT NULL, type text, libelle text, vecteur text, puissance_kw numeric,
    mise_en_service text, retrait text, remarque text,
    pos integer NOT NULL
);
CREATE INDEX IF NOT EXISTS installation_site ON installation (id_site);

CREATE TABLE IF NOT EXISTS meter (
    id_compteur text PRIMARY KEY,
    id_site text NOT NULL, libelle text, fluide text, unite text, niveau text, mesure text, parent text,
    fournisseur_donnee text, releve text, debut text, fin text,
    pos integer NOT NULL
);
CREATE INDEX IF NOT EXISTS meter_site ON meter (id_site);

-- One row per meter and month: the natural key makes the import repeatable.
CREATE TABLE IF NOT EXISTS reading (
    id_compteur text NOT NULL REFERENCES meter,
    mois        text NOT NULL CHECK (mois ~ '^\d{4}-(0[1-9]|1[0-2])$'),
    id_site text, fluide text, mesure text,
    valeur numeric, unite text, energie_kwh numeric, qualite text,
    import_id integer NOT NULL REFERENCES import_run,
    pos integer NOT NULL,
    PRIMARY KEY (id_compteur, mois)
);
CREATE INDEX IF NOT EXISTS reading_site ON reading (id_site, mois);

-- Rows the checks refused, as they were in the file, with the check that refused them. They never reach `reading`.
CREATE TABLE IF NOT EXISTS rejected_row (
    import_id integer NOT NULL REFERENCES import_run ON DELETE CASCADE,
    pos       integer NOT NULL,
    reason    text NOT NULL,
    row       jsonb NOT NULL,
    PRIMARY KEY (import_id, pos)
);

-- Small lookup tables of the dataset (climate, normals, typologies, conversion factors, energy carriers), kept as given.
CREATE TABLE IF NOT EXISTS reference (
    name text NOT NULL,
    pos  integer NOT NULL,
    row  jsonb NOT NULL,
    PRIMARY KEY (name, pos)
);

-- Accounts. Passwords are stored as salted scrypt hashes, sessions as the SHA-256 of a random token.
CREATE TABLE IF NOT EXISTS app_user (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username     text NOT NULL UNIQUE,
    pw_hash      text NOT NULL,
    role         text NOT NULL CHECK (role IN ('admin', 'manager')),
    failed       integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session (
    token_hash text PRIMARY KEY,
    user_id    integer NOT NULL REFERENCES app_user ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
