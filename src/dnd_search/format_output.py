#!/usr/bin/env python3

import json
import re
import textwrap
import tabulate
from argparse import Namespace
from shutil import get_terminal_size

from dnd_search.dnd_data import Spell, Feature, DnDClass, Subclass

class colors():
    """
    Class containing a few ANSI escape codes for terminal colored output

    Contains the following:
    - CLEAR
    - BOLD
    - DISABLE
    - UNDERLINE
    - RED
    - GREEN
    - BLUE
    """
    _start = "\033["
    CLEAR = f"{_start}0m"
    BOLD = f"{_start}01m"
    DISABLE = f"{_start}02m"
    UNDERLINE = f"{_start}04m"
    RED = f"{_start}91m"
    GREEN = f"{_start}92m"
    BLUE = f"{_start}94m"


def format_json(json_obj: dict) -> str:
    """
    Prints the data in a json format. Wrapper around json.dumps function

    Args:
        json_obj: A dictionary list containing all the class data

    Returns:
        String containing the formatted table
    """
    return json.dumps(json_obj, indent=4)


def format_table(table: list[list], headers: list[str], output_format: str = 'txt') -> str:
    """
    Prints the data in a tabular format. Wrapper around tabulate function

    Args:
        table: A 2D list containing all the table data
        headers: Table headers

    Returns:
        String containing the formatted table
    """
    formatted_table = None

    if 'sv' in output_format:
        table = [headers] + table
        chars = (',', '\t')

        if output_format == "csv":
            joining_char, replace_char = chars
        else:
            replace_char, joining_char = chars

        replace_pattern = f"[{joining_char}\n]"
        print([[re.sub(replace_pattern, replace_char, col) for col in row] for row in table])

        formatted_table = '\n'.join([
            joining_char.join([
                re.sub(joining_char, replace_pattern, str(col))
                for col in row
            ]) for row in table
        ])
    else:
        formatted_table = tabulate.tabulate(table, headers=headers, tablefmt='simple')

    return formatted_table


def format_error(subcommand: str, name: str) -> str:
    """Error message"""
    return textwrap.dedent(
        f"Unable to find data for the {subcommand} '{name.replace(':', '')}'. "
        f"Please ensure that the {subcommand} is spelled correctly."
    )


