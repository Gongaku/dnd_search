"""Output formatters for D&D search results (rich table, Markdown, plain text)."""

import json
import logging
import re
import textwrap
from collections.abc import Mapping
from typing import Any, Literal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dnd_search.models import DnDClass, Feat, Item, MiscLink, Race, Spell, Subclass

logger = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _level_str(level: int) -> str:
    if level == 0:
        return "Cantrip"
    suffix = _ORDINAL_SUFFIX.get(level, "th")
    return f"{level}{suffix} Level"


def _rarity_color(rarity: str) -> str:
    colors = {
        "common": "white",
        "uncommon": "green",
        "rare": "blue",
        "very rare": "bright_magenta",
        "legendary": "bright_yellow",
        "artifact": "bright_red",
    }
    return colors.get(rarity.lower(), "white")


# ---------------------------------------------------------------------------
# JSON format
# ---------------------------------------------------------------------------
def _to_dict(obj: Any) -> dict:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
    return {}


def output_json(items: list) -> None:
    print(json.dumps([_to_dict(i) for i in items], indent=2))


# ---------------------------------------------------------------------------
# Shared plain-text / markdown helpers
# ---------------------------------------------------------------------------
_WRAP = 80


def _wrap(text: str, indent: str = "", hang: str | None = None) -> str:
    """Wrap to _WRAP chars. hang= overrides subsequent_indent (for hanging bullets)."""
    if not text:
        return ""
    subsequent = hang if hang is not None else indent
    return textwrap.fill(
        text, width=_WRAP, initial_indent=indent, subsequent_indent=subsequent
    )


_RE_MD_STRUCTURAL = re.compile(r"^(#{1,6} |[-*+] |\d+\. |[|>]|```)")
_RE_PARA_BREAK = re.compile(r"\n{2,}")


def _wrap_md(text: str) -> str:
    """Wrap markdown prose paragraphs to _WRAP chars.

    Structural markdown lines (headings, list items, tables, blockquotes,
    code fences) are left as-is to preserve their semantics.
    """
    if not text:
        return ""
    result = []
    for para in _RE_PARA_BREAK.split(text):
        stripped = para.strip()
        if not stripped:
            continue
        first_line = stripped.split("\n")[0]
        if _RE_MD_STRUCTURAL.match(first_line):
            result.append(para)
        else:
            # Prose: collapse internal newlines then rewrap
            flat = " ".join(
                line.strip() for line in stripped.split("\n") if line.strip()
            )
            result.append(textwrap.fill(flat, width=_WRAP))
    return "\n\n".join(result)


def _plain_table(headers: list[str], rows: list[list[str]], max_col: int = 36) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row[: len(headers)]):
            widths[i] = min(max_col, max(widths[i], len(str(cell))))
    pad = "  "
    lines = [
        pad.join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip(),
        pad.join("-" * widths[i] for i in range(len(headers))).rstrip(),
    ]
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append(
            pad.join(
                str(c).ljust(widths[i]) for i, c in enumerate(padded[: len(headers)])
            ).rstrip()
        )
    return "\n".join(lines)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    def _esc(s: str) -> str:
        return str(s).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(_esc(c) for c in padded[: len(headers)]) + " |")
    return "\n".join(lines)


def _plain_h1(text: str) -> str:
    u = text.upper()
    return u + "\n" + "=" * len(u)


def _plain_h2(text: str) -> str:
    u = text.upper()
    return u + "\n" + "-" * len(u)


def _phb_level(level: int) -> str:
    """Return PHB-style level string: 'cantrip', '1st-level', '3rd-level', …"""
    if level == 0:
        return "cantrip"
    return _level_str(level).lower().replace(" ", "-")


def _tags(spell: "Spell") -> str:
    parts = []
    if spell.ritual:
        parts.append("ritual")
    if spell.concentration:
        parts.append("concentration")
    return ", ".join(parts)


_ORDINAL_CHARS = "stndrh"


def _parse_level_int(cell: str) -> int | None:
    """Parse '1st', '2nd' … '20th' to int; return None on failure."""
    try:
        return int(cell.rstrip(_ORDINAL_CHARS).strip())
    except ValueError:
        return None


def _spell_tag_list(spell: "Spell") -> list[str]:
    """Return display-ready tag strings for ritual/concentration."""
    return (["Ritual"] if spell.ritual else []) + (
        ["Concentration"] if spell.concentration else []
    )


def _rich_field(label: str, value: str) -> str | None:
    """Return a rich-markup '[bold]Label:[/bold] value' line, or None if value is empty."""
    return f"[bold]{label}:[/bold] {value}" if value else None


def _render_blocks_rich(blocks: list, *, detect_dc: bool = False) -> list[str]:
    """Convert FeatureBlocks to rich-markup display lines."""
    parts: list[str] = []
    for i, block in enumerate(blocks):
        btype = block["type"]
        if btype == "heading":
            parts.append(f"[bold magenta]{block.get('text', '')}[/bold magenta]")
        elif btype == "paragraph":
            plain = block.get("text", "")
            low = plain.lower()
            if detect_dc and (
                low.startswith("spell save dc")
                or low.startswith("spell attack modifier")
            ):
                label, _, value = plain.partition("=")
                parts.append(
                    f"  [bold yellow]{label.strip()}[/bold yellow]"
                    + (
                        f" [dim]=[/dim] [italic]{value.strip()}[/italic]"
                        if value
                        else ""
                    )
                )
            else:
                parts.append(block.get("text_rich") or plain)
            if i < len(blocks) - 1:
                parts.append("")
        elif btype == "list":
            for item in block.get("items", []):
                parts.append(f"  • {item}")
        elif btype == "table":
            headers = block.get("headers", [])
            rows = block.get("rows", [])
            if headers:
                all_rows = [headers] + rows
                widths = [
                    max(len(r[c]) if c < len(r) else 0 for r in all_rows)
                    for c in range(len(headers))
                ]
                # Pad plain text then wrap in markup so tag chars don't skew alignment
                sep = "  ".join(
                    f"\n[bold cyan]{h:<{widths[i]}}[/bold cyan]"
                    for i, h in enumerate(headers)
                )
                parts.append(sep)
                for row in rows:
                    parts.append(
                        "  ".join(
                            f"{(row[i] if i < len(row) else ''):<{widths[i]}}"
                            for i in range(len(headers))
                        )
                    )
    return parts


