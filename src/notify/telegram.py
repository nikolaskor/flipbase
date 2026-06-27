"""Telegram-varsling. Bygger og sender det ferdige flip-varselet."""
from __future__ import annotations

import httpx

from src.config import settings
from src.models.schemas import FlipOpportunity

_API = "https://api.telegram.org/bot{token}/sendMessage"


def format_alert(opp: FlipOpportunity) -> str:
    l = opp.listing
    pct = round(opp.flip_score * 100)

    lines = [
        "🟢 *FLIP-MULIGHET*",
        "",
        f"📦 {l.title}",
        f"💰 Pris: {l.price:,} kr".replace(",", " "),
        f"📊 Estimert salg: {opp.estimated_sell_price:,} kr".replace(",", " "),
        f"📈 Margin: ~{opp.net_margin:,} kr ({pct}%)".replace(",", " "),
    ]

    if opp.median_days_to_sold is not None:
        lines.append(f"⚡ Selger typisk paa {opp.median_days_to_sold} dager")

    loc = l.location or "ukjent"
    dist = f" ({round(l.distance_km)} km)" if l.distance_km is not None else ""
    lines.append(f"📍 {loc}{dist} — Frakt: {opp.shipping_cost} kr")

    if opp.vision:
        v = opp.vision
        lines.append(f"👁️ Stand (AI): {v.condition_score}/10 — {v.summary}")
        if v.visible_damage:
            lines.append("   " + "; ".join(v.visible_damage))

    if opp.red_flags:
        lines.append("")
        for f in opp.red_flags:
            mark = {"info": "ℹ️", "warn": "⚠️", "high": "🔴"}.get(f.severity, "⚠️")
            lines.append(f"{mark} {f.label}")

    lines.append("")
    lines.append(f"🔗 {l.url}")
    return "\n".join(lines)


async def send(opp: FlipOpportunity) -> bool:
    text = format_alert(opp)
    url = _API.format(token=settings.telegram_bot_token)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={
            "chat_id": settings.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        })
        return r.status_code == 200
