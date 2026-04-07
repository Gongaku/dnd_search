"""Web scraper for dnd5e.wikidot.com."""

import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

from dnd_search import cache
from dnd_search.models import DnDClass, Feat, Item, Race, Spell, Subclass

logger = logging.getLogger(__name__)

BASE_URL = "https://dnd5e.wikidot.com"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "dnd-search-cli/0.1 (educational tool)"})

_LEVEL_MAP = {
    "cantrip": 0,
    "1st level": 1,
    "2nd level": 2,
    "3rd level": 3,
    "4th level": 4,
    "5th level": 5,
    "6th level": 6,
    "7th level": 7,
    "8th level": 8,
    "9th level": 9,
}


def _fetch(url: str, use_cache: bool = True) -> BeautifulSoup:
    if use_cache:
        cached = cache.get(url)
        if cached:
            return BeautifulSoup(cached, "lxml")

    logger.info(f"Fetching {url}")
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e

    logger.debug(f"Response {resp.status_code} ({len(resp.text)} bytes)")
    if use_cache:
        cache.set(url, resp.text)
    return BeautifulSoup(resp.text, "lxml")


def _main_content(soup: BeautifulSoup) -> Tag | None:
    return soup.find("div", id="page-content") or soup.find(
        "div", class_="page-content"
    )


def _text(tag: Tag | None) -> str:
    if tag is None:
        return ""
    return re.sub(r" {2,}", " ", tag.get_text(separator=" ", strip=True))


def _parse_granted_spells(table: Tag) -> list[dict[str, str]] | None:
    """Parse a granted-spells table (e.g. Oath Spells, Expanded Spell List).
    Returns a list of {"level": str, "spells": str} dicts, or None if the
    table doesn't look like a spell list."""
    rows = table.find_all("tr")
    if not rows:
        return None

    # Find the actual column-header row: the first row with 2+ cells that
    # contains "spell" across its cells. Skip colspan title rows.
    header_row_idx = None
    headers: list[str] = []
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        hdrs = [_text(c).lower() for c in cells]
        if any("spell" in h for h in hdrs):
            header_row_idx = i
            headers = hdrs
            break

    if header_row_idx is None:
        return None

    # Prefer a column with "level" but NOT "spell" (avoids "Spell Level" matching both)
    level_col = next(
        (i for i, h in enumerate(headers) if "level" in h and "spell" not in h),
        next((i for i, h in enumerate(headers) if "level" in h), 0),
    )
    spell_col = next(
        (i for i, h in enumerate(headers) if "spell" in h and "level" not in h),
        next((i for i, h in enumerate(headers) if "spell" in h), 1),
    )
    entries = []
    for row in rows[header_row_idx + 1 :]:
        cells = row.find_all(["td", "th"])
        if len(cells) <= max(level_col, spell_col):
            continue
        lvl = _text(cells[level_col])
        spells = _text(cells[spell_col])
        if lvl and spells:
            entries.append({"level": lvl, "spells": spells})
    return entries or None


def _para_md(el) -> str:
    """Render element content as markdown, converting <a> tags to [text](url) links."""
    parts = []
    for child in el.children:
        if getattr(child, "name", None) == "a":
            href = str(child.get("href", ""))
            link_text = re.sub(r" {2,}", " ", child.get_text(separator=" ", strip=True))
            if href.startswith("/"):
                href = BASE_URL + href
            parts.append(f"[{link_text}]({href})" if link_text else "")
        elif hasattr(child, "get_text"):
            parts.append(child.get_text(separator=" "))
        else:
            parts.append(str(child))
    return re.sub(r" {2,}", " ", "".join(parts).strip())


def _href(tag: Tag | None) -> str:
    if tag is None:
        return ""
    return f"""{BASE_URL}{str(tag.get("href", ""))}"""


# ---------------------------------------------------------------------------
# Spells
# ---------------------------------------------------------------------------