_Fmt = Literal["markdown", "text"]


def _print_description(text: str, text_md: str | None, fmt: _Fmt) -> None:
    """Print a prose description block in the correct format."""
    if fmt == "markdown":
        print(_wrap_md(text_md or text))
    else:
        for para in text.split("\n\n"):
            if para.strip():
                print(_wrap(para.strip()))
                print()


def _fmt_trait(trait: dict, fmt: _Fmt) -> str:
    """Render a single trait line."""
    name, text = trait.get("name", ""), trait.get("text", "")
    if fmt == "markdown":
        return f"- **{name}.** {text}" if name else f"- {text}"
    label = f"{name}. " if name else ""
    return _wrap(label + text, indent="  * ", hang="    ")


def _print_blocks(blocks: list, fmt: _Fmt) -> None:
    """Print FeatureBlocks in the given format."""
    for block in blocks:
        btype = block["type"]
        if btype == "paragraph":
            if fmt == "markdown":
                print(_wrap_md(block.get("text_md") or block.get("text", "")))
            else:
                print(_wrap(block.get("text", "")))
            print()
        elif btype == "list":
            for item in block.get("items", []):
                if fmt == "markdown":
                    print(textwrap.fill(f"- {item}", width=_WRAP, subsequent_indent="  "))
                else:
                    print(_wrap(item, indent="  * ", hang="    "))
            print()
        elif btype == "table":
            headers = block.get("headers", [])
            rows = block.get("rows", [])
            if headers:
                if fmt == "markdown":
                    print("| " + " | ".join(headers) + " |")
                    print("| " + " | ".join("---" for _ in headers) + " |")
                    for row in rows:
                        print(
                            "| "
                            + " | ".join(
                                row[i] if i < len(row) else ""
                                for i in range(len(headers))
                            )
                            + " |"
                        )
                else:
                    all_rows = [headers] + rows
                    widths = [
                        max(len(r[c]) if c < len(r) else 0 for r in all_rows)
                        for c in range(len(headers))
                    ]
                    print(
                        "  ".join(f"{h:<{widths[i]}}" for i, h in enumerate(headers))
                    )
                    print("  ".join("-" * widths[i] for i in range(len(headers))))
                    for row in rows:
                        print(
                            "  ".join(
                                f"{(row[i] if i < len(row) else ''):<{widths[i]}}"
                                for i in range(len(headers))
                            )
                        )
                print()


# ---------------------------------------------------------------------------
# Spell formatters
# ---------------------------------------------------------------------------
def format_spells_table(spells: list[Spell], show_url: bool = False) -> None:
    if not spells:
        console.print("[yellow]No spells found.[/yellow]")
        return

    table = Table(
        title=f"Spells ({len(spells)} results)", show_lines=False, highlight=True
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Level", justify="center", style="bright_green")
    table.add_column("School", style="magenta")
    table.add_column("Casting Time", style="white")
    table.add_column("Range", style="white")
    table.add_column("Duration", style="white")
    table.add_column("Components", style="dim")
    table.add_column("Tags", style="yellow")
    if show_url:
        table.add_column("URL", style="dim")

    for spell in spells:
        tags = []
        if spell.ritual:
            tags.append("[R]")
        if spell.concentration:
            tags.append("[C]")

        row = [
            spell.name,
            _level_str(spell.level),
            spell.school,
            spell.casting_time,
            spell.range,
            spell.duration,
            spell.components,
            " ".join(tags),
        ]
        if show_url:
            row.append(f"[link={spell.url}]{spell.url}[/link]")
        table.add_row(*row)

    console.print(table)


def format_spell_detail(spell: Spell, detail: Mapping[str, Any]) -> None:
    title = f"[bold cyan]{spell.name}[/bold cyan]"
    spell_tag = ""
    if spell.ritual:
        ritual_tag = " [yellow](Ritual)[/yellow]"
        spell_tag += ritual_tag
    if spell.concentration:
        concentration_tag = " [bright_red](Concentration)[/bright_red]"
        spell_tag += concentration_tag

    lines = []
    if spell.url:
        lines.append(f"[bold]URL:[/bold]          [link={spell.url}]{spell.url}[/link]")
    if detail.get("source"):
        lines.append(f"[bold]Source:[/bold]       {detail['source']}")
    lines += [
        "",
        f"[bright_green]{_level_str(spell.level)}[/bright_green] [magenta]{spell.school}[/magenta]{spell_tag}",
        "",
        f"[bold]Casting Time:[/bold] {spell.casting_time}",
        f"[bold]Range:[/bold]        {spell.range}",
        f"[bold]Components:[/bold]   {spell.components}",
        f"[bold]Duration:[/bold]     {spell.duration}",
    ]
    if detail.get("description"):
        lines.append("")
        lines.append(detail["description"])
    if detail.get("at_higher_levels"):
        ahl = detail["at_higher_levels"]
        label, _, body = ahl.partition(".")
        lines.append("")
        lines.append(f"[bold italic]{label}.[/bold italic] {body.lstrip()}")
    if detail.get("classes"):
        lines.append("")
        lines.append(f"[bold]Spell Lists:[/bold] {', '.join(detail['classes'])}")

    console.print(
        Panel("\n".join(lines), title=title, border_style="cyan", title_align="center")
    )


# ---------------------------------------------------------------------------
# Class formatters
# ---------------------------------------------------------------------------
def format_classes_table(classes: list[DnDClass], show_detail: bool = False) -> None:
    if not classes:
        console.print("[yellow]No classes found.[/yellow]")
        return

    table = Table(
        title=f"Classes ({len(classes)} results)", show_lines=False, highlight=True
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    if show_detail:
        table.add_column("Hit Die", style="bright_green", justify="center")
        table.add_column("Saving Throws", style="white")
        table.add_column("Multiclass Requirement", style="magenta")

    for cls in classes:
        row = [cls.name]
        if show_detail:
            row += [cls.hit_die, cls.saving_throws, cls.primary_ability]
        table.add_row(*row)

    console.print(table)


def format_class_detail(cls: DnDClass, detail: Mapping[str, Any]) -> None:
    lines: list[str] = [
        line
        for line in [
            _rich_field("Hit Die", cls.hit_die),
            _rich_field("Saving Throws", cls.saving_throws),
            _rich_field("Primary Ability", cls.primary_ability),
            f"[bold]URL:[/bold] [link={cls.url}]{cls.url}[/link]" if cls.url else None,
        ]
        if line
    ]
    if detail.get("description"):
        lines.append("")
        lines.append(detail["description"])
    if detail.get("subclasses"):
        lines.append("")
        lines.append(f"[bold]Subclasses ({len(detail['subclasses'])}):[/bold]")
        for sub in detail["subclasses"]:
            src = f" [dim]({sub['source']})[/dim]" if sub.get("source") else ""
            lines.append(f"  • {sub['name']}{src}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]{cls.name}[/bold cyan]",
            border_style="cyan",
            title_align="center",
        )
    )


def format_class_header_panel(class_name: str, detail: Mapping[str, Any]) -> None:
    """Render the overview panel shown at the top of the 'class' command."""
    lines: list[str] = []

    if detail.get("description"):
        desc_lines = [
            ln
            for ln in detail["description"].splitlines()
            if "you gain the following" not in ln.lower()
        ]
        desc = "\n".join(desc_lines).strip()
        if desc:
            lines.append(desc)

    # Multiclass requirements
    primary = detail.get("primary_ability", "")
    if primary:
        lines.append("")
        lines.append("[bold magenta]Multiclass Requirements[/bold magenta]")
        lines.append(
            f"  You must have a {primary} to multiclass in and out of this class."
        )

    # Hit Points
    hit_die = detail.get("hit_die", "")
    hp1 = detail.get("hp_first_level", "")
    hpN = detail.get("hp_higher_levels", "")
    if hit_die or hp1 or hpN:
        lines.append("")
        lines.append("[bold magenta]Hit Points[/bold magenta]")
        if hit_die:
            lines.append(f"  [bold yellow]Hit Dice:[/bold yellow] {hit_die}")
        if hp1:
            lines.append(f"  [bold yellow]Hit Points at 1st Level:[/bold yellow] {hp1}")
        if hpN:
            lines.append(f"  [bold yellow]Hit Points at Higher Levels:[/bold yellow] {hpN}")

    # Proficiencies
    prof_fields = [
        ("Armor", detail.get("proficiency_armor", "")),
        ("Weapons", detail.get("proficiency_weapons", "")),
        ("Tools", detail.get("proficiency_tools", "")),
        ("Saving Throws", detail.get("saving_throws", "")),
        ("Skills", detail.get("proficiency_skills", "")),
    ]
    prof_lines = [(label, val) for label, val in prof_fields if val]
    if prof_lines:
        lines.append("")
        lines.append("[bold magenta]Proficiencies[/bold magenta]")
        for label, val in prof_lines:
            if label == "Skills":
                # Parse "Choose two from X, Y, and Z" into intro line + bullet list
                # Split on "from" to separate the preamble from the skill enumeration
                if " from " in val.lower():
                    idx = val.lower().index(" from ")
                    preamble = val[:idx].strip()
                    skill_str = val[idx + len(" from "):].strip().rstrip(".")
                    # Split on commas, strip "and" from last item
                    skills = [s.strip().lstrip("and ").strip() for s in skill_str.split(",")]
                    lines.append(f"  [bold yellow]{label}:[/bold yellow] {preamble} from:")
                    for skill in skills:
                        if skill:
                            lines.append(f"    • {skill}")
                else:
                    lines.append(f"  [bold yellow]{label}:[/bold yellow] {val}")
            else:
                lines.append(f"  [bold yellow]{label}:[/bold yellow] {val}")

    # Equipment
    equipment = detail.get("equipment", "")
    if equipment:
        lines.append("")
        lines.append("[bold magenta magenta]Equipment[/bold magenta]")
        for line in equipment.splitlines():
            lines.append(f"  {line}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]{class_name.title()}[/bold cyan]",
            border_style="cyan",
            title_align="center",
        )
    )


