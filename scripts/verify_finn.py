"""Verifiser FINN-selektorene mot live HTML, og eventuelt land data i Supabase.

Kjor dette der FINN faktisk er naabar (lokalt). Det er M1-broen: bekreft at
parseren henter rett data ut av ekte HTML, og at nye annonser lander i
`listings`. Holder seg til en enkelt kjoring (lavt volum, ToS).

Bruk:
    python -m scripts.verify_finn                 # last iPhone-sok, skriv ut treff
    python -m scripts.verify_finn --dump          # lagre HTML for selektor-revisjon
    python -m scripts.verify_finn --supabase      # normaliser + upsert til Supabase
    python -m scripts.verify_finn -q "iphone 13" --limit 5 --headed

Krever `playwright install chromium` lokalt. --supabase krever utfylt .env
(SUPABASE_URL + SUPABASE_SERVICE_KEY).
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from src.models.schemas import Category
from src.scrapers.finn import (
    FinnScraper,
    SEL_AD_LINK,
    USER_AGENT,
)


async def _dump_html(scraper: FinnScraper, query: str, out_dir: Path) -> None:
    """Lagrer sok-HTML + forste detaljside-HTML for manuell selektor-revisjon."""
    from playwright.async_api import async_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    url = scraper._build_url({"query": query})

    async with async_playwright() as p:
        kwargs = {"headless": scraper.headless}
        if scraper.executable_path:
            kwargs["executable_path"] = scraper.executable_path
        browser = await p.chromium.launch(**kwargs)
        context = await browser.new_context(user_agent=USER_AGENT, locale="nb-NO")
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_selector(SEL_AD_LINK, timeout=10_000)
        except Exception:
            pass
        (out_dir / "search.html").write_text(await page.content(), encoding="utf-8")
        print(f"  lagret {out_dir / 'search.html'}")

        link = await page.query_selector(SEL_AD_LINK)
        if link:
            href = await link.get_attribute("href")
            await page.goto(scraper._abs_url(href), wait_until="domcontentloaded", timeout=30_000)
            (out_dir / "detail.html").write_text(await page.content(), encoding="utf-8")
            print(f"  lagret {out_dir / 'detail.html'}")
        await browser.close()


async def run(args: argparse.Namespace) -> int:
    scraper = FinnScraper(headless=not args.headed, detail_limit=args.limit)

    if args.dump:
        print("Dumper live HTML ...")
        await _dump_html(scraper, args.query, Path(args.dump_dir))

    print(f"Henter FINN-sok: q={args.query!r} (detail_limit={args.limit}) ...")
    raw_list = await scraper.fetch_new(Category.PHONE, {"query": args.query})
    print(f"Fant {len(raw_list)} annonser.\n")

    for raw in raw_list[: args.show]:
        price = f"{raw.price} kr" if raw.price is not None else "ingen pris"
        print(f"  [{raw.external_id}] {raw.title[:55]:55} {price:>12}  imgs={len(raw.image_urls)}")
        if raw.description:
            print(f"      desc: {raw.description[:90]}")
        print(f"      {raw.url}")

    if not args.supabase:
        return 0

    # Normaliser + upsert. Importeres her sa --dump/print virker uten Supabase-config.
    from src.db import repository as repo
    from src.pipeline.normalize import normalize

    stored = skipped = 0
    for raw in raw_list:
        listing = normalize(raw, Category.PHONE)
        if listing is None:
            skipped += 1
            continue
        try:
            repo.upsert_listing(listing)
            stored += 1
        except Exception as e:  # noqa: BLE001
            print(f"  upsert feilet for {raw.external_id}: {e}")
    print(f"\nSupabase: upsertet {stored}, hoppet over {skipped} (manglet pris).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifiser FINN-scraper mot live HTML.")
    parser.add_argument("-q", "--query", default="iphone", help="sokeord (default: iphone)")
    parser.add_argument("--limit", type=int, default=5, help="maks detaljsider a aapne")
    parser.add_argument("--show", type=int, default=20, help="antall treff a skrive ut")
    parser.add_argument("--dump", action="store_true", help="lagre live HTML for revisjon")
    parser.add_argument("--dump-dir", default="scratch/finn_dump", help="hvor HTML lagres")
    parser.add_argument("--supabase", action="store_true", help="normaliser + upsert til Supabase")
    parser.add_argument("--headed", action="store_true", help="vis nettleseren (debug)")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