def _parse_spell_table(table: Tag, level: int) -> list[Spell]:
    rows = table.find_all("tr")
    if not rows:
        return []

    header_row = rows[0]
    headers = [
        th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])
    ]
    if not any(h in ("name", "spell name") for h in headers):
        return []

    col = {
        "name": next((i for i, h in enumerate(headers) if "name" in h), 0),
        "school": next((i for i, h in enumerate(headers) if "school" in h), 1),
        "casting_time": next((i for i, h in enumerate(headers) if "casting" in h), 2),
        "range": next((i for i, h in enumerate(headers) if "range" in h), 3),
        "duration": next((i for i, h in enumerate(headers) if "duration" in h), 4),
        "components": next((i for i, h in enumerate(headers) if "component" in h), 5),
    }

    spells = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        name_cell = cells[col["name"]]
        link = name_cell.find("a")
        name = _text(name_cell)
        url = _href(link) if link else ""

        school = re.sub(
            r"\s*DC\b.*$",
            "",
            _text(cells[col["school"]]) if col["school"] < len(cells) else "",
            flags=re.I,
        ).strip()
        casting_time = (
            _text(cells[col["casting_time"]])
            if col["casting_time"] < len(cells)
            else ""
        )
        rng = _text(cells[col["range"]]) if col["range"] < len(cells) else ""
        duration = _text(cells[col["duration"]]) if col["duration"] < len(cells) else ""
        components = (
            _text(cells[col["components"]]) if col["components"] < len(cells) else ""
        )

        # Ritual spells are marked with a trailing "R" on the casting time (e.g. "1 MinuteR")
        ritual = casting_time.endswith("R") or "(ritual)" in name.lower()
        if casting_time.endswith("R"):
            casting_time = casting_time[:-1].strip()
        concentration = "concentration" in duration.lower()

        if name:
            spells.append(
                Spell(
                    name=name.replace(" (ritual)", "").strip(),
                    url=url,
                    level=level,
                    school=school,
                    casting_time=casting_time,
                    range=rng,
                    duration=duration,
                    components=components,
                    ritual=ritual,
                    concentration=concentration,
                )
            )
    return spells


def fetch_spells(use_cache: bool = True) -> list[Spell]:
    soup = _fetch(f"{BASE_URL}/spells", use_cache)
    content = _main_content(soup)
    if content is None:
        logger.warning("Could not find page content on spells page")
        return []

    spells: list[Spell] = []

    # The spells page uses a YUI tab widget; each tab panel = one spell level.
    # Tab order: Cantrip(0), 1st(1), 2nd(2), ... 9th(9)
    navset = content.find("div", class_="yui-navset")
    if navset:
        yui_content = navset.find("div", class_="yui-content")
        panels = yui_content.find_all("div", recursive=False) if yui_content else []
        for level, panel in enumerate(panels):
            for table in panel.find_all("table"):
                spells.extend(_parse_spell_table(table, level))
        logger.info(f"Fetched {len(spells)} spells from YUI tabs")
        return spells

    # Fallback: h2/h3 level headings followed by tables
    current_level = 0
    for element in content.find_all(["h2", "h3", "table"]):
        if element.name in ("h2", "h3"):
            heading = element.get_text(strip=True).lower().replace("-", " ")
            for key, lvl in _LEVEL_MAP.items():
                if key in heading:
                    current_level = lvl
                    break
        elif element.name == "table":
            spells.extend(_parse_spell_table(element, current_level))

    logger.info(f"Fetched {len(spells)} spells (fallback parser)")
    return spells


def fetch_spells_for_class(class_name: str, use_cache: bool = True) -> list[str]:
    """Return a list of spell names available to the given class."""
    url = f"{BASE_URL}/spells:{class_name}"
    try:
        soup = _fetch(url, use_cache)
    except RuntimeError as e:
        raise RuntimeError(
            f"Could not fetch spell list for class '{class_name}': {e}"
        ) from e

    content = _main_content(soup)
    if content is None:
        return []

    names: list[str] = []
    navset = content.find("div", class_="yui-navset")
    if navset:
        yui_content = navset.find("div", class_="yui-content")
        panels = yui_content.find_all("div", recursive=False) if yui_content else []
        for panel in panels:
            for row in panel.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if cells:
                    names.append(_text(cells[0]).replace(" (ritual)", "").strip())
    else:
        for row in content.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if cells:
                names.append(_text(cells[0]).replace(" (ritual)", "").strip())

    logger.debug(f"Found {len(names)} spells for class '{class_name}'")
    return names


