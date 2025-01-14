#!/usr/bin/env python3

import json
import re
import shutil
import textwrap
import tabulate
from argparse import Namespace
from dnd_search.dnd_data import Spell, Feature, DnDClass, Subclass

class colors():
    _start = "\033["
    CLEAR = f"{_start}0m"
    BOLD = f"{_start}01m"
    DISABLE = f"{_start}02m"
    UNDERLINE = f"{_start}04m"
    RED = f"{_start}91m"
    GREEN = f"{_start}92m"
    BLUE = f"{_start}94m"


def format_error(subcommand: str, name: str) -> str:
    return textwrap.dedent(
        f"Unable to find data for the {subcommand} '{name.replace(':', '')}'. "
        f"Please ensure that the {subcommand} is spelled correctly."
    )


def format_spell(spell: Spell, output_format: str = "txt") -> None:
    """
    Formats the Spell class into the specified format.

    By default, the format chosen emulates the player handbook

    Args:
        spell (Spell): Spell object containing required data
        format (str): Format output will take.
    """
    if spell is None:
        return None

    if output_format == "csv":
        effect = re.sub("[,\n]", "", spell.effect)
        higher_level_effect = re.sub("[,\n]", "", spell.higher_level_effect)
        classes = '|'.join(spell.classes)
        formatted_text = ','.join((
            spell.name,
            spell.source,
            spell.level,
            spell.school,
            spell.casting_time,
            spell.spell_range,
            spell.duration,
            spell.components,
            effect,
            higher_level_effect,
            classes
        ))
    elif output_format == "tsv":
        effect = re.sub("[\n]", "", spell.effect)
        higher_level_effect = re.sub("[\n]", "", spell.higher_level_effect)
        classes = ','.join(spell.classes)
        formatted_text = '\t'.join((
            spell.name,
            spell.source,
            spell.level,
            spell.school,
            spell.casting_time,
            spell.spell_range,
            spell.duration,
            spell.components,
            effect,
            higher_level_effect,
            classes
        ))
    elif output_format == "json":
        formatted_text = json.dumps(spell.dict(), indent=4)
    else:
        TERM_WIDTH, _ = shutil.get_terminal_size()
        padding = int((TERM_WIDTH - len(spell.name)) / 2)
        hle = f"{colors.BOLD}At Higher Levels.{colors.CLEAR} {spell.higher_level_effect}\n" \
            if spell.higher_level_effect else ''
        formatted_text = textwrap.dedent(
            f"""\
            {'─' * TERM_WIDTH}
            {' ' * padding}{colors.BOLD}{spell.name}{colors.CLEAR}
            {'─' * TERM_WIDTH}
            {colors.BOLD}Source:{colors.CLEAR}       {spell.source}
            {colors.BOLD}Level:{colors.CLEAR}        {spell.level.capitalize()}
            {colors.BOLD}School:{colors.CLEAR}       {spell.school.capitalize()}
            {colors.BOLD}Casting Time:{colors.CLEAR} {spell.casting_time}
            {colors.BOLD}Range:{colors.CLEAR}        {spell.spell_range}
            {colors.BOLD}Components:{colors.CLEAR}   {spell.components}
            """) + f"\n{spell.effect.replace('*', '\u2022')}" + hle + textwrap.dedent(
            f"""\
            {colors.BOLD}Spell Lists:{colors.CLEAR} {', '.join(spell.classes)}
            """)

    return formatted_text


def limit_search(
    header: list,
    data: list,
    condition: str | int | list,
    column_index: int,
    shorten: bool = False
) -> list[list]:
    """
    This limits the result set to only the specified condition.

    Args:
        header (list): Headers for spell list table
        data (list): The list of various spells
        condition (str|int): The condition to limit search by
        column_index (int): The column number to remove from dataset if needed
        shorten (bool): Used to determine if a column is needed to be removed

    Returns:
        list: A limited list containing the selected result set
    """
    if shorten:
        header.pop(column_index)
        data = [
            d[:column_index]+d[column_index+1:] for d
            in data
            if str(d[column_index]).lower() == str(condition).lower()
            or str(condition).lower() in str(d[column_index]).lower()
        ]
    else:
        data = [
            d for d in data
            if str(d[column_index]).lower() == str(condition).lower()
            or str(condition).lower() in str(d[column_index]).lower()
            or all(str(c).lower() in str(d[column_index]).lower() for c in condition)
        ]

    return data


