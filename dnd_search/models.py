"""Data models for D&D 5e entities."""

from dataclasses import dataclass, field


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