# ---------------------------------------------------------------------------
# Subclass formatters
# ---------------------------------------------------------------------------
def format_subclasses_table(subclasses: list[Subclass], show_url: bool = False) -> None:
    if not subclasses:
        console.print("[yellow]No subclasses found.[/yellow]")
        return

    table = Table(
        title=f"Subclasses ({len(subclasses)} results)",
        show_lines=False,
        highlight=True,
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Class", style="bright_green")
    table.add_column("Source", style="dim")
    if show_url:
        table.add_column("URL", style="dim")

    for sub in subclasses:
        row = [sub.name, sub.parent_class, sub.source]
        if show_url:
            row.append(f"[link={sub.url}]{sub.url}[/link]")
        table.add_row(*row)

    console.print(table)


def format_subclass_detail(sub: Subclass, detail: Mapping[str, Any]) -> None:
    src = detail.get("source") or sub.source
    lines: list[str] = [
        line
        for line in [
            f"[bold]URL:[/bold]    [link={sub.url}]{sub.url}[/link]"
            if sub.url
            else None,
            _rich_field("Source", src),
            _rich_field("Class", sub.parent_class),
        ]
        if line
    ]
    if detail.get("description"):
        lines += ["", detail["description"]]
    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]{sub.name}[/bold cyan]",
            border_style="cyan",
            title_align="center",
        )
    )

    for feat in detail.get("features", []):
        body_parts = _render_blocks_rich(feat.get("body", []))
        if feat.get("spell_table"):
            if body_parts:
                body_parts.append("")
            body_parts.append("[bold]Level        Spells[/bold]")
            for entry in feat["spell_table"]:
                body_parts.append(f"  {entry['level']:<12} {entry['spells']}")
        console.print(
            Panel(
                "\n".join(body_parts),
                title=f"[bold cyan]{feat['name']}[/bold cyan]",
                border_style="bright_black",
                padding=(0, 1),
                title_align="left",
            )
        )