def fetch_spell_detail(url: str, use_cache: bool = True) -> dict[str, Any]:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return {}

    detail: dict[str, Any] = {
        "source": "",
        "description": "",
        "description_md": "",
        "at_higher_levels": "",
        "at_higher_levels_md": "",
        "classes": [],
    }

    for p in content.find_all("p"):
        text = _text(p)
        if not text:
            continue
        low = text.lower()

        # "Source: Player's Handbook p. 241"
        if low.startswith("source:"):
            detail["source"] = text[len("source:") :].strip()
            continue

        # "3rd-level evocation" / "Evocation cantrip" — level+school line, skip
        if (
            re.match(r"^\d+(st|nd|rd|th)-level", text, re.I)
            or re.match(r"^\w+\s+cantrip\b", text, re.I)
            or re.match(r"^cantrip$", text, re.I)
        ):
            continue

        # Concatenated properties block — "Casting Time:...Range:..." with no spaces between keys
        if low.startswith("casting time:") or low.startswith("casting time "):
            continue

        # "Spell Lists. Sorcerer, Wizard" or "Spell List. Wizard"
        if re.match(r"^spell lists?\.", text, re.I):
            after = re.split(r"\.\s*", text, maxsplit=1)[-1]
            detail["classes"] = [c.strip() for c in after.split(",") if c.strip()]
            continue

        # "At Higher Levels." — separate section
        if re.match(r"^at higher levels", low):
            detail["at_higher_levels"] = text
            detail["at_higher_levels_md"] = _para_md(p)
            continue

        # Everything else is description body
        md_text = _para_md(p)
        if detail["description"]:
            detail["description"] += "\n\n" + text
            detail["description_md"] += "\n\n" + md_text
        else:
            detail["description"] = text
            detail["description_md"] = md_text

    return detail


# Known base classes used for filtering
_BASE_CLASSES = [
    "artificer",
    "barbarian",
    "bard",
    "cleric",
    "druid",
    "fighter",
    "monk",
    "paladin",
    "ranger",
    "rogue",
    "sorcerer",
    "warlock",
    "wizard",
]


def _fetch_home_links(use_cache: bool = True) -> list[tuple[str, str]]:
    """Return (name, href) pairs from the main wikidot index page."""
    soup = _fetch(BASE_URL + "/", use_cache)
    content = _main_content(soup)
    if content is None:
        return []
    return [
        (_text(a), str(a.get("href", "")))
        for a in content.find_all("a")
        if str(a.get("href", "")).startswith("/") and _text(a)
    ]


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------


def fetch_classes(use_cache: bool = True) -> list[DnDClass]:
    links = _fetch_home_links(use_cache)
    classes: list[DnDClass] = []
    seen = set()
    for name, href in links:
        slug = href.lstrip("/")
        if slug in _BASE_CLASSES and slug not in seen:
            seen.add(slug)
            classes.append(DnDClass(name=name, url=BASE_URL + href))
    logger.info(f"Fetched {len(classes)} classes")
    return classes


