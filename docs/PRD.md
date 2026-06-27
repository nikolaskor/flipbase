# FlipBase PRD

Kravspesifikasjon for FlipBase. Skrevet for at en Claude Code-agent skal kunne
bygge prosjektet selvstendig. Komplement til `CLAUDE.md` (operativguide) og
`docs/TASKS.md` (byggeplan).

## 1. Problem

A finne lonnsomme flip-muligheter paa FINN.no krever a scrolle hundrevis av
annonser manuelt for a fange de faa som er feilpriset. Det er tregt, og de beste
dealene forsvinner i lopet av minutter. Uten egen prisdata er det dessuten
vanskelig a vite hva ting faktisk selges for.

## 2. Maal

Bygge en motor som filtrerer dagens annonsestrom ned til de faa som er priset
lavt nok til lonnsom flip, og varsler eieren innen minutter. Eieren starter med
2000 kr kapital og bygger seg opp gjennom gjentatte flips. Motoren gjor research,
eieren tar beslutninger og haandterer logistikk.

## 3. Ikke-maal

- Ikke et kommersielt produkt. Ingen andre brukere, ingen SaaS, ingen betaling.
- Ikke full automasjon. Stand- og selgervurdering forblir manuell.
- Ikke listing-automasjon. Eier eier varen fysisk for salg (FINN-regel).
- Ingen frontend i fase 1. Telegram er grensesnittet.

## 4. Bruker

En person: eieren. Mottar varsler paa Telegram, aapner kandidatene, kjoper,
selger. Bruker ca 20 min/dag aktivt.

## 5. Funksjonelle krav

**FR1 Scraping.** Hent nye annonser per kategori-watchlist fra FINN med jevne
intervaller. Parse tittel, pris, beskrivelse, bilde-URLer, sted, selger, timestamp,
ekstern ID. Dedupliser mot lagret data.

**FR2 Normalisering.** Gjor raa annonse om til strukturert `Listing` med en stabil
`model_key` som grupperer samme produkt paa tvers av ulik tittelskriving.

**FR3 Sold-tracking.** Sammenlign hver kjoring mot forrige. Annonse som var aktiv
og naa er borte markeres som solgt til sin siste kjente pris. Bygger proprietaer
prisdatabase over tid.

**FR4 Prismotor.** Beregn referansepris (median av egne solgte + statisk fallback).
Beregn `flip_score = (estimert_salg - kjopspris - frakt) / kjopspris`. Juster for
fraktkostnad per kategori.

**FR5 Likviditet.** Beregn median dager-til-solgt per `model_key`. Vekt flip_score
mot omlopshastighet (raske flips loftes, trege straffes).

**FR6 Red-flags.** Flagg faa bilder, manglende skjermomtale, kort beskrivelse, ny
selger, skadeord i tekst. Vises i varselet for prioritering.

**FR7 Vision.** Send annonsebilder til Claude for standkarakter 1-10 + synlige
skader. Kjores bare paa kandidater over pristerskelen, innenfor budsjett per kjoring.

**FR8 Varsling.** Send ferdig flip-varsel til Telegram med pris, estimert salg,
margin, likviditet, sted/frakt, vision-vurdering, red-flags og lenke. Ingen
duplikatvarsler for samme annonse.

**FR9 Manuell flip-logg.** Tabell for faktiske kjop/salg eieren gjor, for a maale
reell ROI mot motorens estimater.

## 6. Datamodell

| Tabell | Ansvar |
| --- | --- |
| listings | Hver annonse sett, all raadata + timestamps. Grunnlag for sold-tracking. |
| reference_prices | Cachet median + dager-til-solgt per model_key. |
| alerts_sent | Anti-duplikat for varsler. |
| watchlists | Kategorier, sokefiltre, terskler. |
| flips | Manuell logg over reelle kjop/salg, reell margin. |

Full DDL i `sql/001_init.sql`.

## 7. Kategorier (fase 1)

Elektronikk (iPhone, AirPods, iPad), gaming (PS5, Switch, utstyr), kamera (Sony,
Canon, Fujifilm). Start med iPhone alene i M1.

## 8. Constraints

- **FINN ToS:** scraping ikke tillatt, anti-bot finnes. Lavt volum, mykt feil.
- **Eierskap:** annonsering av varer man ikke fysisk eier er forbudt paa FINN.
- **Vision-kost:** budsjetteres per kjoring.

## 9. Suksesskriterier

- Motoren leverer minst en reell, lonnsom flip-mulighet eieren ellers ville
  gaatt glipp av, per uke.
- Varsel naar eieren innen faa minutter etter at annonsen er publisert.
- Sold-tracking har nok data til at egen median erstatter statisk fallback for
  de viktigste modellene innen noen uker.
- Eieren tjener faktiske penger paa flips startet fra 2000 kr.

## 10. Fase 2

Cross-platform spread (Tise/Facebook Marketplace), web-dashboard for historikk/ROI,
watchlist-styring fra DB, per-rad sold-klassifisering, auto-utkast til salgsannonse.
Arkitekturen er allerede forberedt: `scrapers/base.py` er abstrakt for nye kilder.
