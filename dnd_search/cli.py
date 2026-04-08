"""Main CLI entry point for dnd-search."""

import concurrent.futures
import logging
import sys
from collections.abc import Mapping
from typing import Any

import click
from rich.console import Console

from dnd_search import cache, formatters, logger as log_setup, scraper

console = Console()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared options
# ---------------------------------------------------------------------------
def _common_options(f):
    """Decorator that attaches shared options to a command."""
    f = click.option(
        "--limit",
        default=0,
        metavar="N",
        help="Limit number of results (0 = no limit).",
    )(f)
    f = click.option(
        "--detail",
        "-d",
        is_flag=True,
        help="Fetch and show full detail for each result.",
    )(f)
    f = click.option(
        "--output",
        "-o",
        "fmt",
        type=click.Choice(
            ["table", "text", "json", "markdown", "plain"], case_sensitive=False
        ),
        default="table",
        show_default=True,
        help="Output format (table=rich, text=compact, markdown=PHB md, plain=PHB text).",
    )(f)
    return f


def _validate_results(items: list, entity: str) -> bool:
    if not items:
        console.print(f"[yellow]No {entity} found matching your criteria.[/yellow]")
        return False
    return True


def _find_one(items: list, name: str, entity: str):
    """Resolve a name to exactly one item; print a helpful error otherwise.

    Resolution order:
      1. Exact case-insensitive match (multiple → error)
      2. Partial case-insensitive match (multiple → list candidates + error)
      3. No match → error
    Returns the matched item, or None on failure.
    """
    exact = [i for i in items if i.name.lower() == name.lower()]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        console.print(f"[yellow]Multiple {entity}s share the name '{name}':[/yellow]")
        for item in exact:
            console.print(f"  • {item.name}")
        console.print("[dim]Try a more specific name.[/dim]")
        return None

    partial = [i for i in items if name.lower() in i.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) == 0:
        console.print(f"[red]{entity.title()} not found:[/red] {name!r}")
        return None

    console.print(
        f"[yellow]'{name}' matches multiple {entity}s — be more specific:[/yellow]"
    )
    for item in partial[:12]:
        console.print(f"  • {item.name}")
    if len(partial) > 12:
        console.print(f"  [dim]… and {len(partial) - 12} more[/dim]")
    return None


_SINGULAR_FMT = click.Choice(
    ["table", "json", "markdown", "plain"], case_sensitive=False
)


# ---------------------------------------------------------------------------
# Root command group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--debug", is_flag=True, default=False, help="Enable debug output.")
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Increase verbosity. Use up to three times (-v, -vv, -vvv).",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Bypass the local cache and always fetch fresh data.",
)
@click.pass_context
def main(ctx: click.Context, debug: bool, verbose: int, no_cache: bool) -> None:
    """Search D&D 5e 2014 content from dnd5e.wikidot.com.

    \b
    Verbosity levels:
      (none)  warnings and errors only
      -v      informational messages
      -vv     debug messages
      -vvv    debug + HTTP tracing

    \b
    Examples:
      dnd-search spells --level 3 --school evocation
      dnd-search classes --name fighter
      dnd-search subclasses --class rogue
      dnd-search feats --name "war caster"
      dnd-search races
      dnd-search items --rarity legendary
      dnd-search cache clear
    """
    log_setup.setup(verbosity=verbose, debug=debug)
    ctx.ensure_object(dict)
    ctx.obj["no_cache"] = no_cache


