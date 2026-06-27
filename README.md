# FlipBase

Personlig arbitrage-motor for FINN.no. Scraper nye annonser, beregner flip-verdi
mot egen referansedata, vurderer stand med Claude vision, og varsler via Telegram.

Ikke et kommersielt produkt. Et verktoy for a flippe fra 2000 kr og bygge seg opp.

## Stack
- Python 3.11
- FastAPI (API + manuelle triggers)
- Playwright (scraping)
- Supabase / Postgres (lagring + referansedata)
- Claude API (vision standvurdering)
- Telegram Bot API (varsling)
- Railway (hosting + cron)

## Kjernekonsept
Motoren filtrerer 500 annonser ned til de 5-10 som er priset riktig.
Du tar den endelige beslutningen (stand, selger, frakt vs henting).

## Moduler
| Modul | Ansvar |
|-------|--------|
| `scrapers/finn.py` | Henter nye annonser per watchlist |
| `pipeline/normalize.py` | Rådata til strukturert listing |
| `pipeline/pricing.py` | Referansepris + flip_score |
| `pipeline/sold_tracker.py` | Detekterer solgte annonser (forsvunnet = solgt) |
| `pipeline/liquidity.py` | Median dager-til-solgt per modell |
| `pipeline/redflags.py` | Tekst- og selgerheuristikk |
| `pipeline/vision.py` | Claude vision standvurdering |
| `notify/telegram.py` | Sender varsel |
| `scheduler.py` | Railway cron entrypoint |

## Oppsett
1. `pip install -r requirements.txt`
2. `playwright install chromium`
3. Kopier `.env.example` til `.env` og fyll inn
4. Kjor SQL i `sql/` mot Supabase
5. `python -m src.scheduler` (eller sett opp Railway cron)

## Byggerekkefolge
Se Notion-siden for full plan. Kort: scraper + lagring + sold-tracking forst,
deretter prismotor + Telegram, sa red-flags + vision, sa likviditetsvekting.