def fetch_class_detail(url: str, use_cache: bool = True) -> dict[str, Any]:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return {}

    detail: dict[str, Any] = {"hit_die": "", "primary_ability": "", "saving_throws": ""}
    paragraphs: list[str] = []

    # Single pass: collect description paragraphs and parse <strong>Key:</strong> value pairs.
    # Wikidot sometimes splits a label across adjacent <strong> tags, e.g.
    # <strong>Sav</strong><strong>ing Throws:</strong>, so we walk children
    # accumulating consecutive <strong> text, then grab the following text value.
    for el in content.find_all("p"):
        t = el.get_text(strip=True)
        if t:
            paragraphs.append(t)
        children = list(el.children)
        i = 0
        while i < len(children):
            child = children[i]
            if getattr(child, "name", None) != "strong":
                i += 1
                continue
            # Accumulate consecutive <strong> siblings into one label
            label_parts = [child.get_text(strip=True)]
            j = i + 1
            while j < len(children) and getattr(children[j], "name", None) == "strong":
                label_parts.append(children[j].get_text(strip=True))
                j += 1
            label = "".join(label_parts).rstrip(":").lower()
            # Collect text until next <strong> or <br/>
            value_parts = []
            while j < len(children):
                sib = children[j]
                if getattr(sib, "name", None) in ("strong", "br"):
                    break
                value_parts.append(str(sib))
                j += 1
            value = re.sub(r"\s+", " ", "".join(value_parts)).strip().strip(":")
            if label == "hit dice":
                m = re.search(r"\d*(d\d+)", value, re.I)
                detail["hit_die"] = m.group(1) if m else value
            elif label == "saving throws":
                detail["saving_throws"] = value
            i = j

    detail["description"] = "\n\n".join(paragraphs[:3])

    # Extract primary ability from multi-classing prerequisite text.
    # This text may appear in <p>, <em>, or other elements — search full content.
    full_text = content.get_text(" ", strip=True)
    m2 = re.search(
        r"must have (?:a |an )?(\w+) score and (?:a |an )?(\w+) score of (\d+)?",
        full_text,
        re.I,
    )
    if m2:
        detail["primary_ability"] = (
            f"{m2.group(1)} {m2.group(3)}+ and {m2.group(2)} {m2.group(3)}+"
        )
    else:
        m1 = re.search(
            r"must have (?:a |an )?(\w+(?: or \w+)?)\s+score of (\d+)",
            full_text,
            re.I,
        )
        if m1:
            detail["primary_ability"] = f"{m1.group(1)} {m1.group(2)}+"

    # Extract subclass table
    subclasses = []
    for table in content.find_all("table"):
        headers = [_text(th).lower() for th in table.find_all("th")]
        if any("archetype" in h or "subclass" in h or "name" in h for h in headers):
            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if cells:
                    link = cells[0].find("a")
                    sub_name = _text(cells[0])
                    sub_url = _href(link) if link else ""
                    source = _text(cells[1]) if len(cells) > 1 else ""
                    if sub_name:
                        subclasses.append(
                            {"name": sub_name, "url": sub_url, "source": source}
                        )
    detail["subclasses"] = subclasses
    return detail


