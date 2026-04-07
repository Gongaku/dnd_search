"""Shared fixtures for dnd-search CLI tests."""

import pytest
from dnd_search.models import DnDClass, Feat, Item, Race, Spell, Subclass


@pytest.fixture()
def spells():
    return [
        Spell(
            name="Fireball",
            url="https://dnd5e.wikidot.com/spell:fireball",
            level=3,
            school="Evocation",
            casting_time="1 Action",
            range="150 feet",
            duration="Instantaneous",
            components="V, S, M",
            ritual=False,
            concentration=False,
            classes=["Sorcerer", "Wizard"],
            source="Player's Handbook",
        ),
        Spell(
            name="Detect Magic",
            url="https://dnd5e.wikidot.com/spell:detect-magic",
            level=1,
            school="Divination",
            casting_time="1 Action",
            range="Self",
            duration="10 minutes",
            components="V, S",
            ritual=True,
            concentration=True,
            classes=["Cleric", "Wizard"],
            source="Player's Handbook",
        ),
        Spell(
            name="Fire Bolt",
            url="https://dnd5e.wikidot.com/spell:fire-bolt",
            level=0,
            school="Evocation",
            casting_time="1 Action",
            range="120 feet",
            duration="Instantaneous",
            components="V, S",
            ritual=False,
            concentration=False,
            classes=["Sorcerer", "Wizard"],
            source="Player's Handbook",
        ),
    ]


@pytest.fixture()
def spell_detail():
    return {
        "source": "Player's Handbook",
        "description": "A bright streak flashes from your pointing finger.",
        "description_md": "A bright streak flashes from your pointing finger.",
        "at_higher_levels": "At Higher Levels. Damage increases by 1d6.",
        "at_higher_levels_md": "At Higher Levels. Damage increases by 1d6.",
        "classes": ["Sorcerer", "Wizard"],
    }


@pytest.fixture()
def classes():
    return [
        DnDClass(
            name="Fighter",
            url="https://dnd5e.wikidot.com/fighter",
            hit_die="d10",
            primary_ability="Strength or Dexterity",
            saving_throws="Strength, Constitution",
        ),
        DnDClass(
            name="Wizard",
            url="https://dnd5e.wikidot.com/wizard",
            hit_die="d6",
            primary_ability="Intelligence",
            saving_throws="Intelligence, Wisdom",
        ),
    ]


@pytest.fixture()
def class_detail():
    return {
        "hit_die": "d10",
        "primary_ability": "Strength or Dexterity",
        "saving_throws": "Strength, Constitution",
        "description": "A master of martial combat.",
        "subclasses": [
            {"name": "Battle Master", "url": "/fighter:battle-master", "source": "PHB"},
            {"name": "Champion", "url": "/fighter:champion", "source": "PHB"},
        ],
    }


@pytest.fixture()
def subclasses():
    return [
        Subclass(
            name="Battle Master",
            url="https://dnd5e.wikidot.com/fighter:battle-master",
            parent_class="Fighter",
            source="Player's Handbook",
        ),
        Subclass(
            name="Arcane Trickster",
            url="https://dnd5e.wikidot.com/rogue:arcane-trickster",
            parent_class="Rogue",
            source="Player's Handbook",
        ),
    ]


@pytest.fixture()
def feats():
    return [
        Feat(
            name="War Caster",
            url="https://dnd5e.wikidot.com/feat:war-caster",
            prerequisites="The ability to cast at least one spell",
            source="Player's Handbook",
        ),
        Feat(
            name="Alert",
            url="https://dnd5e.wikidot.com/feat:alert",
            prerequisites="",
            source="Player's Handbook",
        ),
    ]


@pytest.fixture()
def feat_detail():
    return {
        "source": "Player's Handbook",
        "prerequisites": "The ability to cast at least one spell",
        "description": "You have practiced casting spells in the midst of combat.",
        "description_md": "You have practiced casting spells in the midst of combat.",
        "benefits": [
            "Advantage on Constitution saving throws to maintain concentration.",
            "You can perform somatic components even when holding weapons.",
        ],
    }


@pytest.fixture()
def races():
    return [
        Race(
            name="Elf",
            url="https://dnd5e.wikidot.com/elf",
            size="Medium",
            speed="30 feet",
            source="Player's Handbook",
        ),
        Race(
            name="Dwarf",
            url="https://dnd5e.wikidot.com/dwarf",
            size="Medium",
            speed="25 feet",
            source="Player's Handbook",
        ),
    ]


@pytest.fixture()
def race_detail():
    return {
        "source": "Player's Handbook",
        "description": "Elves are a magical people of otherworldly grace.",
        "description_md": "Elves are a magical people of otherworldly grace.",
        "traits": [
            {"name": "Darkvision", "text": "You can see in dim light within 60 feet."},
            {"name": "Fey Ancestry", "text": "Advantage against being charmed."},
        ],
        "subraces": [
            {
                "name": "High Elf",
                "source": "Player's Handbook",
                "description": "High elves have a keen mind.",
                "description_md": "High elves have a keen mind.",
                "traits": [{"name": "Cantrip", "text": "You know one wizard cantrip."}],
            }
        ],
    }


@pytest.fixture()
def items():
    return [
        Item(
            name="Bag of Holding",
            url="https://dnd5e.wikidot.com/wondrous-items:bag-of-holding",
            item_type="Wondrous Item",
            rarity="Uncommon",
            requires_attunement=False,
            source="Dungeon Master's Guide",
        ),
        Item(
            name="Vorpal Sword",
            url="https://dnd5e.wikidot.com/magic-items:vorpal-sword",
            item_type="Weapon (any sword)",
            rarity="Legendary",
            requires_attunement=True,
            source="Dungeon Master's Guide",
        ),
    ]


@pytest.fixture()
def item_detail():
    return {
        "source": "Dungeon Master's Guide",
        "description": "This appears to be a common sack.",
    }
