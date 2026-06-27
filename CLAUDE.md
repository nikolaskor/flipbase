# CLAUDE.md

Operativguide for Claude Code paa FlipBase. Les denne forst. Les `docs/PRD.md`
for hva som skal bygges og hvorfor, og `docs/TASKS.md` for rekkefolgen.

## Hva dette er

Personlig arbitrage-motor for FINN.no. Scraper nye annonser, beregner flip-verdi
mot egen referansedata, vurderer stand med Claude vision, varsler via Telegram.
Eier (Nikolai) flipper fra 2000 kr og bygger seg opp. Ikke et kommersielt produkt.

## Stack

Python 3.11, FastAPI, Playwright, Supabase/Postgres, Claude API (Sonnet for vision),
Telegram Bot API, Railway (hosting + cron).

## Dev-oppsett

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env        # fyll inn nokler
# kjor SQL i sql/ mot Supabase (001_init.sql, deretter 002_indexes.sql)
python -m src.scheduler     # en full syklus
uvicorn src.main:app --reload   # API lokalt
```

## Prosjektstruktur

```
src/
  config.py            pydantic settings (leser .env)
  main.py              FastAPI: /health, /run
  scheduler.py         orchestrator, binder hele pipelinen
  scrapers/
    base.py            abstrakt BaseScraper (Tise/FB dropper inn i fase 2)
    finn.py            Playwright FINN-scraper
  pipeline/
    normalize.py       raadata -> Listing + stabil model_key
    pricing.py         referansepris + flip_score + frakt
    sold_tracker.py    forsvunnet annonse = antatt solgt
    liquidity.py       median dager-til-solgt, vekter raske flips
    redflags.py        tekst/selger-heuristikk
    vision.py          Claude standvurdering fra bilder
  notify/telegram.py   bygger og sender varsel
  db/
    client.py          supabase singleton
    repository.py      alle DB-sporringer
  models/schemas.py    pydantic-modeller gjennom pipelinen
sql/                   tabeller + indekser
```

## Konvensjoner

- Ren, lesbar Python. Type hints overalt. Pydantic for datastrukturer.
- En modul, ett ansvar. Ikke bland scraping, prislogikk og varsling.
- Pipelinen er kildeagnostisk: alt etter scraperen jobber paa `Listing`, ikke raa FINN-data.
- Feil i en enkelt annonse skal aldri rive hele kjoringen. Fang og fortsett.
- Ingen hemmeligheter i koden. Alt sensitivt via `.env` / Railway env vars.
- Skriv en kort test for ny prislogikk for du gaar videre.

## Harde regler (ikke bryt disse)

1. **Eierskap for listing.** FINN forbyr a annonsere varer man ikke fysisk eier.
   Modellen er ALLTID kjop forst, selg etterpaa. Bygg aldri funksjonalitet som
   lister noe eieren ikke har i haanda.
2. **Respekter FINN ToS.** Scraping er ikke tillatt og de har anti-bot. Hold
   volumet lavt, realistiske intervaller (default 7 min), feil mykt. Ikke hamre
   serveren. Scraperen skal vaere lett a bytte ut uten a rive resten.
3. **Vision koster penger.** Kjor bare Claude vision paa annonser som allerede
   passerte pristerskelen. Respekter `VISION_MAX_PER_RUN`.
4. **Sold-tracking fra dag en.** Selv for prislogikken bruker dataen: logg hver
   annonse og marker forsvunne som solgt. Denne dataen er motorens egentlige verdi.

## Tekst i varsler og dokumenter

Aldri bruk em-dash. Bruk komma, punktum, kolon eller parentes. Kort, direkte tone.

## Hvor du starter

Foelg `docs/TASKS.md` i rekkefolge. M1 forst (scraper + lagring for iPhone),
ikke hopp til vision eller likviditet for grunnmuren staar. Verifiser FINN-
selektorene i `scrapers/finn.py` mot live HTML, de er plassholdere.