# ---------------------------------------------------------------------------
# Spells command
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--name", "-n", default="", help="Filter by name (partial, case-insensitive)."
)
@click.option(
    "--level",
    "-l",
    "spell_level",
    default=None,
    type=int,
    help="Filter by spell level (0=cantrip, 1-9).",
)
@click.option(
    "--school", "-s", default="", help="Filter by school (e.g. evocation, abjuration)."
)
@click.option(
    "--class",
    "-c",
    "spell_class",
    default="",
    help="Filter by class name (e.g. wizard, cleric).",
)
@click.option("--ritual", is_flag=True, default=False, help="Show only ritual spells.")
@click.option(
    "--concentration",
    is_flag=True,
    default=False,
    help="Show only concentration spells.",
)
@_common_options
@click.pass_context
def spells(
    ctx: click.Context,
    name: str,
    spell_level: int | None,
    school: str,
    spell_class: str,
    ritual: bool,
    concentration: bool,
    fmt: str,
    detail: bool,
    limit: int,
) -> None:
    """List D&D 5e spells.

    \b
    Examples:
      dnd-search spells
      dnd-search spells --name fireball
      dnd-search spells --level 3 --school evocation
      dnd-search spells --class wizard --concentration
      dnd-search spells --ritual --output markdown
      dnd-search spells --name "magic missile" --detail
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        results = scraper.fetch_spells(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if name:
        results = [s for s in results if name.lower() in s.name.lower()]
    if spell_level is not None:
        results = [s for s in results if s.level == spell_level]
    if school:
        results = [s for s in results if school.lower() in s.school.lower()]
    if ritual:
        results = [s for s in results if s.ritual]
    if concentration:
        results = [s for s in results if s.concentration]
    if spell_class:
        # Fetch the class-specific spell list to get spell names for cross-reference
        try:
            class_spells = scraper.fetch_spells_for_class(
                spell_class.lower(), use_cache
            )
            class_spell_names = {s.lower() for s in class_spells}
            results = [s for s in results if s.name.lower() in class_spell_names]
        except RuntimeError as e:
            logger.warning(f"Could not fetch class spell list: {e}")
            results = []

    results = results[:limit] if limit > 0 else results
    if not _validate_results(results, "spells"):
        return

    if fmt == "json":
        if detail:

            def _enrich_spell(spell):
                d = (
                    scraper.fetch_spell_detail(spell.url, use_cache)
                    if spell.url
                    else {}
                )
                spell.description = d.get("description", "")
                spell.source = d.get("source", "")

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=scraper.MAX_WORKERS
            ) as pool:
                list(pool.map(_enrich_spell, results))
        formatters.output_json(results)
        return

    # Fetch detail for single-result detail view (all non-json formats)
    detail_data: Mapping[str, Any] = {}
    if detail and len(results) == 1 and results[0].url:
        detail_data = scraper.fetch_spell_detail(results[0].url, use_cache)

    if fmt == "markdown":
        if detail and len(results) == 1:
            formatters.format_spell_detail_markdown(results[0], detail_data)
        else:
            formatters.format_spells_markdown(results)
    elif fmt == "plain":
        if detail and len(results) == 1:
            formatters.format_spell_detail_plain(results[0], detail_data)
        else:
            formatters.format_spells_plain(results)
    elif detail and len(results) == 1:
        formatters.format_spell_detail(results[0], detail_data)
    elif fmt == "text":
        formatters.format_spells_text(results)
    else:
        formatters.format_spells_table(results, show_url=detail)


# ---------------------------------------------------------------------------
# Classes command
# ---------------------------------------------------------------------------


@main.command("classes")
@click.option(
    "--name", "-n", default="", help="Filter by name (partial, case-insensitive)."
)
@_common_options
@click.pass_context
def classes(ctx: click.Context, name: str, fmt: str, detail: bool, limit: int) -> None:
    """List D&D 5e classes.

    \b
    Examples:
      dnd-search classes
      dnd-search classes --name fighter
      dnd-search classes --detail
      dnd-search classes --output Markdown
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        results = scraper.fetch_classes(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if name:
        results = [c for c in results if name.lower() in c.name.lower()]

    results = results[:limit] if limit > 0 else results
    if not _validate_results(results, "classes"):
        return

    # Populate hit_die / primary_ability / saving_throws when --detail is set
    if detail:

        def _enrich(cls):
            d = scraper.fetch_class_detail(cls.url, use_cache) if cls.url else {}
            cls.hit_die = d.get("hit_die", "")
            cls.primary_ability = d.get("primary_ability", "")
            cls.saving_throws = d.get("saving_throws", "")
            cls.description = d.get("description", "")

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=scraper.MAX_WORKERS
        ) as pool:
            list(pool.map(_enrich, results))

    if fmt == "json":
        formatters.output_json(results)
        return

    # When --detail and single result, re-fetch detail (hits parsed cache, negligible cost)
    detail_data: Mapping[str, Any] = {}
    if detail and len(results) == 1 and results[0].url:
        detail_data = scraper.fetch_class_detail(results[0].url, use_cache)

    if fmt == "markdown":
        if detail and len(results) == 1:
            formatters.format_class_detail_markdown(results[0], detail_data)
        else:
            formatters.format_classes_markdown(results)
    elif fmt == "plain":
        if detail and len(results) == 1:
            formatters.format_class_detail_plain(results[0], detail_data)
        else:
            formatters.format_classes_plain(results)
    elif detail and len(results) == 1:
        formatters.format_class_detail(results[0], detail_data)
    elif fmt == "text":
        formatters.format_classes_text(results)
    else:
        formatters.format_classes_table(results, show_detail=detail)


