# from collections import namedtuple
from dataclasses import dataclass, asdict

@dataclass
class Feature():
    """Class Feature for either a DndClass or Subclass"""
    title: str
    description: str
    table: list[list]

    def dict(self):
        return {k: str(v) for k, v in asdict(self).items() if v is not None and v != ''}

@dataclass
class Subclass():
    """Subclass/Archetype data for a DnDClass"""
    class_name: str
    title: str
    description: str
    source: str
    features: list[Feature]

    def dict(self):
        return {k: str(v) for k, v in asdict(self).items() if v is not None and v != ''}

@dataclass
class DnDClass():
    """Class data for a DnD 5e Player Class"""
    class_name: str
    description: str
    multiclass_requirement: str
    leveling_headers: list[str]
    leveling_table: list[list]
    features: list[Feature]

    def dict(self):
        return {k: str(v) for k, v in asdict(self).items() if v is not None and v != ''}

@dataclass
class Spell():
    """DnD 5e Spell data"""
    name: str
    source: str
    level: str
    school: str
    casting_time: str
    spell_range: str
    duration: str
    components: str
    effect: str
    higher_level_effect: str
    classes: list[str]

    def dict(self):
        return {k: str(v) for k, v in asdict(self).items() if v is not None and v != ''}