# ---------------------------------------------------------------------------
# Feat formatters
# ---------------------------------------------------------------------------
def format_feats_table(feats: list[Feat], show_url: bool = False) -> None:
    if not feats:
        console.print("[yellow]No feats found.[/yellow]")
        return

    table = Table(
        title=f"Feats ({len(feats)} results)", show_lines=False, highlight=True
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Prerequisites", style="magenta")
    table.add_column("Source", style="dim")
    if show_url:
        table.add_column("URL", style="dim")

    for feat in feats:
        row = [feat.name, feat.prerequisites or "None", feat.source]
        if show_url:
            row.append(f"[link={feat.url}]{feat.url}[/link]")
        table.add_row(*row)

    console.print(table)


def format_feat_detail(feat: Feat, detail: Mapping[str, Any]) -> None:
    src = detail.get("source") or feat.source
    pre = detail.get("prerequisites") or feat.prerequisites or "None"
    lines: list[str] = [
        line
        for line in [
            f"[bold]URL:[/bold] [link={feat.url}]{feat.url}[/link]"
            if feat.url
            else None,
            _rich_field("Source", src),
            _rich_field("Prerequisites", pre),
        ]
        if line
    ]
    if detail.get("description"):
        lines.append("")
        lines.append(detail["description"])
    if detail.get("benefits"):
        lines.append("")
        for benefit in detail["benefits"]:
            lines.append(f"  • {benefit}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]{feat.name}[/bold cyan]",
            border_style="cyan",
            title_align="center",
        )
    )


# ---------------------------------------------------------------------------
# Race formatters
# ---------------------------------------------------------------------------
def format_races_table(races: list[Race], show_url: bool = False) -> None:
    if not races:
        console.print("[yellow]No races found.[/yellow]")
        return

    table = Table(
        title=f"Races ({len(races)} results)", show_lines=False, highlight=True
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Size", style="bright_green", justify="center")
    table.add_column("Speed", style="magenta", justify="center")
    table.add_column("Source", style="dim")
    if show_url:
        table.add_column("URL", style="dim")

    for race in races:
        row = [race.name, race.size, race.speed, race.source]
        if show_url:
            row.append(f"[link={race.url}]{race.url}[/link]")
        table.add_row(*row)

    console.print(table)


def _fmt_trait_rich(trait: dict) -> str:
    name = trait.get("name", "")
    text = trait.get("text", "")
    return f"  • [bold]{name}.[/bold] {text}" if name else f"  • {text}"


def format_race_detail(race: Race, detail: Mapping[str, Any]) -> None:
    src = detail.get("source") or race.source
    lines: list[str] = [
        line
        for line in [
            f"[bold]URL:[/bold] [link={race.url}]{race.url}[/link]"
            if race.url
            else None,
            _rich_field("Source", src),
            _rich_field("Size", race.size),
            _rich_field("Speed", race.speed),
        ]
        if line
    ]
    if detail.get("description"):
        lines.append("")
        lines.append(detail["description"])
    if detail.get("traits"):
        lines.append("")
        lines.append("[bold]Racial Traits[/bold]")
        for trait in detail["traits"]:
            lines.append(_fmt_trait_rich(trait))

    for subrace in detail.get("subraces", []):
        lines.append("")
        lines.append(f"[bold yellow]{subrace['name'].upper()}[/bold yellow]")
        sub_src = subrace.get("source", "")
        if sub_src and sub_src != src:
            lines.append(f"[dim]{sub_src}[/dim]")
        if subrace.get("description"):
            lines.append(subrace["description"])
        for trait in subrace.get("traits", []):
            lines.append(_fmt_trait_rich(trait))
        if subrace.get("spell_table"):
            lines.append("")
            lines.append("[bold]Level        Spells[/bold]")
            for entry in subrace["spell_table"]:
                lines.append(f"  {entry['level']:<12} {entry['spells']}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]{race.name}[/bold cyan]",
            border_style="cyan",
            title_align="center",
        )
    )


# ---------------------------------------------------------------------------
# Item formatters
# ---------------------------------------------------------------------------
def format_items_table(items: list[Item], show_url: bool = False) -> None:
    if not items:
        console.print("[yellow]No items found.[/yellow]")
        return

    table = Table(
        title=f"Magic Items ({len(items)} results)", show_lines=False, highlight=True
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Type", style="bright_green")
    table.add_column("Rarity", style="magenta")
    table.add_column("Attunement", justify="center", style="yellow")
    table.add_column("Source", style="dim")
    if show_url:
        table.add_column("URL", style="dim")

    for item in items:
        attune = "Yes" if item.requires_attunement else "No"
        rarity_color = _rarity_color(item.rarity)
        row = [
            item.name,
            item.item_type,
            f"[{rarity_color}]{item.rarity}[/{rarity_color}]",
            attune,
            item.source,
        ]
        if show_url:
            row.append(f"[link={item.url}]{item.url}[/link]")
        table.add_row(*row)

    console.print(table)


def format_item_detail(item: Item, detail: Mapping[str, Any]) -> None:
    src = item.source or detail.get("source", "")
    color = _rarity_color(item.rarity) if item.rarity else "white"
    attune = "Yes" if item.requires_attunement else "No"
    lines: list[str] = [
        line
        for line in [
            f"[bold]URL:[/bold] [link={item.url}]{item.url}[/link]"
            if item.url
            else None,
            _rich_field("Source", src),
            _rich_field("Type", item.item_type),
            f"[bold]Rarity:[/bold] [{color}]{item.rarity}[/{color}]"
            if item.rarity
            else None,
            f"[bold]Attunement:[/bold] {attune}",
        ]
        if line
    ]
    if detail.get("description"):
        lines.append("")
        lines.append(detail["description"])

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]{item.name}[/bold cyan]",
            border_style="cyan",
            title_align="center",
        )
    )


# ---------------------------------------------------------------------------
# Class feature formatters
# ---------------------------------------------------------------------------
# Columns that deserve a distinct color in the progression table
_COL_STYLES: dict[str, str] = {
    "level": "bold bright_green",
    "proficiency bonus": "bright_yellow",
    "features": "cyan",
    "cantrips known": "magenta",
    "spells known": "magenta",
    "spell slots": "bright_magenta",
    "slot level": "bright_magenta",
    "ki points": "bright_blue",
    "rage": "bright_red",
    "martial arts": "bright_red",
    "sneak attack": "bright_red",
    "unarmored movement": "bright_blue",
}

_RARITY_SUFFIXES = ("st", "nd", "rd", "th")


def _col_style(header: str) -> str:
    h = header.lower()
    for key, style in _COL_STYLES.items():
        if key in h:
            return style
    # Spell slot columns are single ordinals like "1st", "2nd" … "9th"
    if any(h.endswith(s) for s in _RARITY_SUFFIXES) and len(h) <= 3:
        return "bright_magenta"
    return "white"