# ---------------------------------------------------------------------------
# Subclasses command
# ---------------------------------------------------------------------------


@main.command("subclasses")
@click.option(
    "--name", "-n", default="", help="Filter by name (partial, case-insensitive)."
)
@click.option(
    "--class",
    "-c",
    "parent_class",
    default="",
    help="Filter by parent class (e.g. fighter, wizard).",
)
@click.option("--source", default="", help="Filter by source book (partial match).")
@click.option(
    "--sort",
    "-s",
    "sort_by",
    type=click.Choice(["name", "class"], case_sensitive=False),
    default=None,
    help="Sort results by name or class.",
)
@_common_options
@click.pass_context
def subclasses(
    ctx: click.Context,
    name: str,
    parent_class: str,
    source: str,
    sort_by: str | None,
    fmt: str,
    detail: bool,
    limit: int,
) -> None:
    """List D&D 5e subclasses across all classes.

    \b
    Examples:
      dnd-search subclasses
      dnd-search subclasses --class rogue
      dnd-search subclasses --name totem
      dnd-search subclasses --source "Tasha's" --sort name
      dnd-search subclasses --class fighter --detail
      dnd-search subclasses --sort class --output markdown
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        results = scraper.fetch_subclasses(
            class_name=parent_class if parent_class else None,
            use_cache=use_cache,
        )
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if name:
        results = [s for s in results if name.lower() in s.name.lower()]
    if source:
        results = [s for s in results if source.lower() in s.source.lower()]
    if sort_by == "name":
        results = sorted(results, key=lambda s: s.name.lower())
    elif sort_by == "class":
        results = sorted(
            results, key=lambda s: (s.parent_class.lower(), s.name.lower())
        )

    results = results[:limit] if limit > 0 else results
    if not _validate_results(results, "subclasses"):
        return

    if fmt == "json":
        formatters.output_json(results)
        return

    if fmt == "markdown":
        formatters.format_subclasses_markdown(results)
    elif fmt == "plain":
        formatters.format_subclasses_plain(results)
    elif fmt == "text":
        formatters.format_subclasses_text(results)
    else:
        formatters.format_subclasses_table(results, show_url=detail)


# ---------------------------------------------------------------------------
# Feats command
# ---------------------------------------------------------------------------


@main.command("feats")
@click.option(
    "--name", "-n", default="", help="Filter by name (partial, case-insensitive)."
)
@click.option("--prerequisite", "-p", default="", help="Filter by prerequisite text.")
@click.option("--source", default="", help="Filter by source book (partial match).")
@_common_options
@click.pass_context
def feats(
    ctx: click.Context,
    name: str,
    prerequisite: str,
    source: str,
    fmt: str,
    detail: bool,
    limit: int,
) -> None:
    """List D&D 5e feats.

    \b
    Examples:
      dnd-search feats
      dnd-search feats --name "war caster"
      dnd-search feats --prerequisite "spellcasting"
      dnd-search feats --source "Tasha's"
      dnd-search feats --name alert --detail
      dnd-search feats --output markdown
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        results = scraper.fetch_feats(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if name:
        results = [f for f in results if name.lower() in f.name.lower()]
    if prerequisite:
        results = [
            f for f in results if prerequisite.lower() in f.prerequisites.lower()
        ]
    if source:
        results = [f for f in results if source.lower() in f.source.lower()]

    results = results[:limit] if limit > 0 else results
    if not _validate_results(results, "feats"):
        return

    if fmt == "json":
        if detail:

            def _enrich_feat(feat):
                d = scraper.fetch_feat_detail(feat.url, use_cache) if feat.url else {}
                feat.description = d.get("description", "")
                if not feat.source:
                    feat.source = d.get("source", "")

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=scraper.MAX_WORKERS
            ) as pool:
                list(pool.map(_enrich_feat, results))
        formatters.output_json(results)
        return

    detail_data: Mapping[str, Any] = {}
    if detail and len(results) == 1 and results[0].url:
        detail_data = scraper.fetch_feat_detail(results[0].url, use_cache)

    if fmt == "markdown":
        if detail and len(results) == 1:
            formatters.format_feat_detail_markdown(results[0], detail_data)
        else:
            formatters.format_feats_markdown(results)
    elif fmt == "plain":
        if detail and len(results) == 1:
            formatters.format_feat_detail_plain(results[0], detail_data)
        else:
            formatters.format_feats_plain(results)
    elif detail and len(results) == 1:
        formatters.format_feat_detail(results[0], detail_data)
    elif fmt == "text":
        formatters.format_feats_text(results)
    else:
        formatters.format_feats_table(results, show_url=detail)


