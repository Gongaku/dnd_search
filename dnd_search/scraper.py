"""Web scraper for dnd5e.wikidot.com."""

import concurrent.futures
import json
import logging
import re
from dataclasses import asdict
from functools import lru_cache, wraps
from typing import Any, Callable, TypeVar, cast

_DetailT = TypeVar("_DetailT")

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from dnd_search import cache
from dnd_search.models import (
    ClassDetail,
    ClassFeatures,
    DnDClass,
    Feat,
    FeatDetail,
    Feature,
    Item,
    ItemDetail,
    Race,
    RaceDetail,
    Spell,
    SpellDetail,
    SpellTableEntry,
    Subclass,
    SubclassDetailDict,
    SubclassEntry,
    SubraceDetail,
    Trait,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://dnd5e.wikidot.com"
MAX_WORKERS = 8  # Global thread ceiling for all ThreadPoolExecutor usage
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

# Compiled regex patterns
_RE_MULTI_SPACE = re.compile(r" {2,}")
_RE_HTTP_SCHEME = re.compile(r"^https?://")
_RE_LEVEL_SCHOOL = re.compile(r"^\d+(st|nd|rd|th)-level", re.I)
_RE_CANTRIP = re.compile(r"^\w+\s+cantrip\b|^cantrip$", re.I)
_RE_SPELL_LISTS = re.compile(r"^spell lists?\.", re.I)
_RE_AT_HIGHER = re.compile(r"^at higher levels", re.I)
_RE_HIT_DIE = re.compile(r"\d*(d\d+)", re.I)
_RE_ORDINAL_IN_TEXT = re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.I)
_RE_LEVEL_IN_TEXT = re.compile(r"\bat\s+(\d+)(st|nd|rd|th)\s+level\b", re.I)
_RE_MULTICLASS_TWO = re.compile(
    r"must have (?:a |an )?(\w+) score and (?:a |an )?(\w+) score of (\d+)?", re.I
)
_RE_MULTICLASS_ONE = re.compile(
    r"must have (?:a |an )?(\w+(?: or \w+)?)\s+score of (\d+)", re.I
)
_RE_SIZE = re.compile(r"\bYour size is (\w+)", re.I)
_RE_SPEED = re.compile(r"\b(\d+ feet)\b")
_RE_DC_SCHOOL = re.compile(r"\s*DC\b.*$", re.I)


@lru_cache(maxsize=256)
def _fetch_soup(url: str) -> BeautifulSoup:
    """Fetch and parse a URL, reading from file cache if available.

    Results are memoised for the lifetime of the process — callers must not
    mutate the returned BeautifulSoup object.
    """
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
    cache.set(url, resp.text)
    return BeautifulSoup(resp.text, "lxml")


def _fetch(url: str, use_cache: bool = True) -> BeautifulSoup:
    if use_cache:
        return _fetch_soup(url)
    logger.info(f"Fetching {url} (cache bypassed)")
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e
    logger.debug(f"Response {resp.status_code} ({len(resp.text)} bytes)")
    return BeautifulSoup(resp.text, "lxml")


def _parse_cache(prefix: str):
    """Decorator that caches a fetch_*_detail(url, use_cache) function's parsed result.

    On a warm cache hit the function body is skipped entirely — only json.loads runs.
    The cache key is "{prefix}:{url}" so it never collides with raw HTML entries.
    """
    def decorator(fn: Callable[..., _DetailT]) -> Callable[..., _DetailT]:
        @wraps(fn)
        def wrapper(url: str, use_cache: bool = True) -> _DetailT:
            key = f"{prefix}:{url}"
            if use_cache and (hit := cache.get(key)):
                return json.loads(hit)  # type: ignore[return-value]
            result = fn(url, use_cache)
            if use_cache:
                cache.set(key, json.dumps(result))
            return result
        return wrapper
    return decorator


def _main_content(soup: BeautifulSoup) -> Tag | None:
    return soup.find("div", id="page-content") or soup.find(
        "div", class_="page-content"
    )


