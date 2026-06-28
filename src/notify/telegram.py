"""Telegram-varsling. Bygger og sender det ferdige flip-varselet."""
from __future__ import annotations

import html

import httpx

from src.config import settings
from src.models.schemas import FlipOpportunity

_API = "https://api.telegram.org/bot{token}/sendMessage"

_SEV_MARK = {"info": "ℹ️", "warn": "⚠️", "high": "🔴"}


def _kr(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " kr"


def format_alert(opp: FlipOpportunity) -> str:
    """HTML-formatert varsel (parse_mode=HTML). Escaper tittel og beskrivelse."""
    l = opp.listing
    pct = round(opp.flip_score * 100)
    title = html.escape(l.title)

    lines = [
        "🟢 <b>FLIP-MULIGHET</b>",
        "",
        f"📦 {title}",
        f"💰 Pris: {_kr(l.price)}",
        f"📊 Estimert salg: {_kr(opp.estimated_sell_price)}",
        f"📈 Margin: ~{_kr(opp.net_margin)} ({pct}%)",
    ]

    if opp.median_days_to_sold is not None:
        lines.append(f"⚡ Selger typisk paa {opp.median_days_to_sold} dager")

    loc = html.escape(l.location or "ukjent")
    dist = f" ({round(l.distance_km)} km)" if l.distance_km is not None else ""
    lines.append(f"📍 {loc}{dist}, frakt: {_kr(opp.shipping_cost)}")

    if opp.vision:
        v = opp.vision
        lines.append(f"👁 Stand (AI): {v.condition_score}/10, {html.escape(v.summary)}")
        if v.visible_damage:
            lines.append("   " + "; ".join(html.escape(d) for d in v.visible_damage))

    if opp.red_flags:
        lines.append("")
        for flag in opp.red_flags:
            mark = _SEV_MARK.get(flag.severity, "⚠️")
            lines.append(f"{mark} {html.escape(flag.label)}")

    lines += ["", f'🔗 <a href="{l.url}">{title}</a>']
    return "\n".join(lines)


async def send(opp: FlipOpportunity) -> bool:
    text = format_alert(opp)
    url = _API.format(token=settings.telegram_bot_token)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={
            "chat_id": settings.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        return r.status_code == 200