# ---------------------------------------------------------------------------
# Races command
# ---------------------------------------------------------------------------


@main.command("races")
@click.option(
    "--name", "-n", default="", help="Filter by name (partial, case-insensitive)."
)
@click.option(
    "--size", "-s", default="", help="Filter by size (tiny/small/medium/large)."
)
@click.option("--source", default="", help="Filter by source book (partial match).")
@click.option(
    "--subrace",
    "-S",
    default="",
    help="Filter by subrace name (partial, case-insensitive).",
)
@_common_options
@click.pass_context
def races(
    ctx: click.Context,
    name: str,
    size: str,
    source: str,
    subrace: str,
    fmt: str,
    detail: bool,
    limit: int,
) -> None:
    """List D&D 5e races.

    \b
    Examples:
      dnd-search races
      dnd-search races --name elf
      dnd-search races --size small
      dnd-search races --subrace "dark elf"
      dnd-search races --source "Mordenkainen's"
      dnd-search races --name dwarf --detail
      dnd-search races --output markdown
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        results = scraper.fetch_races(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if name:
        results = [r for r in results if name.lower() in r.name.lower()]
    if size:
        results = [r for r in results if size.lower() in r.size.lower()]
    if source:
        results = [r for r in results if source.lower() in r.source.lower()]
    if subrace:

        def _has_subrace(race):
            if not race.url:
                return False
            d = scraper.fetch_race_detail(race.url, use_cache)
            return any(
                subrace.lower() in s["name"].lower() for s in d.get("subraces", [])
            )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=scraper.MAX_WORKERS
        ) as pool:
            matches = list(pool.map(_has_subrace, results))
        results = [r for r, match in zip(results, matches) if match]

    results = results[:limit] if limit > 0 else results
    if not _validate_results(results, "races"):
        return

    if fmt == "json":
        if detail:
            for race in results:
                d = scraper.fetch_race_detail(race.url, use_cache) if race.url else {}
                race.description = d.get("description", "")
                if not race.source:
                    race.source = d.get("source", "")
        formatters.output_json(results)
        return

    detail_data: Mapping[str, Any] = {}
    if detail and len(results) == 1 and results[0].url:
        detail_data = scraper.fetch_race_detail(results[0].url, use_cache)

    if fmt == "markdown":
        if detail and len(results) == 1:
            formatters.format_race_detail_markdown(results[0], detail_data)
        else:
            formatters.format_races_markdown(results)
    elif fmt == "plain":
        if detail and len(results) == 1:
            formatters.format_race_detail_plain(results[0], detail_data)
        else:
            formatters.format_races_plain(results)
    elif detail and len(results) == 1:
        formatters.format_race_detail(results[0], detail_data)
    elif fmt == "text":
        formatters.format_races_text(results)
    else:
        formatters.format_races_table(results, show_url=detail)


# ---------------------------------------------------------------------------
# Items command
# ---------------------------------------------------------------------------


@main.command("items")
@click.option(
    "--name", "-n", default="", help="Filter by name (partial, case-insensitive)."
)
@click.option(
    "--type",
    "-t",
    "item_type",
    default="",
    help="Filter by item type (e.g. weapon, armor, wondrous).",
)
@click.option(
    "--rarity",
    "-r",
    default="",
    help="Filter by rarity (common/uncommon/rare/very rare/legendary/artifact).",
)
@click.option(
    "--attunement",
    "-a",
    is_flag=True,
    default=False,
    help="Show only items that require attunement.",
)
@click.option("--source", default="", help="Filter by source book (partial match).")
@_common_options
@click.pass_context
def items(
    ctx: click.Context,
    name: str,
    item_type: str,
    rarity: str,
    attunement: bool,
    source: str,
    fmt: str,
    detail: bool,
    limit: int,
) -> None:
    """List D&D 5e magic items.

    \b
    Examples:
      dnd-search items
      dnd-search items --name "bag of holding"
      dnd-search items --rarity legendary
      dnd-search items --type weapon --attunement
      dnd-search items --source "Dungeon Master's Guide"
      dnd-search items --name "vorpal" --detail
      dnd-search items --rarity rare --output markdown
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        results = scraper.fetch_items(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if name:
        results = [i for i in results if name.lower() in i.name.lower()]
    if item_type:
        results = [i for i in results if item_type.lower() in i.item_type.lower()]
    if rarity:
        results = [i for i in results if rarity.lower() in i.rarity.lower()]
    if attunement:
        results = [i for i in results if i.requires_attunement]
    if source:
        results = [i for i in results if source.lower() in i.source.lower()]

    results = results[:limit] if limit > 0 else results
    if not _validate_results(results, "items"):
        return

    if fmt == "json":
        if detail:

            def _enrich_item(item):
                d = scraper.fetch_item_detail(item.url, use_cache) if item.url else {}
                item.description = d.get("description", "")
                if not item.source:
                    item.source = d.get("source", "")

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=scraper.MAX_WORKERS
            ) as pool:
                list(pool.map(_enrich_item, results))
        formatters.output_json(results)
        return

    detail_data: Mapping[str, Any] = {}
    if detail and len(results) == 1 and results[0].url:
        detail_data = scraper.fetch_item_detail(results[0].url, use_cache)

    if fmt == "markdown":
        if detail and len(results) == 1:
            formatters.format_item_detail_markdown(results[0], detail_data)
        else:
            formatters.format_items_markdown(results)
    elif fmt == "plain":
        if detail and len(results) == 1:
            formatters.format_item_detail_plain(results[0], detail_data)
        else:
            formatters.format_items_plain(results)
    elif detail and len(results) == 1:
        formatters.format_item_detail(results[0], detail_data)
    elif fmt == "text":
        formatters.format_items_text(results)
    else:
        formatters.format_items_table(results, show_url=detail)