def fetch_class_features(class_name: str, use_cache: bool = True) -> dict[str, Any]:
    """Fetch the full level progression table and feature descriptions for a class."""
    slug = class_name.lower().strip()
    url = f"{BASE_URL}/{slug}"
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return {}

    result: dict[str, Any] = {"class_name": slug.title(), "url": url}

    # ------------------------------------------------------------------
    # Parse the progression table (first table on the page)
    # Row 0 is the title/subtitle row; scan for the row containing "Level"
    # ------------------------------------------------------------------
    tables = content.find_all("table")
    if tables:
        prog_table = tables[0]
        rows = prog_table.find_all("tr")

        header_idx = 0
        for i, row in enumerate(rows):
            texts = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if "Level" in texts:
                header_idx = i
                break

        headers = [
            c.get_text(strip=True) for c in rows[header_idx].find_all(["th", "td"])
        ]
        level_rows: list[list[str]] = []
        for row in rows[header_idx + 1 :]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if cells and cells[0]:  # skip empty rows
                level_rows.append(cells)

        result["table_headers"] = headers
        result["table_rows"] = level_rows

        # Second table (if present) is the subclass list — skip for features
        if len(tables) > 1:
            sub_table = tables[1]
            subclasses = []
            sub_rows = sub_table.find_all("tr")
            for row in sub_rows[1:]:
                cells = row.find_all(["td", "th"])
                if cells:
                    link = cells[0].find("a")
                    sub_name = _text(cells[0])
                    sub_url = _href(link) if link else ""
                    source = _text(cells[1]) if len(cells) > 1 else ""
                    if sub_name:
                        subclasses.append(
                            {"name": sub_name, "url": sub_url, "source": source}
                        )
            result["subclasses"] = subclasses

    # ------------------------------------------------------------------
    # Parse class feature descriptions (h3 headings + their paragraphs/lists)
    # These follow the progression table in the document.
    # ------------------------------------------------------------------
    features: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    past_table = False

    for el in content.find_all(["table", "h1", "h2", "h3", "h4", "p", "ul", "ol"]):
        if el.name == "table":
            past_table = True
            continue
        if not past_table:
            continue

        text = el.get_text(strip=True)
        if not text:
            continue

        # h1/h2 are section dividers (e.g. "Class Features"), not individual features.
        # Flush any open feature but don't start a new one from them.
        if el.name in ("h1", "h2"):
            if current:
                features.append(current)
            current = None
            continue

        if el.name in ("h3", "h4"):
            if current:
                features.append(current)
            current = {"name": text, "level": None, "body": []}
            # Try to infer unlock level from heading text (e.g. "Extra Attack (5th Level)")
            m = re.search(r"\b(\d+)(st|nd|rd|th)\b", text, re.I)
            if m:
                current["level"] = int(m.group(1))

        elif el.name in ("p", "ul", "ol") and current is not None:
            if el.name in ("ul", "ol"):
                items = [_text(li) for li in el.find_all("li") if _text(li)]
                if items:
                    current["body"].append({"type": "list", "items": items})
            else:
                current["body"].append(
                    {"type": "paragraph", "text": text, "text_md": _para_md(el)}
                )
                # Try to infer level from paragraph text if not already found
                if current["level"] is None:
                    m = re.search(r"\bat\s+(\d+)(st|nd|rd|th)\s+level\b", text, re.I)
                    if m:
                        current["level"] = int(m.group(1))

    if current:
        features.append(current)

    result["features"] = features
    logger.info(f"Fetched {len(features)} features for {slug}")
    return result


# ---------------------------------------------------------------------------
# Subclasses
# ---------------------------------------------------------------------------


def fetch_subclasses(
    class_name: str | None = None, use_cache: bool = True
) -> list[Subclass]:
    """Fetch subclasses from the home page link list, enriched with source from class pages."""
    links = _fetch_home_links(use_cache)
    subclasses: list[Subclass] = []
    seen = set()

    # Determine which base classes to scan
    target_classes = [class_name.lower()] if class_name else list(_BASE_CLASSES)

    # Build a URL→source map from each relevant class page's subclass table
    source_map: dict[str, str] = {}
    for cls in target_classes:
        try:
            data = fetch_class_features(cls, use_cache)
            for entry in data.get("subclasses", []):
                if entry.get("url") and entry.get("source"):
                    source_map[entry["url"]] = entry["source"]
        except Exception:
            pass

    for name, href in links:
        slug = href.lstrip("/")
        if ":" not in slug:
            continue

        parts = slug.split(":", 1)
        parent_slug = parts[0]
        sub_slug = parts[1]

        if parent_slug not in _BASE_CLASSES:
            continue
        if ":" in sub_slug:
            continue

        if class_name and parent_slug != class_name.lower():
            continue

        href = href.rstrip("/").lower()
        if href in seen:
            continue
        seen.add(href)

        display_name = f"{name} (UA)" if sub_slug.endswith("-ua") else name
        full_url = BASE_URL + href
        subclasses.append(
            Subclass(
                name=display_name,
                url=full_url,
                parent_class=parent_slug.title(),
                source=source_map.get(full_url, ""),
            )
        )

    logger.info(f"Fetched {len(subclasses)} subclasses")
    return subclasses