def format_class_progression(
    data: Mapping[str, Any], min_level: int = 1, max_level: int = 20
) -> None:
    """Render the class level progression table."""
    class_name = data.get("class_name", "Class")
    headers = data.get("table_headers", [])
    rows = data.get("table_rows", [])

    if not headers or not rows:
        console.print(f"[yellow]No progression data found for {class_name}.[/yellow]")
        return

    # Filter rows to the requested level range
    filtered = []
    for row in rows:
        try:
            lvl = _parse_level_int(row[0])
        except IndexError:
            continue
        if lvl is None:
            continue
        if min_level <= lvl <= max_level:
            filtered.append((lvl, row))

    if not filtered:
        console.print("[yellow]No levels match the given range.[/yellow]")
        return

    title = f"[bold]{class_name} Progression"
    if min_level > 1 or max_level < 20:
        title += f" (Levels {min_level}–{max_level})"
    title += "[/bold]"

    table = Table(
        title=title, show_lines=True, highlight=True, border_style="bright_black"
    )

    for h in headers:
        center = h.lower() != "features"
        table.add_column(
            h,
            style=_col_style(h),
            justify="center" if center else "left",
            no_wrap=False,
        )

    for _, row in filtered:
        padded = row + ["—"] * (len(headers) - len(row))
        cells = padded[: len(headers)]
        # Replace empty cells with a dash for readability
        cells = [c if c else "—" for c in cells]
        table.add_row(*cells)

    console.print(table)


def format_class_features(
    data: Mapping[str, Any], name_filter: str = "", show_body: bool = True
) -> None:
    """Render class feature descriptions."""
    class_name = data.get("class_name", "Class")
    features = data.get("features", [])

    if not features:
        console.print(
            f"[yellow]No feature descriptions found for {class_name}.[/yellow]"
        )
        return

    if name_filter:
        features = [f for f in features if name_filter.lower() in f["name"].lower()]
        if not features:
            console.print(f"[yellow]No features matching '{name_filter}'.[/yellow]")
            return

    for feat in features:
        name = feat["name"]
        level = feat.get("level")
        level_str = f" [dim](unlocked at level {level})[/dim]" if level else ""

        if not show_body or not feat.get("body"):
            console.print(
                f"  [bold magenta]•[/bold magenta] [magenta]{name}[/magenta]{level_str}"
            )
            continue

        body_parts = _render_blocks_rich(feat.get("body", []), detect_dc=True)

        body = "\n".join(body_parts)
        title = f"[bold cyan]{name}[/bold cyan]{level_str}"
        console.print(
            Panel(
                body,
                title=title,
                border_style="bright_black",
                padding=(0, 1),
                title_align="left",
            )
        )


def format_class_subclasses(data: Mapping[str, Any]) -> None:
    """Render the subclass list from class data."""
    class_name = data.get("class_name", "Class")
    subclasses = data.get("subclasses", [])

    if not subclasses:
        return

    table = Table(
        title=f"{class_name} Subclasses", show_lines=False, border_style="bright_black"
    )
    table.add_column("Name", style="bold cyan")
    table.add_column("Source", style="dim")

    for sub in subclasses:
        table.add_row(sub["name"], sub.get("source", ""))

    console.print(table)


# ---------------------------------------------------------------------------
# Markdown formatters  (PHB-style)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Unified markdown + plain-text formatters
# ---------------------------------------------------------------------------

def _format_spells_list(spells: list[Spell], fmt: _Fmt) -> None:
    count = len(spells)
    title = f"Spells ({count} result{'s' if count != 1 else ''})"
    if fmt == "markdown":
        print(f"## {title}\n")
    else:
        print(_plain_h1(title))
        print()
    headers = ["Name", "Level", "School", "Casting Time",
               "Range", "Duration", "Components", "Tags"]
    rows = [
        [
            f"[{s.name}]({s.url})" if (fmt == "markdown" and s.url) else s.name,
            _phb_level(s.level), s.school, s.casting_time,
            s.range, s.duration, s.components, _tags(s),
        ]
        for s in spells
    ]
    print(_md_table(headers, rows) if fmt == "markdown" else _plain_table(headers, rows))


def format_spells_markdown(spells: list[Spell], detail_map: dict | None = None) -> None:
    _format_spells_list(spells, "markdown")


def format_spells_text(spells: list[Spell], detail_map: dict | None = None) -> None:
    _format_spells_list(spells, "text")


def _format_spell_detail(spell: Spell, detail: Mapping[str, Any], fmt: _Fmt) -> None:
    tags = _spell_tag_list(spell)
    lw = 14  # plain-text label column width
    if fmt == "markdown":
        tag_str = f" *({', '.join(tags)})*" if tags else ""
        school_line = f"*{_phb_level(spell.level)} {spell.school.lower()}*{tag_str}"
        title = f"[{spell.name}]({spell.url})" if spell.url else spell.name
        print(f"# {title}")
        print()
        if detail.get("source"):
            print(f"**Source:** {detail['source']}  ")
        print()
        print(school_line)
        print()
        print(f"**Casting Time:** {spell.casting_time}  ")
        print(f"**Range:** {spell.range}  ")
        print(f"**Components:** {spell.components}  ")
        print(f"**Duration:** {spell.duration}  ")
    else:
        tag_str = f"  [{', '.join(tags)}]" if tags else ""
        print(spell.name)
        print()
        if spell.url:
            print(f"{'URL:':<{lw}} {spell.url}")
        if detail.get("source"):
            print(f"{'Source:':<{lw}} {detail['source']}")
        print()
        print(f"{_phb_level(spell.level)} {spell.school.lower()}{tag_str}")
        print()
        print(f"{'Casting Time:':<{lw}} {spell.casting_time}")
        print(f"{'Range:':<{lw}} {spell.range}")
        print(f"{'Components:':<{lw}} {spell.components}")
        print(f"{'Duration:':<{lw}} {spell.duration}")
    print()
    if detail.get("description"):
        _print_description(
            detail["description"], detail.get("description_md"), fmt
        )
    if detail.get("at_higher_levels"):
        ahl_raw = detail.get("at_higher_levels_md") if fmt == "markdown" else None
        ahl = ahl_raw or detail["at_higher_levels"]
        label, _, body = ahl.partition(".")
        if fmt == "markdown":
            print(f"\n{_wrap_md(f'{label}.{body.lstrip()}')}")
        else:
            print(_wrap(f"{label}. {body.lstrip()}"))
            print()
    if detail.get("classes"):
        if fmt == "markdown":
            print(f"\n**Spell Lists:** {', '.join(detail['classes'])}")
        else:
            print(f"{'Spell Lists:':<{lw}} {', '.join(detail['classes'])}")


