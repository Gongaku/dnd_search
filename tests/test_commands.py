"""CLI command tests using Click's CliRunner.

All tests mock dnd_search.scraper so no real HTTP requests are made.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from dnd_search.cli import main


@pytest.fixture()
def runner():
    return CliRunner()


def invoke(runner, *args, **kwargs):
    """Invoke the CLI and assert it exited cleanly unless exit_code is given."""
    expected_code = kwargs.pop("exit_code", 0)
    result = runner.invoke(main, list(args), catch_exceptions=False)
    assert result.exit_code == expected_code, (
        f"Expected exit {expected_code}, got {result.exit_code}.\nOutput:\n{result.output}"
    )
    return result


# ---------------------------------------------------------------------------
# spells
# ---------------------------------------------------------------------------


class TestSpells:
    def test_lists_all_spells(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells")
        assert "Fireball" in result.output
        assert "Detect Magic" in result.output
        assert "Fire Bolt" in result.output

    def test_filter_by_name(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--name", "fire")
        assert "Fireball" in result.output
        assert "Fire Bolt" in result.output
        assert "Detect Magic" not in result.output

    def test_filter_by_level(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--level", "3")
        assert "Fireball" in result.output
        assert "Detect Magic" not in result.output

    def test_filter_ritual_only(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--ritual")
        assert "Detect Magic" in result.output
        assert "Fireball" not in result.output

    def test_filter_concentration_only(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--concentration")
        assert "Detect Magic" in result.output
        assert "Fireball" not in result.output

    def test_filter_by_school(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--school", "divination")
        assert "Detect Magic" in result.output
        assert "Fireball" not in result.output

    def test_limit(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--limit", "1")
        # Only one spell should appear — confirm at most one name from the list
        names_shown = sum(
            1 for s in ["Fireball", "Detect Magic", "Fire Bolt"] if s in result.output
        )
        assert names_shown == 1

    def test_no_results_warns(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--name", "zzznomatch")
        assert "No spells" in result.output

    def test_json_output(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--output", "json")
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(s["name"] == "Fireball" for s in data)

    def test_markdown_output(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--output", "markdown")
        assert "Fireball" in result.output
        assert "|" in result.output  # markdown table

    def test_plain_output(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spells", "--output", "plain")
        assert "Fireball" in result.output


# ---------------------------------------------------------------------------
# spell (single)
# ---------------------------------------------------------------------------


class TestSpell:
    def test_exact_match(self, runner, spells, spell_detail):
        with (
            patch("dnd_search.scraper.fetch_spells", return_value=spells),
            patch("dnd_search.scraper.fetch_spell_detail", return_value=spell_detail),
        ):
            result = invoke(runner, "spell", "fireball")
        assert "Fireball" in result.output

    def test_partial_match(self, runner, spells, spell_detail):
        with (
            patch("dnd_search.scraper.fetch_spells", return_value=spells),
            patch("dnd_search.scraper.fetch_spell_detail", return_value=spell_detail),
        ):
            result = invoke(runner, "spell", "fireb")
        assert "Fireball" in result.output

    def test_ambiguous_name_shows_candidates(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spell", "fire", exit_code=1)
        assert "Multiple" in result.output or "matches" in result.output.lower()

    def test_not_found_exits(self, runner, spells):
        with patch("dnd_search.scraper.fetch_spells", return_value=spells):
            result = invoke(runner, "spell", "zzznomatch", exit_code=1)
        assert result.exit_code == 1

    def test_markdown_output(self, runner, spells, spell_detail):
        with (
            patch("dnd_search.scraper.fetch_spells", return_value=spells),
            patch("dnd_search.scraper.fetch_spell_detail", return_value=spell_detail),
        ):
            result = invoke(runner, "spell", "fireball", "--output", "markdown")
        assert "Fireball" in result.output
        assert result.output.startswith("#")

    def test_json_output(self, runner, spells, spell_detail):
        with (
            patch("dnd_search.scraper.fetch_spells", return_value=spells),
            patch("dnd_search.scraper.fetch_spell_detail", return_value=spell_detail),
        ):
            result = invoke(runner, "spell", "fireball", "--output", "json")
        import json

        data = json.loads(result.output)
        assert data[0]["name"] == "Fireball"


# ---------------------------------------------------------------------------
# classes / class
# ---------------------------------------------------------------------------


class TestClasses:
    def test_lists_all_classes(self, runner, classes):
        with patch("dnd_search.scraper.fetch_classes", return_value=classes):
            result = invoke(runner, "classes")
        assert "Fighter" in result.output
        assert "Wizard" in result.output

    def test_filter_by_name(self, runner, classes):
        with patch("dnd_search.scraper.fetch_classes", return_value=classes):
            result = invoke(runner, "classes", "--name", "fight")
        assert "Fighter" in result.output
        assert "Wizard" not in result.output

    def test_no_results_warns(self, runner, classes):
        with patch("dnd_search.scraper.fetch_classes", return_value=classes):
            result = invoke(runner, "classes", "--name", "zzznomatch")
        assert "No classes" in result.output

    def test_json_output(self, runner, classes):
        with patch("dnd_search.scraper.fetch_classes", return_value=classes):
            result = invoke(runner, "classes", "--output", "json")
        import json

        data = json.loads(result.output)
        assert any(c["name"] == "Fighter" for c in data)


class TestClass:
    def test_exact_match(self, runner, classes, class_detail):
        with (
            patch("dnd_search.scraper.fetch_classes", return_value=classes),
            patch(
                "dnd_search.scraper.fetch_class_features",
                return_value={
                    "class_name": "Fighter",
                    "table_headers": ["Level", "Proficiency Bonus", "Features"],
                    "table_rows": [["1st", "+2", "Fighting Style"]],
                    "features": [],
                    "subclasses": class_detail["subclasses"],
                },
            ),
        ):
            result = invoke(runner, "class", "fighter")
        assert "Fighter" in result.output

    def test_not_found_exits(self, runner, classes):
        with patch("dnd_search.scraper.fetch_classes", return_value=classes):
            result = invoke(runner, "class", "zzznomatch", exit_code=1)
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# subclasses / subclass
# ---------------------------------------------------------------------------


class TestSubclasses:
    def test_lists_all_subclasses(self, runner, subclasses):
        with patch("dnd_search.scraper.fetch_subclasses", return_value=subclasses):
            result = invoke(runner, "subclasses")
        assert "Battle Master" in result.output
        assert "Arcane Trickster" in result.output

    def test_filter_by_name(self, runner, subclasses):
        with patch("dnd_search.scraper.fetch_subclasses", return_value=subclasses):
            result = invoke(runner, "subclasses", "--name", "battle")
        assert "Battle Master" in result.output
        assert "Arcane Trickster" not in result.output

    def test_sort_by_class(self, runner, subclasses):
        with patch("dnd_search.scraper.fetch_subclasses", return_value=subclasses):
            result = invoke(runner, "subclasses", "--sort", "class")
        # Both should appear; Fighter < Rogue alphabetically
        fighter_pos = result.output.index("Fighter")
        rogue_pos = result.output.index("Rogue")
        assert fighter_pos < rogue_pos

    def test_no_results_warns(self, runner, subclasses):
        with patch("dnd_search.scraper.fetch_subclasses", return_value=subclasses):
            result = invoke(runner, "subclasses", "--name", "zzznomatch")
        assert "No subclasses" in result.output


# ---------------------------------------------------------------------------
# feats / feat
# ---------------------------------------------------------------------------


class TestFeats:
    def test_lists_all_feats(self, runner, feats):
        with patch("dnd_search.scraper.fetch_feats", return_value=feats):
            result = invoke(runner, "feats")
        assert "War Caster" in result.output
        assert "Alert" in result.output

    def test_filter_by_name(self, runner, feats):
        with patch("dnd_search.scraper.fetch_feats", return_value=feats):
            result = invoke(runner, "feats", "--name", "war")
        assert "War Caster" in result.output
        assert "Alert" not in result.output

    def test_filter_by_prerequisite(self, runner, feats):
        with patch("dnd_search.scraper.fetch_feats", return_value=feats):
            result = invoke(runner, "feats", "--prerequisite", "spell")
        assert "War Caster" in result.output
        assert "Alert" not in result.output

    def test_json_output(self, runner, feats):
        with patch("dnd_search.scraper.fetch_feats", return_value=feats):
            result = invoke(runner, "feats", "--output", "json")
        import json

        data = json.loads(result.output)
        assert any(f["name"] == "War Caster" for f in data)


class TestFeat:
    def test_exact_match(self, runner, feats, feat_detail):
        with (
            patch("dnd_search.scraper.fetch_feats", return_value=feats),
            patch("dnd_search.scraper.fetch_feat_detail", return_value=feat_detail),
        ):
            result = invoke(runner, "feat", "war caster")
        assert "War Caster" in result.output

    def test_not_found_exits(self, runner, feats):
        with patch("dnd_search.scraper.fetch_feats", return_value=feats):
            result = invoke(runner, "feat", "zzznomatch", exit_code=1)
        assert result.exit_code == 1

    def test_shows_benefits(self, runner, feats, feat_detail):
        with (
            patch("dnd_search.scraper.fetch_feats", return_value=feats),
            patch("dnd_search.scraper.fetch_feat_detail", return_value=feat_detail),
        ):
            result = invoke(runner, "feat", "war caster")
        assert "concentration" in result.output.lower()


# ---------------------------------------------------------------------------
# races / race
# ---------------------------------------------------------------------------


class TestRaces:
    def test_lists_all_races(self, runner, races):
        with patch("dnd_search.scraper.fetch_races", return_value=races):
            result = invoke(runner, "races")
        assert "Dwarf" in result.output
        assert "Elf" in result.output

    def test_filter_by_name(self, runner, races):
        with patch("dnd_search.scraper.fetch_races", return_value=races):
            result = invoke(runner, "races", "--name", "half")
        assert "Halfling" not in result.output

    def test_filter_by_size(self, runner, races):
        with patch("dnd_search.scraper.fetch_races", return_value=races):
            result = invoke(runner, "races", "--size", "medium")
        assert "Elf" in result.output
        assert "Gnome" not in result.output

    def test_filter_by_subrace(self, runner, races):
        with patch("dnd_search.scraper.fetch_races", return_value=races):
            result = invoke(runner, "races", "--subrace", "dark")
        assert "Elf" in result.output

    def test_limit(self, runner, races):
        with patch("dnd_search.scraper.fetch_races", return_value=races):
            result = invoke(runner, "races", "--limit", "1")
        # Only one spell should appear — confirm at most one name from the list
        names_shown = sum(
            1 for s in ["Elf", "Dwarf", "Dragonborn"] if s in result.output
        )
        assert names_shown == 1

    def test_no_results_warns(self, runner, races):
        with patch("dnd_search.scraper.fetch_races", return_value=races):
            result = invoke(runner, "races", "--name", "zzznomatch")
        assert "No races" in result.output


class TestRace:
    def test_exact_match(self, runner, races, race_detail):
        with (
            patch("dnd_search.scraper.fetch_races", return_value=races),
            patch("dnd_search.scraper.fetch_race_detail", return_value=race_detail),
        ):
            result = invoke(runner, "race", "elf")
        assert "Elf" in result.output

    def test_not_found_exits(self, runner, races):
        with patch("dnd_search.scraper.fetch_races", return_value=races):
            result = invoke(runner, "race", "zzznomatch", exit_code=1)
        assert result.exit_code == 1

    def test_shows_traits(self, runner, races, race_detail):
        with (
            patch("dnd_search.scraper.fetch_races", return_value=races),
            patch("dnd_search.scraper.fetch_race_detail", return_value=race_detail),
        ):
            result = invoke(runner, "race", "elf")
        assert "Darkvision" in result.output

    def test_subrace_filter(self, runner, races, race_detail):
        with (
            patch("dnd_search.scraper.fetch_races", return_value=races),
            patch("dnd_search.scraper.fetch_race_detail", return_value=race_detail),
        ):
            result = invoke(runner, "race", "elf", "--subrace", "high")
        assert "HIGH ELF" in result.output


# ---------------------------------------------------------------------------
# items / item
# ---------------------------------------------------------------------------


class TestItems:
    def test_lists_all_items(self, runner, items):
        with patch("dnd_search.scraper.fetch_items", return_value=items):
            result = invoke(runner, "items")
        assert "Bag of Holding" in result.output
        assert "Vorpal Sword" in result.output

    def test_filter_by_rarity(self, runner, items):
        with patch("dnd_search.scraper.fetch_items", return_value=items):
            result = invoke(runner, "items", "--rarity", "legendary")
        assert "Vorpal Sword" in result.output
        assert "Bag of Holding" not in result.output

    def test_filter_attunement(self, runner, items):
        with patch("dnd_search.scraper.fetch_items", return_value=items):
            result = invoke(runner, "items", "--attunement")
        assert "Vorpal Sword" in result.output
        assert "Bag of Holding" not in result.output

    def test_no_results_warns(self, runner, items):
        with patch("dnd_search.scraper.fetch_items", return_value=items):
            result = invoke(runner, "items", "--name", "zzznomatch")
        assert "No" in result.output


class TestItem:
    def test_exact_match(self, runner, items, item_detail):
        with (
            patch("dnd_search.scraper.fetch_items", return_value=items),
            patch("dnd_search.scraper.fetch_item_detail", return_value=item_detail),
        ):
            result = invoke(runner, "item", "bag of holding")
        assert "Bag of Holding" in result.output

    def test_not_found_exits(self, runner, items):
        with patch("dnd_search.scraper.fetch_items", return_value=items):
            result = invoke(runner, "item", "zzznomatch", exit_code=1)
        assert result.exit_code == 1

    def test_shows_description(self, runner, items, item_detail):
        with (
            patch("dnd_search.scraper.fetch_items", return_value=items),
            patch("dnd_search.scraper.fetch_item_detail", return_value=item_detail),
        ):
            result = invoke(runner, "item", "bag of holding")
        assert "common sack" in result.output


# ---------------------------------------------------------------------------
# cache commands
# ---------------------------------------------------------------------------


class TestCache:
    def test_info(self, runner):
        result = invoke(runner, "cache", "info")
        assert "Cache directory" in result.output

    def test_clear(self, runner):
        with patch("dnd_search.cache.clear", return_value=0):
            result = invoke(runner, "cache", "clear")
        assert "Cleared" in result.output

    def test_prune(self, runner):
        with patch("dnd_search.cache.prune", return_value=3):
            result = invoke(runner, "cache", "prune")
        assert "3" in result.output


# ---------------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------------


class TestGlobalOptions:
    def test_no_cache_flag_passes_through(self, runner, spells):
        fetch = MagicMock(return_value=spells)
        with patch("dnd_search.scraper.fetch_spells", fetch):
            invoke(runner, "--no-cache", "spells")
        fetch.assert_called_once_with(False)

    def test_help_exits_cleanly(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Commands" in result.output