def _text(tag: Tag | None) -> str:
    if tag is None:
        return ""
    return _RE_MULTI_SPACE.sub(" ", tag.get_text(separator=" ", strip=True))


def _first_line(tag: Tag) -> str:
    """Return only the text before the first <br> in a tag.

    Some wiki prerequisite paragraphs merge the prerequisite and description
    in one <p>, separated by <br> tags.  Walking direct children and stopping
    at the first <br> preserves inline link text (e.g. feat hyperlinks) while
    still splitting at real line-break boundaries.
    """
    parts: list[str] = []
    for child in tag.children:
        if isinstance(child, Tag) and child.name == "br":
            break
        if isinstance(child, Tag):
            parts.append(child.get_text(separator=" ", strip=True))
        elif isinstance(child, NavigableString):
            parts.append(str(child))
    return _RE_MULTI_SPACE.sub(" ", " ".join(parts)).strip()


def _parse_granted_spells(table: Tag) -> list[SpellTableEntry] | None:
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


def _para_inline(el, bold: tuple[str, str], italic: tuple[str, str], links: bool = False) -> str:
    """Render element children with inline formatting.

    bold/italic are (open, close) tag pairs, e.g. ("**", "**") for markdown
    or ("[bold]", "[/bold]") for Rich. Set links=True to render <a> as markdown links.
    """
    parts = []
    for child in el.children:
        name = getattr(child, "name", None)
        if links and name == "a":
            href = str(child.get("href", ""))
            link_text = _RE_MULTI_SPACE.sub(" ", child.get_text(separator=" ", strip=True))
            if href.startswith("/"):
                href = BASE_URL + href
            parts.append(f"[{link_text}]({href})" if link_text else "")
        elif name in ("strong", "b"):
            inner = _para_inline(child, bold, italic, links)
            parts.append(f"{bold[0]}{inner}{bold[1]}")
        elif name in ("em", "i"):
            inner = _para_inline(child, bold, italic, links)
            parts.append(f"{italic[0]}{inner}{italic[1]}")
        elif hasattr(child, "get_text"):
            parts.append(child.get_text(separator=" "))
        else:
            parts.append(str(child))
    return _RE_MULTI_SPACE.sub(" ", "".join(parts).strip())


def _para_md(el) -> str:
    """Render element content as markdown, preserving links and bold/italic."""
    return _para_inline(el, bold=("**", "**"), italic=("*", "*"), links=True)


def _para_rich(el) -> str:
    """Render element content as Rich markup, preserving bold/italic."""
    return _para_inline(el, bold=("[bold]", "[/bold]"), italic=("[italic]", "[/italic]"))


def _norm_url(url: str) -> str:
    """Strip scheme and trailing slash for scheme-agnostic URL comparison."""
    return _RE_HTTP_SCHEME.sub("", url).rstrip("/")


