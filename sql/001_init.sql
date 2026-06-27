-- FlipBase datamodell (Supabase / Postgres)
-- Kjor i Supabase SQL editor.

-- =========================================================
-- listings: hver annonse vi har sett, med all raadata.
-- Hjertet i systemet. Sold-tracking bygger paa denne.
-- =========================================================
create table if not exists listings (
    id                   bigint generated always as identity primary key,
    source               text        not null default 'finn',
    external_id          text        not null,
    category             text        not null,
    model_key            text        not null,
    title                text        not null,
    price                integer     not null,
    description          text        default '',
    image_urls           jsonb       default '[]'::jsonb,
    location             text        default '',
    distance_km          numeric,
    seller_name          text        default '',
    seller_listing_count integer,
    posted_at            timestamptz,
    url                  text        not null,
    status               text        not null default 'active',  -- active | sold | removed
    first_seen           timestamptz not null default now(),
    last_seen            timestamptz not null default now(),
    sold_at              timestamptz,
    unique (source, external_id)
);

-- =========================================================
-- reference_prices: cachet median/snitt per model_key.
-- Kan regnes paa sparken fra listings, men caches for fart.
-- =========================================================
create table if not exists reference_prices (
    model_key            text        primary key,
    median_sold_price    integer,
    sample_size          integer     not null default 0,
    median_days_to_sold  numeric,
    static_fallback      integer,
    updated_at           timestamptz not null default now()
);

-- =========================================================
-- alerts_sent: hva du allerede er varslet om (unngaa spam).
-- =========================================================
create table if not exists alerts_sent (
    id          bigint generated always as identity primary key,
    source      text        not null,
    external_id text        not null,
    flip_score  numeric     not null,
    sent_at     timestamptz not null default now(),
    unique (source, external_id)
);

-- =========================================================
-- watchlists: dine kategorier, sokefiltre og terskler.
-- Kan styres herfra istedenfor i kode naar du vil.
-- =========================================================
create table if not exists watchlists (
    id                   bigint generated always as identity primary key,
    category             text        not null,
    query                text        not null,
    flip_score_threshold numeric     not null default 0.30,
    active               boolean     not null default true,
    created_at           timestamptz not null default now()
);

-- =========================================================
-- flips: faktiske kjop og salg du gjor (manuell logg).
-- Lar deg male reell ROI vs motorens estimater over tid.
-- =========================================================
create table if not exists flips (
    id            bigint generated always as identity primary key,
    listing_url   text,
    model_key     text,
    buy_price     integer     not null,
    sell_price    integer,
    shipping_cost integer     default 0,
    bought_at     timestamptz not null default now(),
    sold_at       timestamptz,
    notes         text,
    realized_margin integer generated always as (
        coalesce(sell_price, 0) - buy_price - coalesce(shipping_cost, 0)
    ) stored
);
