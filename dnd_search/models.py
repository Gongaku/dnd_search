"""Data models for D&D 5e entities."""

from dataclasses import dataclass, field
from typing import TypedDict


# ---------------------------------------------------------------------------
# Detail TypedDicts — returned by scraper.fetch_*_detail functions.
# These give formatters.py a typed contract so renamed/missing keys are caught
# by the type checker instead of raising KeyError at runtime.
# ---------------------------------------------------------------------------
class SpellTableEntry(TypedDict):
    level: str
    spells: str


class SubclassEntry(TypedDict):
    name: str
    url: str
    source: str


class FeatureBlock(TypedDict, total=False):
    """A single body block inside a class feature or subclass feature.

    `type` is always present; other keys depend on the type value:
      paragraph → text, text_md, text_rich
      list      → items
      heading   → text
      table     → headers, rows
    """

    type: str  # "paragraph" | "list" | "heading" | "table"
    text: str
    text_md: str
    text_rich: str
    items: list[str]
    spell_table: list[SpellTableEntry]
    headers: list[str]
    rows: list[list[str]]


class _FeatureRequired(TypedDict):
    name: str
    body: list[FeatureBlock]


class Feature(_FeatureRequired, total=False):
    level: int | None
    spell_table: list[SpellTableEntry]


class Trait(TypedDict):
    name: str
    text: str


class _SubraceDetailRequired(TypedDict):
    name: str
    source: str
    description: str
    description_md: str
    traits: list[Trait]


class SubraceDetail(_SubraceDetailRequired, total=False):
    spell_table: list[SpellTableEntry]


class SpellDetail(TypedDict):
    source: str
    description: str
    description_md: str
    at_higher_levels: str
    at_higher_levels_md: str
    classes: list[str]


class ClassDetail(TypedDict):
    hit_die: str
    primary_ability: str
    saving_throws: str
    description: str
    subclasses: list[SubclassEntry]


class SubclassDetailDict(TypedDict):
    source: str
    description: str
    description_md: str
    features: list[Feature]


class FeatDetail(TypedDict):
    source: str
    prerequisites: str
    description: str
    description_md: str
    benefits: list[str]


class RaceDetail(TypedDict):
    source: str
    description: str
    description_md: str
    traits: list[Trait]
    subraces: list[SubraceDetail]


class ItemDetail(TypedDict):
    source: str
    description: str


class ClassFeatures(TypedDict, total=False):
    class_name: str
    url: str
    table_headers: list[str]
    table_rows: list[list[str]]
    subclasses: list[SubclassEntry]
    features: list[Feature]


@dataclass
class Spell:
    name: str
    url: str
    level: int = 0  # 0 = cantrip
    school: str = ""
    casting_time: str = ""
    range: str = ""
    duration: str = ""
    components: str = ""
    ritual: bool = False
    concentration: bool = False
    classes: list[str] = field(default_factory=list)
    source: str = ""
    description: str = ""


@dataclass
class DnDClass:
    name: str
    url: str
    hit_die: str = ""
    primary_ability: str = ""
    saving_throws: str = ""
    description: str = ""


@dataclass
class Subclass:
    name: str
    url: str
    parent_class: str = ""
    source: str = ""
    description: str = ""


@dataclass
class Feat:
    name: str
    url: str
    prerequisites: str = ""
    source: str = ""
    description: str = ""


@dataclass
class Race:
    name: str
    url: str
    size: str = ""
    speed: str = ""
    source: str = ""
    description: str = ""


@dataclass
class Item:
    name: str
    url: str
    item_type: str = ""
    rarity: str = ""
    requires_attunement: bool = False
    source: str = ""
    description: str = ""


@dataclass
class MiscLink:
    name: str
    url: str
    parent_class: str = ""
