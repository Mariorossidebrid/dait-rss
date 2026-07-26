#!/usr/bin/env python3
"""
generate_feed.py
-----------------
Scarica la pagina "Archivio delle notizie" di
https://dait.interno.gov.it/finanza-locale/notizie
estrae i comunicati/notizie ed elenca in docs/feed.xml (RSS 2.0).

Mantiene uno stato persistente (docs/items.json) con tutte le notizie
già viste, così il feed cresce nel tempo anche se il sito mostra solo
le ultime N notizie in home.

Pensato per girare via GitHub Actions (vedi .github/workflows/dait-rss.yml),
ma funziona identico in locale con: python scripts/generate_feed.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

BASE_URL = "https://dait.interno.gov.it"
LISTING_PATH = "/finanza-locale/notizie"
LISTING_URL = urljoin(BASE_URL, LISTING_PATH)

# Quante pagine di elenco leggere ad ogni esecuzione (0 = prima pagina).
# Leggerne un paio serve a non perdere notizie inserite "fuori ordine".
PAGES_TO_FETCH = 2

STATE_FILE = Path("docs/items.json")
FEED_FILE = Path("docs/feed.xml")
MAX_ITEMS_IN_FEED = 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL + "/finanza-locale",
}

MESI_ITA = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

DATE_IN_SLUG_RE = re.compile(
    r"(\d{1,2})[-\s](" + "|".join(MESI_ITA.keys()) + r")[-\s](\d{4})"
)


def fetch_html(url: str) -> str | None:
    """Scarica una pagina con header 'da browser'. Ritorna None se blocco/errore."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        print(f"[ERRORE] richiesta fallita per {url}: {exc}", file=sys.stderr)
        return None

    if resp.status_code != 200:
        print(
            f"[ERRORE] status {resp.status_code} per {url} "
            f"(possibile blocco anti-bot del sito)",
            file=sys.stderr,
        )
        return None

    # Il sito, quando blocca, spesso restituisce comunque 200 ma con una
    # pagina "Servizio sospeso" al posto del contenuto atteso.
    if "Servizio sospeso" in resp.text or "bloccata dai sistemi" in resp.text:
        print(
            f"[ERRORE] il sito ha risposto con una pagina di blocco per {url}",
            file=sys.stderr,
        )
        return None

    return resp.text


def parse_date_from_slug(url: str) -> datetime | None:
    """Prova a leggere una data tipo 'comunicato-del-14-luglio-2026' dallo slug URL."""
    m = DATE_IN_SLUG_RE.search(url.replace("_", "-"))
    if not m:
        return None
    day, month_name, year = m.groups()
    month = MESI_ITA.get(month_name.lower())
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day), 9, 0, tzinfo=timezone.utc)
    except ValueError:
        return None


def extract_items(html: str) -> list[dict]:
    """Estrae le notizie da una pagina di elenco.

    Il sito è basato su Drupal: si cercano i link che puntano a
    sotto-pagine di /finanza-locale/notizie/ (escludendo la paginazione
    e la pagina indice stessa), che è il pattern osservato per i
    singoli comunicati.
    """
    soup = BeautifulSoup(html, "lxml")
    items: dict[str, dict] = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/finanza-locale/notizie/" not in href:
            continue
        if href.rstrip("/").endswith("/finanza-locale/notizie"):
            continue

        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        full_url = urljoin(BASE_URL, href)

        # Evita di catturare due volte lo stesso link con testo diverso
        # (es. link "immagine" + link "titolo" sulla stessa card).
        if full_url in items and len(items[full_url]["title"]) >= len(title):
            continue

        items[full_url] = {"title": title, "link": full_url}

    return list(items.values())


def load_state() -> dict[str, dict]:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return {it["link"]: it for it in data}
        except (json.JSONDecodeError, KeyError):
            print("[AVVISO] items.json illeggibile, riparto da zero", file=sys.stderr)
    return {}


def save_state(items_by_link: dict[str, dict]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(
        items_by_link.values(), key=lambda it: it["pubDate"], reverse=True
    )
    STATE_FILE.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_feed(items: list[dict]) -> None:
    fg = FeedGenerator()
    fg.title("DAIT — Finanza locale — Notizie")
    fg.link(href=LISTING_URL, rel="alternate")
    fg.link(href="https://example.invalid/feed.xml", rel="self")
    fg.description(
        "Feed RSS non ufficiale delle notizie pubblicate su "
        "dait.interno.gov.it/finanza-locale/notizie"
    )
    fg.language("it")

    for it in items[:MAX_ITEMS_IN_FEED]:
        fe = fg.add_entry()
        fe.id(it["link"])
        fe.title(it["title"])
        fe.link(href=it["link"])
        pub = datetime.fromisoformat(it["pubDate"])
        fe.pubDate(pub)

    FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    fg.rss_file(str(FEED_FILE), pretty=True)


def main() -> int:
    known = load_state()
    new_count = 0
    any_page_ok = False

    for page in range(PAGES_TO_FETCH):
        url = LISTING_URL if page == 0 else f"{LISTING_URL}?page={page}"
        html = fetch_html(url)
        if html is None:
            continue
        any_page_ok = True

        for it in extract_items(html):
            if it["link"] in known:
                continue
            pub_date = parse_date_from_slug(it["link"]) or datetime.now(timezone.utc)
            known[it["link"]] = {
                "title": it["title"],
                "link": it["link"],
                "pubDate": pub_date.isoformat(),
            }
            new_count += 1

    if not any_page_ok:
        print(
            "[FATALE] nessuna pagina è stata scaricata correttamente: "
            "il sito ha probabilmente bloccato la richiesta.",
            file=sys.stderr,
        )
        # Se avevamo già uno stato precedente, rigenera comunque il feed
        # da quello (il feed resta valido/consultabile), ma fai fallire
        # il job così te ne accorgi nei log di GitHub Actions.
        if known:
            save_state(known)
            build_feed(sorted(known.values(), key=lambda it: it["pubDate"], reverse=True))
        return 1

    save_state(known)
    build_feed(sorted(known.values(), key=lambda it: it["pubDate"], reverse=True))
    print(f"OK: {new_count} nuove notizie, {len(known)} totali nel feed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