def _href(tag: Tag | None) -> str:
    if tag is None:
        return ""
    raw = str(tag.get("href", ""))
    # Wiki table links sometimes use http:// — normalise to https://.
    if raw.startswith("http://"):
        raw = "https://" + raw[len("http://"):]
    if raw.startswith("/"):
        return BASE_URL + raw
    return raw


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

        school = _RE_DC_SCHOOL.sub(
            "",
            _text(cells[col["school"]]) if col["school"] < len(cells) else "",
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


@_parse_cache("spell")
def fetch_spell_detail(url: str, use_cache: bool = True) -> SpellDetail:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return cast(SpellDetail, {})

    detail: SpellDetail = {
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
            _RE_LEVEL_SCHOOL.match(text)
            or _RE_CANTRIP.match(text)
        ):
            continue

        # Concatenated properties block — "Casting Time:...Range:..." with no spaces between keys
        if low.startswith("casting time:") or low.startswith("casting time "):
            continue

        # "Spell Lists. Sorcerer, Wizard" or "Spell List. Wizard"
        if _RE_SPELL_LISTS.match(text):
            after = re.split(r"\.\s*", text, maxsplit=1)[-1]
            detail["classes"] = [c.strip() for c in after.split(",") if c.strip()]
            continue

        # "At Higher Levels." — separate section
        if _RE_AT_HIGHER.match(low):
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


# First-column header names used by each class's subclass table on the wiki.
# Each class calls its subclass concept something different (Path, Circle, etc.).
_SUBCLASS_COL_NAMES = {
    "archetype",   # Fighter, Rogue
    "circle",      # Druid
    "college",     # Bard
    "conclave",    # Ranger
    "domain",      # Cleric
    "oath",        # Paladin
    "origin",      # Sorcerer
    "path",        # Barbarian
    "patron",      # Warlock
    "school",      # Wizard
    "specialty",   # Artificer
    "subclass",    # generic fallback
    "tradition",   # Monk
}


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


@_parse_cache("class")
def fetch_class_detail(url: str, use_cache: bool = True) -> ClassDetail:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return cast(ClassDetail, {})

    detail: ClassDetail = {"hit_die": "", "primary_ability": "", "saving_throws": "", "description": "", "subclasses": []}
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
            value = " ".join("".join(value_parts).split()).strip(":")
            if label == "hit dice":
                m = _RE_HIT_DIE.search(value)
                detail["hit_die"] = m.group(1) if m else value
            elif label == "saving throws":
                detail["saving_throws"] = value
            i = j

    detail["description"] = "\n\n".join(paragraphs[:3])

    # Extract primary ability from multi-classing prerequisite text.
    # This text may appear in <p>, <em>, or other elements — search full content.
    full_text = content.get_text(" ", strip=True)
    m2 = _RE_MULTICLASS_TWO.search(full_text)
    if m2:
        detail["primary_ability"] = (
            f"{m2.group(1)} {m2.group(3)}+ and {m2.group(2)} {m2.group(3)}+"
        )
    else:
        m1 = _RE_MULTICLASS_ONE.search(full_text)
        if m1:
            detail["primary_ability"] = f"{m1.group(1)} {m1.group(2)}+"

    # Extract subclass table
    subclasses = []
    for table in content.find_all("table"):
        headers = [_text(th).lower() for th in table.find_all("th")]
        if any(h in _SUBCLASS_COL_NAMES for h in headers):
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


def _parse_progression_table(table: Tag) -> tuple[list[str], list[list[str]]]:
    """Parse a class progression table into (headers, level_rows)."""
    rows = table.find_all("tr")
    header_idx = 0
    for i, row in enumerate(rows):
        if "Level" in [c.get_text(strip=True) for c in row.find_all(["th", "td"])]:
            header_idx = i
            break
    headers = [c.get_text(strip=True) for c in rows[header_idx].find_all(["th", "td"])]
    level_rows = [
        [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        for row in rows[header_idx + 1:]
        if (cells := row.find_all(["td", "th"])) and cells[0].get_text(strip=True)
    ]
    return headers, level_rows


def _parse_subclass_table(table: Tag) -> list[SubclassEntry]:
    """Parse a subclass list table into a list of {name, url, source} dicts."""
    subclasses = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        if cells:
            link = cells[0].find("a")
            sub_name = _text(cells[0])
            if sub_name:
                subclasses.append({
                    "name": sub_name,
                    "url": _href(link) if link else "",
                    "source": _text(cells[1]) if len(cells) > 1 else "",
                })
    return subclasses


def _parse_feature_descriptions(content: Tag) -> list[Feature]:
    """Parse h3/h4 feature headings and their body blocks from class page content."""
    features: list[Feature] = []
    current: Feature | None = None
    past_table = False

    for el in content.find_all(["table", "h1", "h2", "h3", "h4", "h5", "p", "ul", "ol"]):
        if el.name == "table":
            past_table = True
            continue
        if not past_table:
            continue

        text = el.get_text(strip=True)
        if not text:
            continue

        # h1/h2 are section dividers — flush open feature but don't start a new one
        if el.name in ("h1", "h2"):
            if current:
                features.append(current)
            current = None
            continue

        if el.name in ("h3", "h4"):
            if current:
                features.append(current)
            current = {"name": text, "level": None, "body": []}
            m = _RE_ORDINAL_IN_TEXT.search(text)
            if m:
                current["level"] = int(m.group(1))

        elif el.name == "h5" and current is not None:
            current["body"].append({"type": "heading", "text": text})

        elif el.name in ("p", "ul", "ol") and current is not None:
            if el.name in ("ul", "ol"):
                items = [_text(li) for li in el.find_all("li") if _text(li)]
                if items:
                    current["body"].append({"type": "list", "items": items})
            else:
                current["body"].append(
                    {"type": "paragraph", "text": text, "text_md": _para_md(el), "text_rich": _para_rich(el)}
                )
                if current["level"] is None:
                    m = _RE_LEVEL_IN_TEXT.search(text)
                    if m:
                        current["level"] = int(m.group(1))

    if current:
        features.append(current)
    return features


def fetch_class_features(class_name: str, use_cache: bool = True) -> ClassFeatures:
    """Fetch the full level progression table and feature descriptions for a class."""
    slug = class_name.lower().strip()
    url = f"{BASE_URL}/{slug}"
    key = f"class_features:{slug}"
    if use_cache and (hit := cache.get(key)):
        return cast(ClassFeatures, json.loads(hit))

    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return cast(ClassFeatures, {})

    result: ClassFeatures = {"class_name": slug.title(), "url": url}

    tables = content.find_all("table")
    if tables:
        headers, level_rows = _parse_progression_table(tables[0])
        result["table_headers"] = headers
        result["table_rows"] = level_rows
        if len(tables) > 1:
            result["subclasses"] = _parse_subclass_table(tables[1])

    features = _parse_feature_descriptions(content)
    result["features"] = features
    logger.info(f"Fetched {len(features)} features for {slug}")
    if use_cache:
        cache.set(key, json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# Subclasses
# ---------------------------------------------------------------------------


def fetch_subclasses(
    class_name: str | None = None, use_cache: bool = True
) -> list[Subclass]:
    """Fetch subclasses from the home page link list, enriched with source from class pages."""
    _key = f"subclasses:{class_name or 'all'}"
    if use_cache and (hit := cache.get(_key)):
        return [Subclass(**d) for d in json.loads(hit)]

    links = _fetch_home_links(use_cache)
    subclasses: list[Subclass] = []
    seen = set()

    # Determine which base classes to scan
    target_classes = [class_name.lower()] if class_name else list(_BASE_CLASSES)

    # Build a URL→source map from each relevant class page's subclass table.
    # fetch_class_detail is used here (not fetch_class_features) to avoid
    # parsing full progression tables and feature descriptions just for source data.
    source_map: dict[str, str] = {}
    for cls in target_classes:
        try:
            cls_url = f"{BASE_URL}/{cls}"
            data = fetch_class_detail(cls_url, use_cache)
            for entry in data.get("subclasses", []):
                if entry.get("url") and entry.get("source"):
                    source_map[_norm_url(entry["url"])] = entry["source"]
        except Exception as e:
            logger.debug(f"Could not fetch subclass sources for {cls}: {e}")

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
                source=source_map.get(_norm_url(full_url), ""),
            )
        )

    logger.info(f"Fetched {len(subclasses)} subclasses")
    if use_cache:
        cache.set(_key, json.dumps([asdict(s) for s in subclasses]))
    return subclasses


@_parse_cache("subclass")
def fetch_subclass_detail(url: str, use_cache: bool = True) -> SubclassDetailDict:
    """Fetch full detail for a single subclass page."""
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return cast(SubclassDetailDict, {})

    detail: SubclassDetailDict = {
        "source": "",
        "description": "",
        "description_md": "",
        "features": [],
    }
    current: Feature | None = None

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
            current = Feature(name=text, body=[])
            continue

        if tag == "p":
            low = text.lower()
            if low.startswith("source:"):
                detail["source"] = text[len("source:") :].strip()
                continue
            md_text = _para_md(el)
            rich_text = _para_rich(el)
            if current is None:
                detail["description"] = (detail["description"] + "\n\n" + text).lstrip(
                    "\n"
                )
                detail["description_md"] = (
                    detail["description_md"] + "\n\n" + md_text
                ).lstrip("\n")
            else:
                current["body"].append(
                    {"type": "paragraph", "text": text, "text_md": md_text, "text_rich": rich_text}
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
    """Collect all feat links from the main index page and enrich with prerequisites."""
    links = _fetch_home_links(use_cache)
    stubs: list[Feat] = []
    seen: set[str] = set()

    for name, href in links:
        if not href.startswith("/feat:"):
            continue
        if href in seen:
            continue
        seen.add(href)
        slug = href[len("/feat:"):]
        display_name = f"{name} (UA)" if slug.endswith("-ua") else name
        stubs.append(Feat(name=display_name, url=BASE_URL + href))

    if not stubs:
        return []

    def _enrich(feat: Feat) -> Feat:
        basic = _fetch_feat_basic(feat.url, use_cache)
        return Feat(
            name=feat.name,
            url=feat.url,
            prerequisites=basic.get("prerequisites", ""),
            source=basic.get("source", ""),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        feats = list(pool.map(_enrich, stubs))

    logger.info(f"Fetched {len(feats)} feats")
    return feats


def _fetch_feat_basic(url: str, use_cache: bool = True) -> dict[str, str]:
    """Extract prerequisites and source from a feat page for listing enrichment."""
    try:
        soup = _fetch(url, use_cache)
    except RuntimeError:
        return {}
    content = _main_content(soup)
    if content is None:
        return {}

    result: dict[str, str] = {}
    for p in content.find_all("p"):
        text = _text(p)
        if not text:
            continue
        low = text.lower()
        if low.startswith("source:") and "source" not in result:
            result["source"] = text[len("source:"):].strip()
        elif low.startswith("prerequisite") and "prerequisites" not in result:
            first = _first_line(p)
            result["prerequisites"] = re.sub(r"^prerequisites?:\s*", "", first, flags=re.I)
        if "source" in result and "prerequisites" in result:
            break
    return result


@_parse_cache("feat")
def fetch_feat_detail(url: str, use_cache: bool = True) -> FeatDetail:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return cast(FeatDetail, {})

    detail: FeatDetail = {
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
            first = _first_line(p)
            detail["prerequisites"] = re.sub(r"^prerequisites?:\s*", "", first, flags=re.I)
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
            m = _RE_SIZE.search(text)
            if m:
                result["size"] = m.group(1).capitalize()
            else:
                m2 = re.search(r"\b(Tiny|Small|Medium|Large|Huge|Gargantuan)\b", text, re.I)
                if m2:
                    result["size"] = m2.group(1).capitalize()

        elif label == "speed" and "speed" not in result:
            m = _RE_SPEED.search(text)
            if m:
                result["speed"] = m.group(1)

    return result


def fetch_races(use_cache: bool = True) -> list[Race]:
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        races = list(pool.map(_enrich, stubs))

    logger.info(f"Fetched {len(races)} races")
    return races


def _parse_trait_li(li: Tag) -> Trait:
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


@_parse_cache("race")
def fetch_race_detail(url: str, use_cache: bool = True) -> RaceDetail:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return cast(RaceDetail, {})

    # Result structure mirrors the page hierarchy:
    # base (before first h2) + subraces (one dict per h2)
    result: RaceDetail = {
        "source": "",
        "description": "",
        "description_md": "",
        "traits": [],
        "subraces": [],
    }

    current_source = ""
    first_h1 = True
    # current_target points to either result (base) or current subrace dict
    current_target: RaceDetail | SubraceDetail = result

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
                section: SubraceDetail = {
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
            subrace: SubraceDetail = {
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
                # spell_table only appears on subrace sections, not the base result
                cast(SubraceDetail, current_target).setdefault("spell_table", []).extend(spell_entries)
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


@_parse_cache("item")
def fetch_item_detail(url: str, use_cache: bool = True) -> ItemDetail:
    soup = _fetch(url, use_cache)
    content = _main_content(soup)
    if content is None:
        return cast(ItemDetail, {})

    detail: ItemDetail = {"source": "", "description": ""}

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
