-- Indekser for ytelse paa de hyppigste sporringene.

-- Sold-tracking og referansepris slaar opp paa model_key + status.
create index if not exists idx_listings_model_status
    on listings (model_key, status);

-- Reconcile-steget henter aktive annonser per source + kategori.
create index if not exists idx_listings_source_cat_status
    on listings (source, category, status);

-- Rask dedup-oppslag.
create index if not exists idx_listings_source_extid
    on listings (source, external_id);

-- Likviditet: dager-til-solgt regnes fra solgte annonser.
create index if not exists idx_listings_sold
    on listings (model_key, sold_at)
    where status = 'sold';
