# ---------------------------------------------------------------------------
# Utils or Helpers
# ---------------------------------------------------------------------------

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import dateparser
import requests
from bs4 import BeautifulSoup
import logging
from typing import Optional 
import re
import time
from dataclasses import asdict
from .data_model import PropertyListing
# from data_model import PropertyListing
import os
import psycopg2
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Base Configuration
# ---------------------------------------------------------------------------

BASE_URL    = "https://belirumah.co/jual/rumah"
DETAIL_BASE = "https://belirumah.co"
DB_CONN  = os.environ["PROPERTY_DB_CONN"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://belirumah.co/",
    "Connection":      "keep-alive",
}

REQUEST_DELAY = 1.5   # polite delay between requests (seconds)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

def _get(url: str, session: requests.Session or bool, retries: int = 3) -> Optional[BeautifulSoup]:
    """GET a URL and return a parsed BeautifulSoup, or None on failure."""
    for attempt in range(1, retries + 1):
        try:
            if session:
                resp = session.get(url, headers=HEADERS, timeout=20)
                resp.raise_for_status()
                html = resp.text
            
            else:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, timeout=60000)
                    
                    try:
                        page.wait_for_selector('[class*="posted--at"]', timeout=15000)
                    except Exception:
                        print("The element took too long to load or didn't appear.")
                    
                    # Grab the finished HTML after the wait is done
                    html = page.content()
                    browser.close()

            # return BeautifulSoup(resp.text, "lxml")
            return BeautifulSoup(html, "lxml")
        
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(REQUEST_DELAY * attempt)
    logger.error("All retries exhausted for %s", url)
    return None


def _parse_price(raw: str) -> Optional[int]:
    """
    Convert Indonesian price strings to an integer (IDR).
      "Rp1,8 miliar"  → 1_800_000_000
      "Rp545 juta"    → 545_000_000
      "Rp850.000.000" → 850_000_000
    """
    if not raw:
        return None
    raw = raw.strip().replace("Rp", "").replace("\xa0", "").strip()

    miliar = re.search(r"([\d,\.]+)\s*miliar", raw, re.IGNORECASE)
    juta   = re.search(r"([\d,\.]+)\s*juta",   raw, re.IGNORECASE)
    if miliar:
        return int(float(miliar.group(1).replace(",", ".")) * 1_000_000_000)
    if juta:
        return int(float(juta.group(1).replace(",", ".")) * 1_000_000)

    plain = re.sub(r"\.", "", raw).replace(",", "")
    return int(plain) if plain.isdigit() else None


# ---------------------------------------------------------------------------
# Listing-page parser 
# ---------------------------------------------------------------------------

def _collect_cards(soup: BeautifulSoup):
    """
    Return a list of (anchor_tag, card_tag) pairs, one per unique listing.
    """
    anchors = soup.find_all("a", href=re.compile(r"^/properti/rumah/"))

    seen_ids: set[str] = set()
    cards = []

    for anchor in anchors:
        href = anchor.get("href", "")
        id_match = re.search(r"/(\d{6,})(?:/|$|\?)", href)
        if not id_match:
            continue
        prop_id = id_match.group(1)
        if prop_id in seen_ids:
            continue
        seen_ids.add(prop_id)
        card = anchor.parent

        cards.append((anchor, card, prop_id, href))

    return cards

def _parse_card(anchor, card, prop_id: str) -> PropertyListing:
    """Extract listing fields from a single card div."""
    prop = PropertyListing()
    prop.property_id = prop_id

    # Title lives inside the <a> tag (in an <h3>)
    h3 = anchor.find("h3")
    prop.property_name = h3.get_text(strip=True) if h3 else anchor.get_text(strip=True)

    # Location is an <h4> that is a sibling of the <a> inside the card
    h4 = card.find("h4")
    prop.location = h4.get_text(strip=True) if h4 else ""

    card_text = card.get_text(" ", strip=True)

    # Price
    price_match = re.search(r"Rp[\d\s,\.]+(?:miliar|juta)?", card_text, re.IGNORECASE)
    if price_match:
        prop.price = _parse_price(price_match.group())

    # Land area (LT) and building area (LB)
    lt = re.search(r"LT\s*[:\-]?\s*([\d,\.]+)\s*m", card_text, re.IGNORECASE)
    lb = re.search(r"LB\s*[:\-]?\s*([\d,\.]+)\s*m", card_text, re.IGNORECASE)
    if lt:
        prop.land_area_m2     = int(float(lt.group(1).replace(",", ".")))
    if lb:
        prop.building_area_m2 = int(float(lb.group(1).replace(",", ".")))

    # Bedrooms & bathrooms: two small digit-only spans appear in order KT, KM.
    # Exclude any number that is part of area/price text by scoping to short spans.
    digit_spans = [
        el.get_text(strip=True)
        for el in card.find_all(["span", "div", "p"])
        if re.fullmatch(r"\d{1,2}", el.get_text(strip=True))
    ]
    if len(digit_spans) >= 1:
        prop.bedrooms  = int(digit_spans[0])
    if len(digit_spans) >= 2:
        prop.bathrooms = int(digit_spans[1])
    
    # Try to extract a human-readable relative publish time from the card text,

    date_match = card.find(class_=re.compile(r"posted--at"))
    if date_match:
        relative_text = date_match.get_text(strip=True)
        relative_text = relative_text.split()[0]
        prop.date_published = str(dateparser.parse(relative_text))

    agent_name = card.find(class_=re.compile(r"agent--info-container"))
    if agent_name:
        prop.agent_name = agent_name.get_text(strip=True)

    return prop


