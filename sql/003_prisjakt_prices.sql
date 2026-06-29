-- Prisjakt ny-priser, cachet per modell.
-- Kjores sjelden (daglig/ukentlig). Brukes som fallback naar vi mangler
-- nok egne FINN-salgdata til aa beregne referansepris.

create table if not exists prisjakt_prices (
    model_key       text        primary key,
    new_price_nok   integer     not null,
    fetched_at      timestamptz not null default now()
);