def format_spell_detail_markdown(spell: Spell, detail: Mapping[str, Any]) -> None:
    _format_spell_detail(spell, detail, "markdown")


def format_spell_detail_text(spell: Spell, detail: Mapping[str, Any]) -> None:
    _format_spell_detail(spell, detail, "text")


def _format_classes_list(classes: list[DnDClass], fmt: _Fmt) -> None:
    count = len(classes)
    title = f"Classes ({count} result{'s' if count != 1 else ''})"
    if fmt == "markdown":
        print(f"## {title}\n")
    else:
        print(_plain_h1(title))
        print()
    headers = ["Name", "Hit Die", "Primary Ability", "Saving Throws"]
    rows = [
        [
            f"[{c.name}]({c.url})" if (fmt == "markdown" and c.url) else c.name,
            c.hit_die, c.primary_ability, c.saving_throws,
        ]
        for c in classes
    ]
    print(_md_table(headers, rows) if fmt == "markdown" else _plain_table(headers, rows))


def format_classes_markdown(classes: list[DnDClass]) -> None:
    _format_classes_list(classes, "markdown")


def format_classes_text(classes: list[DnDClass]) -> None:
    _format_classes_list(classes, "text")


def _format_class_detail(cls: DnDClass, detail: Mapping[str, Any], fmt: _Fmt) -> None:
    if fmt == "markdown":
        print(f"# {cls.name}")
        print()
        if cls.hit_die:
            print(f"**Hit Die:** {cls.hit_die}  ")
        if cls.primary_ability:
            print(f"**Primary Ability:** {cls.primary_ability}  ")
        if cls.saving_throws:
            print(f"**Saving Throws:** {cls.saving_throws}  ")
        if cls.url:
            print(f"**Reference:** [{cls.url}]({cls.url})  ")
    else:
        print(_plain_h1(cls.name))
        print()
        if cls.hit_die:
            print(f"Hit Die:         {cls.hit_die}")
        if cls.primary_ability:
            print(f"Primary Ability: {cls.primary_ability}")
        if cls.saving_throws:
            print(f"Saving Throws:   {cls.saving_throws}")
    if detail.get("description"):
        print()
        _print_description(detail["description"], None, fmt)
    if detail.get("subclasses"):
        if fmt == "markdown":
            print("\n## Subclasses\n")
        else:
            print(_plain_h2("Subclasses"))
            print()
        headers = ["Name", "Source"]
        rows = [[s["name"], s.get("source", "")] for s in detail["subclasses"]]
        print(_md_table(headers, rows) if fmt == "markdown" else _plain_table(headers, rows))


def format_class_detail_markdown(cls: DnDClass, detail: Mapping[str, Any]) -> None:
    _format_class_detail(cls, detail, "markdown")


def format_class_detail_text(cls: DnDClass, detail: Mapping[str, Any]) -> None:
    _format_class_detail(cls, detail, "text")


def _format_subclasses_list(subclasses: list[Subclass], fmt: _Fmt) -> None:
    count = len(subclasses)
    title = f"Subclasses ({count} result{'s' if count != 1 else ''})"
    if fmt == "markdown":
        print(f"## {title}\n")
    else:
        print(_plain_h1(title))
        print()
    headers = ["Name", "Class", "Source"]
    rows = [
        [
            f"[{s.name}]({s.url})" if (fmt == "markdown" and s.url) else s.name,
            s.parent_class, s.source,
        ]
        for s in subclasses
    ]
    print(_md_table(headers, rows) if fmt == "markdown" else _plain_table(headers, rows))


def format_subclasses_markdown(subclasses: list[Subclass]) -> None:
    _format_subclasses_list(subclasses, "markdown")


def format_subclasses_text(subclasses: list[Subclass]) -> None:
    _format_subclasses_list(subclasses, "text")


def _format_subclass_detail(
    sub: Subclass, detail: Mapping[str, Any], fmt: _Fmt
) -> None:
    src = detail.get("source") or sub.source
    if fmt == "markdown":
        title = f"[{sub.name}]({sub.url})" if sub.url else sub.name
        print(f"# {title}\n")
        if src:
            print(f"**Source:** {src}  ")
        if sub.parent_class:
            print(f"**Class:** {sub.parent_class}  ")
    else:
        print(sub.name.upper())
        print("=" * len(sub.name))
        if sub.url:
            print(f"URL:    {sub.url}")
        if src:
            print(f"Source: {src}")
        if sub.parent_class:
            print(f"Class:  {sub.parent_class}")
        print()
    if detail.get("description"):
        print()
        _print_description(
            detail["description"], detail.get("description_md"), fmt
        )
    spell_tbl_fmt = _md_table if fmt == "markdown" else _plain_table
    for feat in detail.get("features", []):
        if fmt == "markdown":
            print(f"\n### {feat['name']}\n")
        else:
            print(_plain_h2(feat["name"]))
            print()
        _print_blocks(feat.get("body", []), fmt)
        if feat.get("spell_table"):
            print(
                spell_tbl_fmt(
                    ["Level", "Spells"],
                    [[e["level"], e["spells"]] for e in feat["spell_table"]],
                )
            )
            print()


def format_subclass_detail_markdown(sub: Subclass, detail: Mapping[str, Any]) -> None:
    _format_subclass_detail(sub, detail, "markdown")


def format_subclass_detail_text(sub: Subclass, detail: Mapping[str, Any]) -> None:
    _format_subclass_detail(sub, detail, "text")


def _format_feats_list(feats: list[Feat], fmt: _Fmt) -> None:
    count = len(feats)
    title = f"Feats ({count} result{'s' if count != 1 else ''})"
    if fmt == "markdown":
        print(f"## {title}\n")
    else:
        print(_plain_h1(title))
        print()
    headers = ["Name", "Prerequisites", "Source"]
    rows = [
        [
            f"[{f.name}]({f.url})" if (fmt == "markdown" and f.url) else f.name,
            f.prerequisites or "None", f.source,
        ]
        for f in feats
    ]
    print(_md_table(headers, rows) if fmt == "markdown" else _plain_table(headers, rows))