def format_spell(spell: Spell, output_format: str = "txt") -> None:
    """
    Formats the Spell class into the specified format.

    By default, the format chosen emulates the player handbook

    Args:
        spell: Spell object containing required data
        format: Format output will take.
    """
    if spell is None:
        return None

    if output_format == "csv" or output_format == "tsv":
        chars = (',', '\t')

        if output_format == "csv":
            joining_char, replace_char = chars
            replace_char = ','
        else:
            replace_char, joining_char = chars

        replace_pattern = f"[{joining_char}\n]"
        formatted_spell = joining_char.join([
            f'"{col}"' for col in (
                spell.name,
                spell.source,
                spell.level,
                spell.school,
                spell.casting_time,
                spell.spell_range,
                spell.duration,
                re.sub(replace_pattern, "", spell.components),
                re.sub(replace_pattern, "", spell.effect),
                re.sub(replace_pattern, "", spell.higher_level_effect),
                replace_char.join(spell.classes)
            )
        ])

    elif output_format == "json":
        formatted_spell = format_json(spell.dict())

    elif output_format == "md":
        hle = f"\nAt Higher Levels. {spell.higher_level_effect}\n" \
            if spell.higher_level_effect else ''
        formatted_spell = textwrap.dedent(
            f"""\
            {spell.name}
            -
            Source:       {spell.source}\\
            Level:        {spell.level.capitalize()}\\
            School:       {spell.school.capitalize()}\\
            Casting Time: {spell.casting_time}\\
            Range:        {spell.spell_range}\\
            Components:   {spell.components}\\
            Duration:     {spell.duration}\\
            Effect:""") + f"\n{'\n'.join([sentence.strip() for sentence in spell.effect.split('.')])}" + hle + textwrap.dedent(
            f"""\
            Spell Lists: {', '.join(spell.classes)}
            """)

    else:
        TERM_WIDTH, _ = get_terminal_size()
        padding = int((TERM_WIDTH - len(spell.name)) / 2)
        hle = f"{colors.BOLD}At Higher Levels.{colors.CLEAR} {spell.higher_level_effect}\n" \
            if spell.higher_level_effect else ''
        formatted_spell = textwrap.dedent(
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
            {colors.BOLD}Duration:{colors.CLEAR}     {spell.duration}
            """) + f"\n{spell.effect.replace('*', '\u2022')}" + hle + textwrap.dedent(
            f"""\
            {colors.BOLD}Spell Lists:{colors.CLEAR} {', '.join(spell.classes)}
            """)

    return formatted_spell


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
        header: Headers for spell list table
        data: The list of various spells
        condition: The condition to limit search by
        column_index: The column number to remove from dataset if needed
        shorten: Used to determine if a column is needed to be removed

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
        spell_list: List containing abbreviated spell information
        cli_arguments: A namedtuple containing command line arguments

    Returns:
        String containing the spell list in the desired output format
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
    if "sv" in cli_arguments.output:
        joining_char = ',' if cli_arguments.output == "csv" else '\t'

        formatted_list = '\n'.join([
            joining_char.join([
                str(val).replace(joining_char, '')
                for val in spell.dict().values()
            ]) for spell in spell_list
        ])

    elif cli_arguments.output == "json":
        formatted_list = format_json({
            "Spell Count": len(spell_list),
            "Spells": [dict(zip(headers, spell)) for spell in spell_list]
        })

    else:
        formatted_list = format_table(spell_list, headers=headers)

    return formatted_list


def colorize(text, pattern) -> str:
    """
    Function to go through and add ANSI escape codes to the desired text.

    Args:
        text: The string to add colorized output to
        pattern: The regex pattern for the area you want to bolden

    Returns:
        A string containing the ANSI escape codes
    """
    return re.sub(pattern, lambda m: f"{colors.BOLD}{m.group()}{colors.CLEAR}", text)


def format_feature(
    feature: Feature,
    output_format: str = "str",
    only_table: bool = False
) -> str:
    """
    Formats a player class feature into the desire output format

    Args:
        feature: The class feature that needs to be formatted.
        output_format: The style to format the data as. Ex: csv

    Returns:
        Formatted output using the output_format form
    """
    table = None
    if feature.table:
        table_headers, *table = [row for row in feature.table if len(row) == len(feature.table[0])]

    if output_format == "csv" or output_format == "tsv":
        separator = "," if output_format == "csv" else "\t"
        replacement_char = "|" if output_format == "csv" else ""
        description = feature.description.replace(separator, replacement_char).replace("\n", "").strip()
        formatted_feature = f"{feature.title}{separator}{description}"

    elif output_format == "json":
        formatted_feature = {
            "feature_name": feature.title,
            "feature_description": feature.description,
        }
        if table:
            table = [dict(zip(table_headers, row)) for row in table]
            formatted_feature.update({"feature_table": table})
        formatted_feature = format_json(formatted_feature)

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

        formatted_table = format_table(table, headers=table_headers) if table else ""
        formatted_feature = f"{title}\n{description}"
        if table:
            formatted_feature = f"{formatted_feature.strip()}\n{formatted_table}\n\n" \

        if only_table:
            formatted_feature = formatted_table

        formatted_feature = textwrap.dedent(formatted_feature)

    return formatted_feature


def format_subclass(data: Subclass, output_format: str = "str") -> str:
    """
    Formats a subclass to the desired output format.

    Args:
        data: The class data to format.
        output_format: The form that output will take.

    Returns:
        A string containing the data in the desired output format.
    """
    output = None

    if output_format == "csv" or output_format == "tsv":
        output = '\n'.join([format_feature(feature, output_format) for feature in data.features])

    elif output_format == "json":
        output = format_json({
            "class_name": data.class_name,
            "subclass_name": data.title,
            "subclass_description": data.description,
            "subclass_source": data.source,
            "features": [format_feature(feature, "json") for feature in data.features]
        })

    else:
        TERM_WIDTH, _ = get_terminal_size()
        padding = int((TERM_WIDTH - len(data.title)) / 2)
        double_space = "\n\n"
        output = textwrap.dedent(
            f"""\
            {'─' * TERM_WIDTH}
            {' ' * padding}{colors.BOLD}{data.class_name}:{data.title}{colors.CLEAR}
            {'─' * TERM_WIDTH}
            {colors.BOLD}Description
            {'─'*40}{colors.CLEAR}
            {data.description}\n\n
            {colors.BOLD}Source
            {'─'*40}{colors.CLEAR}
            {data.source}\n\n
            """) + "\n".join([format_feature(feature) for feature in data.features])

    return output


def format_class(data: DnDClass, output_format: str = "str") -> str:
    """
    Formats a class to the desired output format.

    Args:
        data: The class data to format.
        output_format: The form that output will take.

    Returns:
        A string containing the data in the desired output format.
    """
    output = None
    if output_format == "csv" or output_format == "tsv":
        output = '\n'.join([format_feature(feature, output_format) for feature in data.features])

    elif output_format == "json":
        output = format_json({
            "name": data.class_name,
            "description": data.description,
            "multiclass_requirement": data.multiclass_requirement,
            "leveling_table": [dict(zip(data.leveling_headers, row)) for row in data.leveling_table],
            "features": [format_feature(feature, "json") for feature in data.features]
        })

    else:
        TERM_WIDTH, _ = get_terminal_size()
        padding = int((TERM_WIDTH - len(data.class_name)) / 2)
        output = textwrap.dedent(f"""\
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
            """) \
            + format_table(data.leveling_table, headers=data.leveling_headers) \
            + "\n\n" \
            + "\n".join([format_feature(feature) for feature in data.features])

    return output