def fetch_subclass_detail(url: str, use_cache: bool = True) -> dict[str, Any]:
    """Fetch full detail for a single subclass page."""
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return {}

    detail: dict[str, Any] = {
        "source": "",
        "description": "",
        "description_md": "",
        "features": [],
    }
    current: dict[str, Any] | None = None

    for el in content.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "table"]):
        tag = el.name
        text = _text(el)

        if tag == "table":
            spell_entries = _parse_granted_spells(el)
            if spell_entries and current is not None:
                current["spell_table"] = spell_entries
            continue

        if not text:
            continue

        if tag == "h1":
            if not detail["source"]:
                detail["source"] = text
            continue

        # h2 = section divider (e.g. "Subclass Features"), not a feature itself
        if tag == "h2":
            if current:
                detail["features"].append(current)
            current = None
            continue

        # h3/h4 = individual feature headings
        if tag in ("h3", "h4"):
            if current:
                detail["features"].append(current)
            current = {"name": text, "body": []}
            continue

        if tag == "p":
            low = text.lower()
            if low.startswith("source:"):
                detail["source"] = text[len("source:") :].strip()
                continue
            md_text = _para_md(el)
            if current is None:
                detail["description"] = (detail["description"] + "\n\n" + text).lstrip(
                    "\n"
                )
                detail["description_md"] = (
                    detail["description_md"] + "\n\n" + md_text
                ).lstrip("\n")
            else:
                current["body"].append(
                    {"type": "paragraph", "text": text, "text_md": md_text}
                )

        elif tag in ("ul", "ol") and current is not None:
            items = [_text(li) for li in el.find_all("li") if _text(li)]
            if items:
                current["body"].append({"type": "list", "items": items})

    if current:
        detail["features"].append(current)

    return detail


# ---------------------------------------------------------------------------
# Feats
# ---------------------------------------------------------------------------


def fetch_feats(use_cache: bool = True) -> list[Feat]:
    """Collect all feat links from the main index page."""
    links = _fetch_home_links(use_cache)
    feats: list[Feat] = []
    seen: set[str] = set()

    for name, href in links:
        if not href.startswith("/feat:"):
            continue
        if href in seen:
            continue
        seen.add(href)
        feats.append(Feat(name=name, url=BASE_URL + href))

    logger.info(f"Fetched {len(feats)} feats")
    return feats


def fetch_feat_detail(url: str, use_cache: bool = True) -> dict[str, Any]:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return {}

    detail: dict[str, Any] = {
        "source": "",
        "prerequisites": "",
        "description": "",
        "description_md": "",
        "benefits": [],
    }

    for p in content.find_all("p"):
        text = _text(p)
        if not text:
            continue
        low = text.lower()

        if low.startswith("source:"):
            detail["source"] = text[len("source:") :].strip()
            continue

        if low.startswith("prerequisite"):
            detail["prerequisites"] = re.sub(
                r"^prerequisites?:\s*", "", text, flags=re.I
            )
            continue

        md_text = _para_md(p)
        if detail["description"]:
            detail["description"] += "\n\n" + text
            detail["description_md"] += "\n\n" + md_text
        else:
            detail["description"] = text
            detail["description_md"] = md_text

    # Bullet benefits come from <ul><li> elements
    for ul in content.find_all(["ul", "ol"]):
        for li in ul.find_all("li"):
            item_text = _text(li)
            if item_text:
                detail["benefits"].append(item_text)

    return detail


# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------


def _fetch_race_basic(url: str, use_cache: bool = True) -> dict[str, str]:
    """Extract size, speed, and source from an individual race page."""
    try:
        soup = _fetch(url, use_cache)
    except RuntimeError:
        return {}
    content = _main_content(soup)
    if content is None:
        return {}

    result: dict[str, str] = {}

    # Source = first h1 heading (e.g. "Player's Handbook")
    h1 = content.find("h1")
    if h1:
        src = h1.get_text(strip=True)
        # Skip headings that are just "<Race> Features" — not a real book name
        if not src.endswith("Features"):
            result["source"] = src

    # Size and Speed are in <li> items under <strong>Label.</strong>
    for li in content.find_all("li"):
        strong = li.find("strong")
        if not strong:
            continue
        label = strong.get_text(strip=True).rstrip(".").lower()
        text = li.get_text(strip=True)

        if label == "size" and "size" not in result:
            m = re.search(r"\bYour size is (\w+)", text, re.I)
            if m:
                result["size"] = m.group(1).capitalize()
            else:
                m2 = re.search(
                    r"\b(Tiny|Small|Medium|Large|Huge|Gargantuan)\b", text, re.I
                )
                if m2:
                    result["size"] = m2.group(1).capitalize()

        elif label == "speed" and "speed" not in result:
            m = re.search(r"\b(\d+ feet)\b", text)
            if m:
                result["speed"] = m.group(1)

    return result