def format_feats_markdown(feats: list[Feat]) -> None:
    _format_feats_list(feats, "markdown")


def format_feats_text(feats: list[Feat]) -> None:
    _format_feats_list(feats, "text")


def _format_feat_detail(feat: Feat, detail: Mapping[str, Any], fmt: _Fmt) -> None:
    src = detail.get("source") or feat.source
    prereq = detail.get("prerequisites") or feat.prerequisites or "None"
    if fmt == "markdown":
        title = f"[{feat.name}]({feat.url})" if feat.url else feat.name
        print(f"# {title}\n")
        if src:
            print(f"**Source:** {src}  ")
        print(f"*Prerequisite: {prereq}*\n")
    else:
        print(feat.name)
        print("-" * len(feat.name))
        if feat.url:
            print(f"URL:          {feat.url}")
        if src:
            print(f"Source:       {src}")
        print(f"Prerequisite: {prereq}")
        print()
    if detail.get("description"):
        _print_description(
            detail["description"], detail.get("description_md"), fmt
        )
    if detail.get("benefits"):
        print()
        for benefit in detail["benefits"]:
            if fmt == "markdown":
                print(f"- {benefit}")
            else:
                print(_wrap(benefit, indent="  * ", hang="    "))
        if fmt == "text":
            print()


def format_feat_detail_markdown(feat: Feat, detail: Mapping[str, Any]) -> None:
    _format_feat_detail(feat, detail, "markdown")


def format_feat_detail_text(feat: Feat, detail: Mapping[str, Any]) -> None:
    _format_feat_detail(feat, detail, "text")


def _format_races_list(races: list[Race], fmt: _Fmt) -> None:
    count = len(races)
    title = f"Races ({count} result{'s' if count != 1 else ''})"
    if fmt == "markdown":
        print(f"## {title}\n")
    else:
        print(_plain_h1(title))
        print()
    headers = ["Name", "Size", "Speed", "Source"]
    rows = [
        [
            f"[{r.name}]({r.url})" if (fmt == "markdown" and r.url) else r.name,
            r.size, r.speed, r.source,
        ]
        for r in races
    ]
    print(_md_table(headers, rows) if fmt == "markdown" else _plain_table(headers, rows))


def format_races_markdown(races: list[Race]) -> None:
    _format_races_list(races, "markdown")


def format_races_text(races: list[Race]) -> None:
    _format_races_list(races, "text")


def _format_race_detail(race: Race, detail: Mapping[str, Any], fmt: _Fmt) -> None:
    src = detail.get("source") or race.source
    spell_tbl_fmt = _md_table if fmt == "markdown" else _plain_table
    if fmt == "markdown":
        title = f"[{race.name}]({race.url})" if race.url else race.name
        print(f"# {title}\n")
        if src:
            print(f"**Source:** {src}  ")
        if race.size:
            print(f"**Size:** {race.size}  ")
        if race.speed:
            print(f"**Speed:** {race.speed}  ")
    else:
        print(race.name.upper())
        print("=" * len(race.name))
        if race.url:
            print(f"URL:    {race.url}")
        if src:
            print(f"Source: {src}")
        if race.size:
            print(f"Size:   {race.size}")
        if race.speed:
            print(f"Speed:  {race.speed}")
        print()
    if detail.get("description"):
        print()
        _print_description(
            detail["description"], detail.get("description_md"), fmt
        )
    if detail.get("traits"):
        if fmt == "markdown":
            print("\n### Racial Traits\n")
        else:
            print("RACIAL TRAITS")
            print("-------------")
        for t in detail["traits"]:
            print(_fmt_trait(t, fmt))
        if fmt == "text":
            print()
    for subrace in detail.get("subraces", []):
        sub_name = subrace.get("name", "")
        sub_src = subrace.get("source", "")
        if fmt == "markdown":
            print(f"\n## {sub_name}")
            if sub_src and sub_src != src:
                print(f"*{sub_src}*\n")
        else:
            print(sub_name.upper())
            print("-" * len(sub_name))
            if sub_src and sub_src != src:
                print(f"Source: {sub_src}")
        if subrace.get("description"):
            print()
            _print_description(
                subrace["description"], subrace.get("description_md"), fmt
            )
        if subrace.get("traits"):
            if fmt == "markdown":
                print()
            for t in subrace["traits"]:
                print(_fmt_trait(t, fmt))
            if fmt == "text":
                print()
        if subrace.get("spell_table"):
            print()
            print(
                spell_tbl_fmt(
                    ["Level", "Spells"],
                    [[e["level"], e["spells"]] for e in subrace["spell_table"]],
                )
            )


def format_race_detail_markdown(race: Race, detail: Mapping[str, Any]) -> None:
    _format_race_detail(race, detail, "markdown")


def format_race_detail_text(race: Race, detail: Mapping[str, Any]) -> None:
    _format_race_detail(race, detail, "text")


def _format_items_list(items: list[Item], fmt: _Fmt) -> None:
    count = len(items)
    title = f"Magic Items ({count} result{'s' if count != 1 else ''})"
    if fmt == "markdown":
        print(f"## {title}\n")
    else:
        print(_plain_h1(title))
        print()
    headers = ["Name", "Type", "Rarity", "Attunement", "Source"]
    rows = [
        [
            f"[{i.name}]({i.url})" if (fmt == "markdown" and i.url) else i.name,
            i.item_type, i.rarity,
            "Yes" if i.requires_attunement else "No",
            i.source,
        ]
        for i in items
    ]
    print(_md_table(headers, rows) if fmt == "markdown" else _plain_table(headers, rows))


def format_items_markdown(items: list[Item]) -> None:
    _format_items_list(items, "markdown")


def format_items_text(items: list[Item]) -> None:
    _format_items_list(items, "text")