def format_spell_list(spell_list: list[Spell], cli_arguments: Namespace = None) -> str:
    """
    Formats a list of spells into different formats. Options: csv, tsv, json, and txt. Default: text

    Args:
        spell_list (list[Spell]): List containing abbreviated spell information
        cli_arguments (argparse.Namespace): A namedtuple containing command line arguments
    """
    headers = ["Name", "Level", "School", "Casting Time", "Range", "Duration", "Components"]

    if cli_arguments is None:
        return spell_list

    # Limit search result set
    if cli_arguments.level:
        spell_list = limit_search(headers, spell_list, cli_arguments.level, headers.index("Level"), cli_arguments.short)

    if cli_arguments.school:
        spell_list = limit_search(headers, spell_list, cli_arguments.school, headers.index("School"), cli_arguments.short)

    if cli_arguments.component:
        spell_list = limit_search(headers, spell_list, cli_arguments.component, headers.index("Components"), cli_arguments.short)

    # Output format
    if cli_arguments.output == "csv":
        output = f"{','.join(headers)}\n"+'\n'.join([','.join([str(col).replace(', ', '|') for col in spell]) for spell in spell_list])

    elif cli_arguments.output == "tsv":
        output = f"{'\t'.join(headers)}\n"+'\n'.join(['\t'.join([str(col) for col in spell]) for spell in spell_list])

    elif cli_arguments.output == "json":
        output = json.dumps({
            "Spell Count": len(spell_list),
            "Spells": [dict(zip(headers, spell)) for spell in spell_list]
        }, indent=4)

    else:
        output = tabulate.tabulate(spell_list, headers=headers, tablefmt="simple")

    return output

def colorize(text, pattern) -> str:
    return re.sub(pattern, lambda m: f"{colors.BOLD}{m.group()}{colors.CLEAR}", text)


def format_feature(feature: Feature, output_format: str = "str") -> str:
    if output_format == "csv":
        description = feature.description.replace(",", "").replace("\n", "").strip()
        output = f"{feature.title},{description}"

    elif output_format == "tsv":
        description = feature.description.replace("\t", "").replace("\n", "").strip()
        output = f"{feature.title}\t{description}"

    elif output_format == "json":
        output = {
            "feature_name": feature.title,
            "feature_description": feature.description,
        }
        if feature.table:
            table_headers, *table = [row for row in feature.table if len(row) == len(feature.table[0])]
            table = [dict(zip(table_headers, row)) for row in table]
            output.update({"feature_table": table})
        output = json.dumps(output, indent=4)

    else:
        highlights = [
            "(Hit|Armor|Weapons|Tools|Saving|Skills)(.*):",
            "Spell save DC", "Spell attack modifier",
            "Copying a Spell into the Book.", "Replacing the Book.", "The Book's Appearance."
        ]
        description = feature.description
        title = f"{colors.BOLD}{feature.title}{colors.CLEAR}\n{'─'*40}" if feature.title else ""

        if title is None:
            title = re.match('.*:', description).group()
        for h in highlights:
            description = colorize(description, h)
        output = f"{title}\n{description}"
        if feature.table:
            table_headers, *table = [row for row in feature.table if len(row) == len(feature.table[0])]
            output = f"{output.strip()}\n" \
                + tabulate.tabulate(table, headers=table_headers, tablefmt='simple_grid')\
                + "\n\n"
        output = textwrap.dedent(output)

    return output


def format_subclass(data: Subclass, output_format: str = "str") -> str:
    output = None
    if output_format == "json":
        output = json.dumps(
            {
                "class_name": data.class_name,
                "subclass_name": data.title,
                "subclass_description": data.description,
                "subclass_source": data.source,
                "features": [format_feature(feature, "json") for feature in data.features]
            },
            indent=4
        )
    else:
        TERM_WIDTH, _ = shutil.get_terminal_size()
        padding = int((TERM_WIDTH - len(data.title)) / 2)
        output = textwrap.dedent(
            f"""\
            {'─' * TERM_WIDTH}
            {' ' * padding}{colors.BOLD}{data.class_name}:{data.title}{colors.CLEAR}
            {'─' * TERM_WIDTH}
            {colors.BOLD}Description
            {'─'*40}{colors.CLEAR}
            {data.description}


            {colors.BOLD}Source
            {'─'*40}{colors.CLEAR}
            {data.source}


            """) + "\n".join([format_feature(feature) for feature in data.features])
    return output


def format_class(data: DnDClass, output_format: str = "str") -> str:
    output = None
    if output_format == "csv":
        output = '\n'.join([format_feature(feature, "csv") for feature in data.features])

    elif output_format == "tsv":
        pass

    elif output_format == "json":
        output = json.dumps(
            {
                "name": data.class_name,
                "description": data.description,
                "multiclass_requirement": data.multiclass_requirement,
                "leveling_table": [dict(zip(data.leveling_headers, row)) for row in data.leveling_table],
                "features": [format_feature(feature, "json") for feature in data.features]
            },
            indent=4)
    else:
        TERM_WIDTH, _ = shutil.get_terminal_size()
        padding = int((TERM_WIDTH - len(data.class_name)) / 2)
        output = textwrap.dedent(
            f"""\
            {'─' * TERM_WIDTH}
            {' ' * padding}{colors.BOLD}{data.class_name}{colors.CLEAR}
            {'─' * TERM_WIDTH}
            {colors.BOLD}Description
            {'─'*40}{colors.CLEAR}
            {data.description}


            {colors.BOLD}Multiclass Requirement
            {'─'*40}{colors.CLEAR}
            {data.multiclass_requirement}

            {colors.BOLD}Leveling Table
            {'─'*40}{colors.CLEAR}
            """) + tabulate.tabulate(data.leveling_table, headers=data.leveling_headers, tablefmt='simple') \
            + "\n\n" + "\n".join([format_feature(feature) for feature in data.features])

    return output