# ---------------------------------------------------------------------------
# Class detail command
# ---------------------------------------------------------------------------


@main.command("class")
@click.argument("class_name")
@click.option(
    "--min-level",
    "-m",
    default=1,
    type=click.IntRange(1, 20),
    show_default=True,
    help="Only show progression from this level onward.",
)
@click.option(
    "--max-level",
    "-M",
    default=20,
    type=click.IntRange(1, 20),
    show_default=True,
    help="Only show progression up to this level.",
)
@click.option(
    "--features/--no-features",
    default=True,
    show_default=True,
    help="Show or hide class feature descriptions.",
)
@click.option(
    "--feature",
    "-F",
    default="",
    help="Filter feature descriptions by name (partial match).",
)
@click.option(
    "--subclasses/--no-subclasses",
    "show_subclasses",
    default=True,
    show_default=True,
    help="Show or hide the subclass list.",
)
@click.option(
    "--only-table", is_flag=True, default=False, help="Show only the progression table."
)
@click.option(
    "--only-subclasses",
    is_flag=True,
    default=False,
    help="Show only the subclass list.",
)
@click.option(
    "--only-features", is_flag=True, default=False, help="Show only the class features."
)
@click.option(
    "--only-header", is_flag=True, default=False, help="Show only the class overview panel."
)
@click.option(
    "--output",
    "-o",
    "fmt",
    type=click.Choice(["table", "json", "markdown", "plain"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format (table=rich, markdown=PHB md, plain=PHB text).",
)
@click.pass_context
def class_info(
    ctx: click.Context,
    class_name: str,
    min_level: int,
    max_level: int,
    features: bool,
    feature: str,
    show_subclasses: bool,
    only_table: bool,
    only_subclasses: bool,
    only_features: bool,
    only_header: bool,
    fmt: str,
) -> None:
    """Show class features and subclasses for a single class.

    \b
    Examples:
      dnd-search class fighter
      dnd-search class wizard --min-level 5 --max-level 10
      dnd-search class rogue --feature "sneak attack"
      dnd-search class cleric --no-features
      dnd-search class fighter --only-table
      dnd-search class paladin --only-subclasses
      dnd-search class druid --only-features
      dnd-search class barbarian --only-header
      dnd-search class barbarian --output json
    """
    use_cache = not ctx.obj["no_cache"]

    valid = [
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
    slug = class_name.lower().strip()
    if slug not in valid:
        console.print(
            f"[red]Unknown class:[/red] {class_name!r}\n"
            f"Valid classes: {', '.join(valid)}"
        )
        sys.exit(1)

    try:
        data = scraper.fetch_class_features(slug, use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not data:
        console.print(f"[yellow]No data found for class '{class_name}'.[/yellow]")
        return

    # Resolve which sections to show. --only-* flags take priority over the
    # boolean --features/--no-features and --subclasses/--no-subclasses flags.
    using_only = only_table or only_subclasses or only_features or only_header
    show_table = only_table if using_only else True
    show_features_section = only_features if using_only else features
    show_subclasses_section = only_subclasses if using_only else show_subclasses

    if fmt == "json":
        import json

        print(json.dumps(data, indent=2))
        return

    if fmt == "markdown":
        formatters.format_class_markdown(
            data,
            min_level=min_level,
            max_level=max_level,
            show_table=show_table,
            show_features=show_features_section,
            feature_filter=feature,
            show_subclasses=show_subclasses_section,
        )
        return

    if fmt == "plain":
        formatters.format_class_plain(
            data,
            min_level=min_level,
            max_level=max_level,
            show_table=show_table,
            show_features=show_features_section,
            feature_filter=feature,
            show_subclasses=show_subclasses_section,
        )
        return

    # Rich table output — header panel shown unless a different --only-* flag is set
    if not using_only or only_header:
        class_detail = scraper.fetch_class_detail(
            f"{scraper.BASE_URL}/{slug}", use_cache
        )
        formatters.format_class_header_panel(slug, class_detail)
        console.print()

    if only_header:
        return

    if show_table:
        formatters.format_class_progression(
            data, min_level=min_level, max_level=max_level
        )
        console.print()

    if show_features_section:
        console.print(
            "[bold]Class Features[/bold] — [dim]use --no-features to hide[/dim]"
        )
        console.print()
        formatters.format_class_features(data, name_filter=feature, show_body=True)
    elif not using_only:
        console.print(
            "[bold]Class Features[/bold] [dim](names only — use --features to see descriptions)[/dim]"
        )
        formatters.format_class_features(data, name_filter=feature, show_body=False)

    if show_subclasses_section and data.get("subclasses"):
        if show_table or show_features_section:
            console.print()
        formatters.format_class_subclasses(data)


# ---------------------------------------------------------------------------
# Singular lookup commands
# ---------------------------------------------------------------------------


@main.command("spell")
@click.argument("name")
@click.option(
    "--output",
    "-o",
    "fmt",
    type=_SINGULAR_FMT,
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def spell_cmd(ctx: click.Context, name: str, fmt: str) -> None:
    """Display the full entry for a single spell.

    \b
    NAME may be an exact or partial spell name.

    \b
    Examples:
      dnd-search spell fireball
      dnd-search spell "magic missile" --output markdown
      dnd-search spell "eldritch blast" --output plain
      dnd-search spell identify --output json
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        all_spells = scraper.fetch_spells(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    spell = _find_one(all_spells, name, "spell")
    if spell is None:
        sys.exit(1)

    detail: Mapping[str, Any] = (
        scraper.fetch_spell_detail(spell.url, use_cache) if spell.url else {}
    )

    if fmt == "json":
        spell.description = detail.get("description", "")
        spell.source = detail.get("source", "")
        spell.classes = detail.get("classes", [])
        formatters.output_json([spell])
    elif fmt == "markdown":
        formatters.format_spell_detail_markdown(spell, detail)
    elif fmt == "plain":
        formatters.format_spell_detail_plain(spell, detail)
    else:
        formatters.format_spell_detail(spell, detail)


@main.command("feat")
@click.argument("name")
@click.option(
    "--output",
    "-o",
    "fmt",
    type=_SINGULAR_FMT,
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def feat_cmd(ctx: click.Context, name: str, fmt: str) -> None:
    """Display the full entry for a single feat.

    \b
    NAME may be an exact or partial feat name.

    \b
    Examples:
      dnd-search feat "war caster"
      dnd-search feat actor --output markdown
      dnd-search feat grappler --output plain
      dnd-search feat alert --output json
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        all_feats = scraper.fetch_feats(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    feat = _find_one(all_feats, name, "feat")
    if feat is None:
        sys.exit(1)

    detail: Mapping[str, Any] = (
        scraper.fetch_feat_detail(feat.url, use_cache) if feat.url else {}
    )

    if fmt == "json":
        feat.description = detail.get("description", "")
        feat.source = feat.source or detail.get("source", "")
        formatters.output_json([feat])
    elif fmt == "markdown":
        formatters.format_feat_detail_markdown(feat, detail)
    elif fmt == "plain":
        formatters.format_feat_detail_plain(feat, detail)
    else:
        formatters.format_feat_detail(feat, detail)


@main.command("race")
@click.argument("name")
@click.option(
    "--subrace",
    "-S",
    default="",
    help="Filter to matching subraces (partial, case-insensitive).",
)
@click.option(
    "--output",
    "-o",
    "fmt",
    type=_SINGULAR_FMT,
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def race_cmd(ctx: click.Context, name: str, subrace: str, fmt: str) -> None:
    """Display the full entry for a single race/lineage.

    \b
    NAME may be an exact or partial race name.

    \b
    Examples:
      dnd-search race elf
      dnd-search race elf --subrace "dark elf"
      dnd-search race dwarf --subrace hill
      dnd-search race "half-orc" --output markdown
      dnd-search race tiefling --output plain
      dnd-search race dragonborn --output json
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        all_races = scraper.fetch_races(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    race = _find_one(all_races, name, "race")
    if race is None:
        sys.exit(1)

    detail: Mapping[str, Any] = (
        scraper.fetch_race_detail(race.url, use_cache) if race.url else {}
    )

    if subrace:
        matched = [
            s
            for s in detail.get("subraces", [])
            if subrace.lower() in s["name"].lower()
        ]
        if not matched:
            console.print(
                f"[red]No subraces found matching[/red] {subrace!r} [red]for[/red] {race.name}"
            )
            sys.exit(1)
        detail = {**detail, "subraces": matched}

    if fmt == "json":
        race.description = detail.get("description", "")
        race.source = race.source or detail.get("source", "")
        formatters.output_json([race])
    elif fmt == "markdown":
        formatters.format_race_detail_markdown(race, detail)
    elif fmt == "plain":
        formatters.format_race_detail_plain(race, detail)
    else:
        formatters.format_race_detail(race, detail)


@main.command("subclass")
@click.argument("name")
@click.option(
    "--output",
    "-o",
    "fmt",
    type=_SINGULAR_FMT,
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def subclass_cmd(ctx: click.Context, name: str, fmt: str) -> None:
    """Display the full entry for a single subclass.

    \b
    NAME may be an exact or partial subclass name.

    \b
    Examples:
      dnd-search subclass "battle master"
      dnd-search subclass evocation --output markdown
      dnd-search subclass "arcane trickster" --output plain
      dnd-search subclass "oath of devotion" --output json
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        all_subclasses = scraper.fetch_subclasses(use_cache=use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    sub = _find_one(all_subclasses, name, "subclass")
    if sub is None:
        sys.exit(1)

    detail: Mapping[str, Any] = (
        scraper.fetch_subclass_detail(sub.url, use_cache) if sub.url else {}
    )

    if fmt == "json":
        sub.description = detail.get("description", "")
        sub.source = sub.source or detail.get("source", "")
        formatters.output_json([sub])
    elif fmt == "markdown":
        formatters.format_subclass_detail_markdown(sub, detail)
    elif fmt == "plain":
        formatters.format_subclass_detail_plain(sub, detail)
    else:
        formatters.format_subclass_detail(sub, detail)


@main.command("item")
@click.argument("name")
@click.option(
    "--output",
    "-o",
    "fmt",
    type=_SINGULAR_FMT,
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def item_cmd(ctx: click.Context, name: str, fmt: str) -> None:
    """Display the full entry for a single magic item.

    \b
    NAME may be an exact or partial item name.

    \b
    Examples:
      dnd-search item "vorpal sword"
      dnd-search item "bag of holding" --output markdown
      dnd-search item "cloak of invisibility" --output plain
      dnd-search item "ring of protection" --output json
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        all_items = scraper.fetch_items(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    item = _find_one(all_items, name, "item")
    if item is None:
        sys.exit(1)

    detail: Mapping[str, Any] = (
        scraper.fetch_item_detail(item.url, use_cache) if item.url else {}
    )

    if fmt == "json":
        item.description = detail.get("description", "")
        item.source = item.source or detail.get("source", "")
        formatters.output_json([item])
    elif fmt == "markdown":
        formatters.format_item_detail_markdown(item, detail)
    elif fmt == "plain":
        formatters.format_item_detail_plain(item, detail)
    else:
        formatters.format_item_detail(item, detail)


# ---------------------------------------------------------------------------
# Cache management command
# ---------------------------------------------------------------------------


@main.group("cache")
def cache_group() -> None:
    """Manage the local response cache."""


@cache_group.command("clear")
def cache_clear() -> None:
    """Delete all cached responses."""
    count = cache.clear()
    console.print(f"[green]Cleared {count} cached response(s).[/green]")


@cache_group.command("prune")
def cache_prune() -> None:
    """Remove expired entries and trim cache to the size cap."""
    removed = cache.prune()
    console.print(f"[green]Pruned {removed} cache entry/entries.[/green]")


@cache_group.command("info")
def cache_info() -> None:
    """Show cache directory, entry count, disk usage, and age statistics."""
    from dnd_search.cache import CACHE_DIR, HTML_TTL, DETAIL_TTL, MAX_ENTRIES

    if not CACHE_DIR.exists():
        console.print("[yellow]Cache directory does not exist.[/yellow]")
        return

    s = cache.stats()

    def _fmt_age(seconds: float) -> str:
        if seconds < 3600:
            return f"{int(seconds // 60)}m"
        if seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"

    def _fmt_bytes(n: int) -> str:
        for unit in ("B", "KB", "MB"):
            if n < 1024:
                return f"{n:.0f} {unit}"
            n //= 1024
        return f"{n:.0f} GB"

    console.print(f"Cache directory: [cyan]{CACHE_DIR}[/cyan]")
    console.print(
        f"HTML TTL:        [dim]{_fmt_age(HTML_TTL)}[/dim]  [dim](DND_CACHE_TTL)[/dim]"
    )
    console.print(
        f"Detail TTL:      [dim]{_fmt_age(DETAIL_TTL)}[/dim]  [dim](DND_DETAIL_CACHE_TTL)[/dim]"
    )
    console.print(
        f"Max entries:     [dim]{MAX_ENTRIES}[/dim]  [dim](DND_CACHE_MAX_ENTRIES)[/dim]"
    )
    console.print(
        f"Entries:         [bright_green]{s['count']}[/bright_green]"
        + (f"  ([yellow]{s['expired']} expired[/yellow])" if s["expired"] else "")
    )
    console.print(f"Disk usage:      [dim]{_fmt_bytes(s['bytes'])}[/dim]")
    if s["count"]:
        console.print(f"Oldest entry:    [dim]{_fmt_age(s['oldest_age'])} ago[/dim]")
        console.print(f"Newest entry:    [dim]{_fmt_age(s['newest_age'])} ago[/dim]")


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


@main.command("misc")
@click.argument("name", default="")
@click.option(
    "--feature", "-f", default="", help="Filter features by name (partial match)."
)
@click.option(
    "--output",
    "-o",
    "fmt",
    type=click.Choice(
        ["table", "text", "json", "markdown", "plain"], case_sensitive=False
    ),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def misc(ctx: click.Context, name: str, feature: str, fmt: str) -> None:
    """List class quick links (invocations, infusions, maneuvers, etc.).

    \b
    Examples:
      dnd-search misc
      dnd-search misc "eldritch invocations"
      dnd-search misc "eldritch invocations" --feature "agonizing blast"
      dnd-search misc infusions --output markdown
    """
    use_cache = not ctx.obj["no_cache"]
    try:
        all_misc = scraper.fetch_misc_links(use_cache)
        homebrew = scraper.fetch_homebrew_hrefs(use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    all_misc = [
        m for m in all_misc if m.url not in {scraper.BASE_URL + h for h in homebrew}
    ]

    if not name:
        if not _validate_results(all_misc, "misc links"):
            return
        if fmt == "json":
            formatters.output_json(all_misc)
        elif fmt == "markdown":
            formatters.format_misc_markdown(all_misc)
        elif fmt == "plain":
            formatters.format_misc_plain(all_misc)
        elif fmt == "text":
            formatters.format_misc_text(all_misc)
        else:
            formatters.format_misc_table(all_misc)
        return

    matches = [m for m in all_misc if name.lower() in m.name.lower()]
    if not matches:
        console.print(f"[yellow]No misc link matching '{name}'.[/yellow]")
        sys.exit(1)
    if len(matches) > 1:
        names = ", ".join(m.name for m in matches)
        console.print(f"[yellow]Multiple matches: {names}. Be more specific.[/yellow]")
        sys.exit(1)

    link = matches[0]
    try:
        features = scraper.fetch_misc_detail(link.url, use_cache)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if feature:
        features = [f for f in features if feature.lower() in f.get("name", "").lower()]
        if not features:
            console.print(
                f"[yellow]No feature matching '{feature}' in {link.name}.[/yellow]"
            )
            sys.exit(1)

    if fmt == "json":
        formatters.output_json(features)
    elif fmt == "markdown":
        formatters.format_misc_detail_markdown(link, features)
    elif fmt == "plain":
        formatters.format_misc_detail_plain(link, features)
    else:
        formatters.format_misc_detail(link, features)
