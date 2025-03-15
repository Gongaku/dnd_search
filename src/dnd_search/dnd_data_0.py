#!/usr/bin/env python3
import dataclasses
import json
from dataclasses import dataclass, field, asdict

@dataclass
class Base:
    """
    Base Class that all other DnD Search Classes inherit from
    """
    name: str
    description: str = field(metadata={
        "name": "Description of the object",
        "description": "Description of the class or effect of the spell"
    })

    def dict(self):
        """
        Converts class data into a dictionary format
        """
        return {
            k: str(v)
            for k, v in asdict(self).items()
            if v is not None and v != ''
        }

    def to_json(self):
        json.dumps(self.dict())

@dataclass
class Spell(Base):
    """
    DnD 5e Spell data
    """
    source: str = field(metadata={
        "name": "Source Book",
        "description": "Dnd 5e Book containing new spell"})
    level: str = field(metadata={
        "name": "Spell Level",
        "description": "Spell Slot Level required to cast spell"})
    school: str = field(metadata={
        "name": "Spell School",
        "description": "The category for the spell"})
    casting_time: str = field(metadata={
        "name": "Casting Time",
        "description": "Amount of time/type of action required to cast the spell"})
    spell_range: str = field(metadata={
        "name": "Spell Range",
        "description": "Distance that the spell can reach when cast"})
    duration: str = field(metadata={
        "name": "Spell Duration",
        "description": "How long the spell will last after casting"})
    components: str = field(metadata={})
    higher_level_effect: str = field(metadata={})
    classes: list[str] = field(metadata={})


@dataclass
class Feature(Base):
    """
    Class Feature for either DnDClass or SubClass
    """
    table: list[list]

@dataclass
class BaseClass(Base):
    """
    Class that DndClass and SubClass inherits from
    """
    features: list[Feature]

@dataclass
class DnDClass(BaseClass):
    """
    Class data for a DnD 5e Player Class
    """
    multiclass_requirement: str
    leveling_headers: list[str]
    leveling_table: list[list]

@dataclass
class SubClass(BaseClass):
    """
    Subclass/Archetype data for a DndClass
    """
    class_name: str
    source: str


f = Feature(name="Test", description="Test", table=[[0, 1]])
c = BaseClass(name="barbarian", description="Test", features=[f])
print(dataclasses.fields(f))
print(c.name, c.description, c.features)
