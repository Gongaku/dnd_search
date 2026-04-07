# dnd-search

A command-line tool for looking up D&D 5e (2014) content — spells, classes, subclasses, feats, races, and magic items — pulled live from [dnd5e.wikidot.com](https://dnd5e.wikidot.com).

---

## Installation

**Linux / macOS**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

**Windows**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Requires Python 3.10 or later. On Windows, [Windows Terminal](https://aka.ms/terminal) or PowerShell 7+ is recommended for the best color output experience. The tool works in legacy `cmd.exe` but colors may be limited.

---

## Commands

Every command accepts `--help` for full option details.

### Listing commands

These search across all entries and support filtering, sorting, and output format selection.

| Command | What it lists |
|---|---|
| `dnd-search spells` | All spells |
| `dnd-search classes` | All classes |
| `dnd-search subclasses` | All subclasses across all classes |
| `dnd-search feats` | All feats |
| `dnd-search races` | All races and lineages |
| `dnd-search items` | All magic items |

**Common options (all listing commands)**

| Option | Description |
|---|---|
| `-n`, `--name TEXT` | Filter by name (partial match) |
| `--source TEXT` | Filter by source book (partial match) |
| `-o`, `--output FORMAT` | Output format: `table` (default), `text`, `json`, `markdown`, `plain` |
| `-d`, `--detail` | Fetch and show full description for each result |
| `--limit N` | Cap the number of results (0 = no limit) |

**Spell-specific filters**

```bash
dnd-search spells --level 3 --school evocation
dnd-search spells --class wizard --concentration
dnd-search spells --ritual
```

**Subclass-specific filters**

```bash
dnd-search subclasses --class rogue
dnd-search subclasses --sort class          # sort by parent class
```

**Item-specific filters**

```bash
dnd-search items --rarity legendary
dnd-search items --type weapon --attunement
```

**Race-specific filters**

```bash
dnd-search races --size small
dnd-search races --subrace "dark elf"
```

**Feat-specific filters**

```bash
dnd-search feats --prerequisite spellcasting
```

---

### Detail commands

Look up a single entry by name. Partial names work — if more than one result matches, you'll be prompted to be more specific.

```bash
dnd-search spell fireball
dnd-search spell "magic missile" --output markdown

dnd-search class fighter
dnd-search class wizard --min-level 5 --max-level 10
dnd-search class rogue --feature "sneak attack"
dnd-search class paladin --only-subclasses

dnd-search subclass "battle master"
dnd-search subclass evocation --output plain

dnd-search feat "war caster"
dnd-search feat alert --output json

dnd-search race elf
dnd-search race elf --subrace "dark elf"

dnd-search item "bag of holding"
dnd-search item "vorpal sword" --output markdown
```

---

### Output formats

| Format | Description |
|---|---|
| `table` | Rich colored table in the terminal (default) |
| `text` | Compact one-line-per-result list |
| `markdown` | PHB-style Markdown, suitable for piping to a file |
| `plain` | Plain text, no color, no special characters |
| `json` | Machine-readable JSON |

---

### Cache management

Responses are cached locally so repeat lookups are instant and work offline.

```bash
dnd-search cache info    # Show cache location, size, and age
dnd-search cache prune   # Remove expired entries and trim to size cap
dnd-search cache clear   # Delete everything
```

---

### Global options

These go before the command name:

```bash
dnd-search --no-cache spells --name fireball   # Always fetch fresh data
dnd-search -v spells                            # Show info messages
dnd-search -vv spells                           # Show debug messages
dnd-search -vvv spells                          # Debug + HTTP tracing
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DND_CACHE_TTL` | `604800` (7 days) | Seconds before raw HTML pages expire |
| `DND_DETAIL_CACHE_TTL` | `2592000` (30 days) | Seconds before parsed detail entries expire |
| `DND_CACHE_MAX_ENTRIES` | `500` | Maximum number of entries before oldest are evicted |

Example — force fresh data every hour:

```bash
DND_CACHE_TTL=3600 dnd-search spells --name fireball
```

---

## How it works

1. **Fetching** — `scraper.py` makes HTTP requests to dnd5e.wikidot.com and parses the HTML with BeautifulSoup.
2. **Caching** — Every response is stored as a gzip-compressed JSON file in `~/.cache/dnd-search/`. Cached pages avoid re-fetching on repeat runs. Two TTLs are used: a shorter one for raw HTML (which may update) and a longer one for parsed detail blobs (which are stable).
3. **Parallel enrichment** — When fetching full detail for many results at once (e.g. `--detail`), requests run in parallel using a thread pool capped at 8 workers.
4. **Formatting** — `formatters.py` renders results in the chosen output format. Rich panels and tables are used for terminal output; plain text and Markdown are printed directly for piping or copying.

### Module overview

| File | Responsibility |
|---|---|
| `cli.py` | Command definitions, argument parsing, orchestration |
| `scraper.py` | HTTP fetching, HTML parsing, data extraction |
| `formatters.py` | All output rendering (rich, markdown, plain, JSON) |
| `cache.py` | File-based response cache with TTL and size cap |
| `models.py` | Data classes and TypedDicts shared across modules |

---

## Data source

All content is sourced from [dnd5e.wikidot.com](https://dnd5e.wikidot.com), a community wiki covering the 2014 edition of D&D 5e. The tool does not store or redistribute any game content — it reads the wiki on demand and caches pages locally for performance.