def fetch_races(use_cache: bool = True) -> list[Race]:
    import concurrent.futures

    # Collect all /lineage:xxx links from the /lineage index page
    soup = _fetch(f"{BASE_URL}/lineage", use_cache)
    content = _main_content(soup)
    if content is None:
        return []

    seen: set[str] = set()
    stubs: list[Race] = []
    for a in content.find_all("a"):
        href = str(a.get("href", ""))
        if not href.startswith("/lineage:"):
            continue
        # Skip Unearthed Arcana playtest variants that duplicate published entries
        if href.endswith("-ua"):
            continue
        if href in seen:
            continue
        seen.add(href)
        name = _text(a)
        if name:
            stubs.append(Race(name=name, url=BASE_URL + href))

    if not stubs:
        logger.warning("No /lineage: links found on the lineage index page")
        return []

    # Enrich each race with size/speed/source from its individual page
    def _enrich(race: Race) -> Race:
        basic = _fetch_race_basic(race.url, use_cache)
        return Race(
            name=race.name,
            url=race.url,
            size=basic.get("size", ""),
            speed=basic.get("speed", ""),
            source=basic.get("source", ""),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        races = list(pool.map(_enrich, stubs))

    logger.info(f"Fetched {len(races)} races")
    return races


def _parse_trait_li(li: Tag) -> dict[str, str]:
    """Parse a <li><strong>Name.</strong> Description</li> into {"name": ..., "text": ...}."""
    strong = li.find("strong")
    if strong:
        name = strong.get_text(strip=True).rstrip(".")
        # Use separator=" " so inline elements don't merge without spaces
        full = li.get_text(separator=" ", strip=True)
        prefix = strong.get_text(strip=True)
        text = full[len(prefix) :].strip().lstrip(". ").strip()
    else:
        name = ""
        text = li.get_text(separator=" ", strip=True)
    return {"name": name, "text": text}


def fetch_race_detail(url: str, use_cache: bool = True) -> dict[str, Any]:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return {}

    # Result structure mirrors the page hierarchy:
    # base (before first h2) + subraces (one dict per h2)
    result: dict[str, Any] = {
        "source": "",
        "description": "",
        "description_md": "",
        "traits": [],
        "subraces": [],
    }

    current_source = ""
    first_h1 = True
    # current_target points to either result (base) or current subrace dict
    current_target: dict[str, Any] = result

    for el in content.find_all(["h1", "h2", "p", "ul", "ol", "table"]):
        tag = el.name
        text = _text(el)

        if tag == "h1":
            if not text.endswith("Features"):
                current_source = text
            if first_h1:
                # First source section → base result
                first_h1 = False
                result["source"] = current_source
                current_target = result
            else:
                # Subsequent source sections get their own container so that
                # traits between this h1 and the next h2 aren't absorbed into
                # the base section.
                section: dict[str, Any] = {
                    "name": current_source,
                    "source": current_source,
                    "description": "",
                    "description_md": "",
                    "traits": [],
                }
                result["subraces"].append(section)
                current_target = section
            continue

        if tag == "h2":
            subrace: dict[str, Any] = {
                "name": text,
                "source": current_source,
                "description": "",
                "description_md": "",
                "traits": [],
            }
            result["subraces"].append(subrace)
            current_target = subrace
            continue

        if tag == "p":
            if not text:
                continue
            low = text.lower()
            if low.startswith("source:"):
                if current_target is not result:
                    current_target["source"] = text[len("source:") :].strip()
                continue
            md_text = _para_md(el)
            if current_target["description"]:
                current_target["description"] += "\n\n" + text
                current_target["description_md"] += "\n\n" + md_text
            else:
                current_target["description"] = text
                current_target["description_md"] = md_text
            continue

        if tag == "table":
            spell_entries = _parse_granted_spells(el)
            if spell_entries:
                current_target.setdefault("spell_table", []).extend(spell_entries)
            continue

        if tag in ("ul", "ol"):
            for li in el.find_all("li"):
                trait = _parse_trait_li(li)
                if trait["name"] or trait["text"]:
                    current_target["traits"].append(trait)

    # Drop empty placeholder sections (h1 with no content before next h2)
    result["subraces"] = [
        s for s in result["subraces"] if s.get("description") or s.get("traits")
    ]

    return result


# ---------------------------------------------------------------------------
# Items (Magic Items)
# ---------------------------------------------------------------------------

_RARITY_TABS = [
    "Common",
    "Uncommon",
    "Rare",
    "Very Rare",
    "Legendary",
    "Artifact",
    "Unique",
    "???",
]


def _parse_item_table(table: Tag, rarity: str) -> list[Item]:
    rows = table.find_all("tr")
    if not rows:
        return []

    header_row = rows[0]
    headers = [_text(th).lower() for th in header_row.find_all(["th", "td"])]

    col = {
        "name": next(
            (i for i, h in enumerate(headers) if "name" in h or "item" in h), 0
        ),
        "type": next((i for i, h in enumerate(headers) if "type" in h), -1),
        "attune": next((i for i, h in enumerate(headers) if "attun" in h), -1),
        "source": next((i for i, h in enumerate(headers) if "source" in h), -1),
    }

    items = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        name_cell = cells[col["name"]]
        link = name_cell.find("a")
        name = _text(name_cell)
        url = _href(link) if link else ""
        item_type = (
            _text(cells[col["type"]])
            if col["type"] >= 0 and col["type"] < len(cells)
            else ""
        )
        attune_val = (
            _text(cells[col["attune"]])
            if col["attune"] >= 0 and col["attune"] < len(cells)
            else "-"
        )
        source = (
            _text(cells[col["source"]])
            if col["source"] >= 0 and col["source"] < len(cells)
            else ""
        )
        requires_attunement = attune_val.lower() not in ("-", "no", "false", "")

        if name:
            items.append(
                Item(
                    name=name,
                    url=url,
                    item_type=item_type,
                    rarity=rarity,
                    requires_attunement=requires_attunement,
                    source=source,
                )
            )
    return items


def fetch_items(use_cache: bool = True) -> list[Item]:
    """Fetch magic items from the wondrous-items page (tabs = rarity tiers)."""
    items: list[Item] = []

    soup = _fetch(f"{BASE_URL}/wondrous-items", use_cache)
    content = _main_content(soup)
    if content:
        navset = content.find("div", class_="yui-navset")
        if navset:
            # Tab labels correspond to rarity
            nav = navset.find("ul", class_="yui-nav")
            tab_labels = (
                [_text(li) for li in nav.find_all("li")] if nav else _RARITY_TABS
            )
            yui_content = navset.find("div", class_="yui-content")
            panels = yui_content.find_all("div", recursive=False) if yui_content else []
            for i, panel in enumerate(panels):
                rarity = tab_labels[i] if i < len(tab_labels) else ""
                for table in panel.find_all("table"):
                    items.extend(_parse_item_table(table, rarity))
        else:
            for table in content.find_all("table"):
                items.extend(_parse_item_table(table, ""))

    logger.info(f"Fetched {len(items)} items")
    return items


def fetch_item_detail(url: str, use_cache: bool = True) -> dict[str, Any]:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return {}

    detail: dict[str, Any] = {"source": "", "description": ""}

    for p in content.find_all("p"):
        text = p.get_text(strip=True)
        if not text:
            continue
        low = text.lower()

        if low.startswith("source:"):
            detail["source"] = text[len("source:") :].strip()
            continue

        # Skip the "type, rarity (requires attunement)" metadata line
        # These are short lines that contain rarity keywords
        if (
            any(
                r in low
                for r in ("common", "uncommon", "rare", "legendary", "artifact")
            )
            and len(text) < 100
        ):
            continue

        if detail["description"]:
            detail["description"] += "\n\n" + text
        else:
            detail["description"] = text

    return detail
