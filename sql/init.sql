CREATE TABLE IF NOT EXISTS property_listings (
    id                 SERIAL PRIMARY KEY,
    property_id        VARCHAR(20)  NOT NULL,
    scraped_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    property_name      TEXT,
    location           TEXT,
    price              BIGINT,
    land_area_m2       INT,
    building_area_m2   INT,
    certificate        VARCHAR(20),
    hoek               BOOLEAN      DEFAULT FALSE,
    bedrooms           INT,
    bathrooms          INT,
    floors             INT,
    electrical_voltage INT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_property_id_scraped_date
    ON property_listings(property_id, ((scraped_at AT TIME ZONE 'UTC')::DATE));

CREATE INDEX IF NOT EXISTS idx_property_id  ON property_listings(property_id);
CREATE INDEX IF NOT EXISTS idx_scraped_at   ON property_listings(scraped_at);
CREATE INDEX IF NOT EXISTS idx_location     ON property_listings(location);