# ---------------------------------------------------------------------------
# Detail-page parser
# ---------------------------------------------------------------------------

def _parse_detail(soup: BeautifulSoup, prop: PropertyListing) -> PropertyListing:
    """Enrich a listing with fields only present on the detail page."""
    text = soup.get_text(" ", strip=True)

    # Certificate
    cert = re.search(
        r"(?:Sertifikat|Certificate)[^\w]*:?\s*([A-Z]{2,10}(?:/[A-Z]{2,6})?)",
        text, re.IGNORECASE,
    )
    if cert:
        prop.certificate = cert.group(1).upper()
    else:
        for label in ("SHM", "HGB", "SHMSRS", "Girik", "Strata"):
            if re.search(rf"\b{label}\b", text, re.IGNORECASE):
                prop.certificate = label.upper()
                break

    # Hoek (corner lot)
    prop.hoek = bool(re.search(r"\bhoek\b", text, re.IGNORECASE))

    # Floors
    floors = re.search(
        r"(?:Lantai|Jumlah\s+Lantai|Floor)[^\d]*(\d+)", text, re.IGNORECASE
    )
    if floors:
        prop.floors = int(floors.group(1))

    # Electrical voltage
    volt = re.search(
        r"(?:Listrik|Daya|Electrical|Voltage)[^\d]*(\d{3,5})\s*(?:Watt|VA|W)?",
        text, re.IGNORECASE,
    )
    if volt:
        prop.electrical_voltage = int(volt.group(1))
    else:
        standalone = re.search(r"\b(\d{3,5})\s*(?:Watt|VA)\b", text, re.IGNORECASE)
        if standalone:
            prop.electrical_voltage = int(standalone.group(1))

    # Refine bedrooms / bathrooms from spec table (more reliable than card icons)
    kt = re.search(r"(?:Kamar\s*Tidur|Bedrooms?|KT)[^\d]*(\d{1,2})", text, re.IGNORECASE)
    km = re.search(r"(?:Kamar\s*Mandi|Bathrooms?|KM)[^\d]*(\d{1,2})", text, re.IGNORECASE)
    if kt:
        prop.bedrooms  = int(kt.group(1))
    if km:
        prop.bathrooms = int(km.group(1))

    # Refine areas
    lt = re.search(r"(?:Luas\s*Tanah|LT)[^\d]*(\d+)\s*m",    text, re.IGNORECASE)
    lb = re.search(r"(?:Luas\s*Bangunan|LB)[^\d]*(\d+)\s*m", text, re.IGNORECASE)
    if lt:
        prop.land_area_m2     = int(lt.group(1))
    if lb:
        prop.building_area_m2 = int(lb.group(1))

    return prop

# ---------------------------------------------------------------------------
# Database connect
# ---------------------------------------------------------------------------
def load_property_ids(db_conn: str = DB_CONN) -> set[str]:
    """Return the set of existing property IDs from Postgres."""

    collect_data_query = """
        SELECT DISTINCT property_id FROM property_listings;
    """

    try:
        conn = psycopg2.connect(db_conn)
    except psycopg2.OperationalError as exc:
        if "postgres-data" in db_conn:
            fallback_conn = db_conn.replace("postgres-data:5432", "localhost:5433")
            logger.warning(
                "DB host %s not reachable from this environment; trying fallback %s",
                "postgres-data",
                fallback_conn,
            )
            conn = psycopg2.connect(fallback_conn)
        else:
            raise

    try:
        with conn.cursor() as cur:
            logger.info("Connected to database, fetching existing property IDs...")
            cur.execute(collect_data_query)
            
            # Fetch all rows
            property_ids = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    return property_ids

# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

def scrape_belirumah(location: str, pages: int) -> list[dict]:
    """
    Scrape BeliRumah.co for house listings.

    Parameters
    ----------
    location : str  - city/area to search, e.g. "Bogor"
    pages    : int  - number of listing pages to scrape

    Returns
    -------
    list[dict] - one dict per unique listing
    """

    session  = requests.Session()
    results: list[PropertyListing] = []

    # Load existing property IDs to avoid duplicates in the database
    existing_ids = load_property_ids()

    for page_num in range(1, pages + 1):
        url = f"{BASE_URL}?page={page_num}&q={location.lower()}"
        logger.info("Fetching listing page %d → %s", page_num, url)

        soup = _get(url, session=False)
        # with open("debug.html", "w", encoding="utf-8") as f:
        #     f.write(soup.prettify())
        if soup is None:
            logger.error("Skipping page %d (fetch failed).", page_num)
            continue

        cards = _collect_cards(soup)
        if not cards:
            logger.warning("No property cards found on page %d.", page_num)
            continue

        logger.info("Found %d unique cards on page %d.", len(cards), page_num)

        for anchor, card, prop_id, href in cards:
            if prop_id in existing_ids:
                logger.info("Skipping existing property: %s", prop_id)
                continue

            prop = _parse_card(anchor, card, prop_id)

            # Fetch detail page for enriched fields
            detail_url = DETAIL_BASE + href
            logger.info("  → detail: %s", detail_url)
            time.sleep(REQUEST_DELAY)

            detail_soup = _get(detail_url, session=session)
            if detail_soup:
                prop = _parse_detail(detail_soup, prop)

            results.append(prop)

        time.sleep(REQUEST_DELAY)

    return [asdict(p) for p in results]