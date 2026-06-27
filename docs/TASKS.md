# FlipBase byggeplan

Sekvensert oppgaveliste for Claude Code. Bygg i rekkefolge. Hver milepael har
akseptansekriterier som ma vaere oppfylt for du gaar videre. Ikke hopp fremover.

Status pr modul: skjelett finnes, men selektorer/integrasjoner er plassholdere
som ma fullfores og verifiseres mot live tjenester.

---

## M1 — Scraper + lagring (iPhone)

Maal: en kategori ende til ende, data lander i Supabase.

- [ ] Sett opp Supabase-prosjekt, kjor `sql/001_init.sql` + `sql/002_indexes.sql`.
- [ ] Fyll inn `.env` (Supabase URL + service key).
- [ ] Verifiser FINN-selektorene i `scrapers/finn.py` mot live HTML for iPhone-sok.
- [ ] Utvid scraperen til a aapne detaljsiden og hente beskrivelse + bilde-URLer.
- [ ] Koble `normalize.py` -> `repository.upsert_listing`.
- [ ] Kjor `python -m src.scheduler` med kun iPhone-watchlist.

Akseptanse: nye iPhone-annonser dukker opp i `listings`-tabellen med korrekt
`model_key`, pris og bilder. Re-kjoring lager ikke duplikater (upsert virker).

---

## M2 — Sold-tracking

Maal: forsvunne annonser markeres, prisdata begynner a akkumulere.

- [ ] Implementer reconcile-steget skikkelig i `scheduler._reconcile_sold`.
- [ ] Bruk `sold_tracker.classify_disappeared` per rad (solgt vs fjernet) basert
      paa `first_seen`/`last_seen` fra DB.
- [ ] Sett `sold_at` naar status blir `sold`.

Akseptanse: en iPhone-annonse som forsvinner fra FINN faar status `sold` med
`sold_at` satt, og prisen telles med i referanseutvalget.

---

## M3 — Prismotor + Telegram

Maal: forste reelle flip-varsel.

- [ ] Sett opp Telegram-bot, fyll inn token + chat_id i `.env`.
- [ ] Verifiser `pricing.compute_flip_score` mot ekte tall.
- [ ] Bekreft fallback-logikken (statisk til egen median er tykk nok).
- [ ] Send testvarsel via `notify.telegram.send`.
- [ ] Koble inn `alerts_sent` sa ingen annonse varsles to ganger.

Akseptanse: en feilpriset iPhone over terskel utloser et Telegram-varsel med
pris, estimert salg, margin og lenke. Samme annonse varsles ikke paa nytt.

---

## M4 — Red-flags

Maal: varsler hjelper deg prioritere.

- [ ] Bekreft at `redflags.detect` kjorer paa hver kandidat.
- [ ] Verifiser at flaggene rendres riktig i Telegram-varselet.

Akseptanse: et varsel for en annonse med tynn beskrivelse + ny selger viser de
korrekte advarslene.

---

## M5 — Vision

Maal: AI forhaandssorterer stand.

- [ ] Fyll inn `ANTHROPIC_API_KEY`.
- [ ] Bekreft bildenedlasting + base64 i `vision.assess`.
- [ ] Verifiser at `VISION_MAX_PER_RUN` respekteres.
- [ ] Sjekk at JSON-parsing taaler rotete svar.

Akseptanse: et varsel inneholder en standkarakter 1-10 + synlige skader, og
vision kjorer ikke paa flere annonser enn budsjettet per kjoring.

---

## M6 — Likviditetsvekting

Maal: raske flips prioriteres naar nok sold-data finnes.

- [ ] Bekreft `repository.sold_durations` returnerer rett dager-til-solgt.
- [ ] Verifiser `liquidity.adjusted_score` paavirker terskelbeslutningen.

Akseptanse: to like marginer rangeres ulikt naar den ene modellen selger
raskere, og det vises i varselet.

---

## M7 — Utvid kategorier

Maal: gaming + kamera inn.

- [ ] Legg til watchlists for PS5, Switch, Sony-kamera.
- [ ] Verifiser `model_key`-monstre for de nye kategoriene i `normalize.py`.
- [ ] Juster fraktmatrisen i `pricing.py` ved behov.

Akseptanse: motoren varsler korrekt for alle tre kategoriene uten falske
model_key-sammenslaainger.

---

## Deploy

- [ ] Push til GitHub.
- [ ] Koble repo til Railway. Web-tjeneste (uvicorn) + cron-tjeneste (`*/7 * * * *`).
- [ ] Sett env vars i Railway.
- [ ] Verifiser at cron kjorer og varsler kommer.

---

## Fase 2 (ikke naa)

Cross-platform (Tise/FB via ny scraper paa `BaseScraper`), web-dashboard,
DB-styrte watchlists, per-rad sold-klassifisering, auto-annonseutkast.