def _format_item_detail(item: Item, detail: Mapping[str, Any], fmt: _Fmt) -> None:
    src = item.source or detail.get("source", "")
    parts = [p for p in [item.item_type, item.rarity] if p]
    if item.requires_attunement:
        parts.append("requires attunement")
    if fmt == "markdown":
        title = f"[{item.name}]({item.url})" if item.url else item.name
        print(f"# {title}\n")
        if src:
            print(f"**Source:** {src}  ")
        if parts:
            print(f"*{', '.join(parts)}*\n")
    else:
        print(item.name)
        print("-" * len(item.name))
        if item.url:
            print(f"URL:    {item.url}")
        if src:
            print(f"Source: {src}")
        if parts:
            print(", ".join(parts))
        print()
    if detail.get("description"):
        _print_description(detail["description"], None, fmt)


def format_item_detail_markdown(item: Item, detail: Mapping[str, Any]) -> None:
    _format_item_detail(item, detail, "markdown")


def format_item_detail_text(item: Item, detail: Mapping[str, Any]) -> None:
    _format_item_detail(item, detail, "text")


def _format_class_output(
    data: Mapping[str, Any],
    fmt: _Fmt,
    min_level: int = 1,
    max_level: int = 20,
    show_table: bool = True,
    show_features: bool = True,
    feature_filter: str = "",
    show_subclasses: bool = True,
) -> None:
    class_name = data.get("class_name", "Class")
    headers = data.get("table_headers", [])
    rows = data.get("table_rows", [])
    features = data.get("features", [])
    subclasses = data.get("subclasses", [])

    if fmt == "markdown":
        print(f"# The {class_name}\n")
    else:
        print(_plain_h1(f"The {class_name}"))
        print()

    # Progression table
    if show_table and headers and rows:
        if fmt == "markdown":
            print(f"## {class_name} Progression\n")
        else:
            print(_plain_h2(f"{class_name} Progression"))
            print()
        filtered = []
        for row in rows:
            try:
                lvl = _parse_level_int(row[0])
            except IndexError:
                continue
            if lvl is not None and min_level <= lvl <= max_level:
                filtered.append(row)
        if filtered:
            print(
                _md_table(headers, filtered)
                if fmt == "markdown"
                else _plain_table(headers, filtered)
            )
        print()

    # Class features
    if show_features and features:
        if fmt == "markdown":
            print("## Class Features\n")
        else:
            print(_plain_h2("Class Features"))
            print()
        feat_list = features
        if feature_filter:
            feat_list = [
                f for f in feat_list if feature_filter.lower() in f["name"].lower()
            ]
        for feat in feat_list:
            lvl = feat.get("level")
            if fmt == "markdown":
                lvl_note = f" *(unlocked at level {lvl})*" if lvl else ""
                print(f"### {feat['name']}{lvl_note}\n")
            else:
                lvl_note = f"  (unlocked at level {lvl})" if lvl else ""
                print(_plain_h2(f"{feat['name']}{lvl_note}"))
                print()
            _print_blocks(feat.get("body", []), fmt)

    # Subclasses
    if show_subclasses and subclasses:
        if fmt == "markdown":
            print(f"## {class_name} Subclasses\n")
        else:
            print(_plain_h2(f"{class_name} Subclasses"))
            print()
        print(
            _md_table(["Name", "Source"], [[s["name"], s.get("source", "")] for s in subclasses])
            if fmt == "markdown"
            else _plain_table(["Name", "Source"], [[s["name"], s.get("source", "")] for s in subclasses])
        )
        print()


def format_class_markdown(
    data: Mapping[str, Any],
    min_level: int = 1,
    max_level: int = 20,
    show_table: bool = True,
    show_features: bool = True,
    feature_filter: str = "",
    show_subclasses: bool = True,
) -> None:
    _format_class_output(
        data, "markdown",
        min_level=min_level, max_level=max_level,
        show_table=show_table, show_features=show_features,
        feature_filter=feature_filter, show_subclasses=show_subclasses,
    )


def format_class_text(
    data: Mapping[str, Any],
    min_level: int = 1,
    max_level: int = 20,
    show_table: bool = True,
    show_features: bool = True,
    feature_filter: str = "",
    show_subclasses: bool = True,
) -> None:
    _format_class_output(
        data, "text",
        min_level=min_level, max_level=max_level,
        show_table=show_table, show_features=show_features,
        feature_filter=feature_filter, show_subclasses=show_subclasses,
    )


# ---------------------------------------------------------------------------
# Misc formatters
# ---------------------------------------------------------------------------
def format_misc_table(items: list[MiscLink]) -> None:
    if not items:
        console.print("[yellow]No misc links found.[/yellow]")
        return
    table = Table(
        title=f"Misc Links ({len(items)} results)",
        show_lines=False,
        highlight=True,
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Class", style="bright_green")
    for item in items:
        table.add_row(item.name, item.parent_class)
    console.print(table)


def format_misc_detail(link: MiscLink, features: list) -> None:
    console.print(
        Panel(
            "\n".join(
                filter(
                    None,
                    [
                        f"[bold]URL:[/bold]    [link={link.url}]{link.url}[/link]",
                        _rich_field("Class", link.parent_class),
                    ],
                )
            ),
            title=f"[bold cyan]{link.name}[/bold cyan]",
            border_style="cyan",
            title_align="center",
        )
    )
    for feat in features:
        body_parts = _render_blocks_rich(feat.get("body", []))
        console.print(
            Panel(
                "\n".join(body_parts) if body_parts else "",
                title=f"[bold cyan]{feat['name']}[/bold cyan]",
                border_style="bright_black",
                padding=(0, 1),
                title_align="left",
            )
        )


def format_misc_markdown(items: list[MiscLink]) -> None:
    headers = ["Name", "Class"]
    rows = [[i.name, i.parent_class] for i in items]
    print(_md_table(headers, rows))


def format_misc_detail_markdown(link: MiscLink, features: list) -> None:
    print(f"# {link.name}\n")
    if link.parent_class:
        print(f"*Class: {link.parent_class}*\n")
    for feat in features:
        print(f"## {feat['name']}\n")
        _print_blocks(feat.get("body", []), "markdown")
        print()


def format_misc_text(items: list[MiscLink]) -> None:
    headers = ["Name", "Class"]
    rows = [[i.name, i.parent_class] for i in items]
    print(_plain_table(headers, rows))


def format_misc_detail_text(link: MiscLink, features: list) -> None:
    print(f"{link.name.upper()}")
    if link.parent_class:
        print(f"Class: {link.parent_class}")
    print()
    for feat in features:
        print(feat["name"].upper())
        _print_blocks(feat.get("body", []), "text")
        print()
