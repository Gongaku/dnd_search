#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from signal import signal, SIGPIPE, SIG_DFL

import dnd_search.class_api as class_api
import dnd_search.format_output as format_output
import dnd_search.spell_api as spell_api
from dnd_search.dnd_data import Subclass, DnDClass

DND_CLASSES = [
    "artificer",
    "barbarian",
    "bard",
    "cleric",
    "druid",
    "fighter",
    "monk",
    "paladin",
    "rogue",
    "sorcerer",
    "warlock",
    "wizard"
]

def spell_subcommand(subparsers: argparse.ArgumentParser) -> tuple:
    """Adds subcommands for the SPELL subcommands"""

    spell_parser = subparsers.add_parser(
        "spell",
        help="fetch spell information",
        description="Fetches spell information for either individual\
                spells or whole spell lists")
    spell_subparsers = spell_parser.add_subparsers(
        help="command help",
        dest="subcommand")

    # Parser for individual spells
    get_spell_parser = spell_subparsers.add_parser(
        "get",
        help="fetch individual spell information",
        description="Fetch the information of an individual spell. \
                Includes the name, source, level, school of magic, \
                effect, and the class spell list")
    get_spell_parser.add_argument(
        "spell_name",
        nargs='*',
        help="spell Name to search information for.")
    get_spell_parser.add_argument(
        "-o", "--output",
        type=str,
        choices=["txt", "csv", "tsv", "json"],
        help="Changes the format that the data is outputted. Default: txt")

    # Parser for spell list
    list_parser = spell_subparsers.add_parser(
        "list",
        help="provides a list of 5e spells as a table",
        description="Pull a list of spells depending \
                on the specified arguments. By default \
                It pulls a list of all avaliable Wizard's\
                of the Coast spells.")
    list_parser.add_argument(
        "-cl", "--class_name",
        metavar="CLASS",
        type=str.lower,
        choices=DND_CLASSES,
        help="limits search to a specified player class")
    list_parser.add_argument(
        "-l", "--level",
        type=str,
        help="limits search to specified spell level")
    list_parser.add_argument(
        "-s", "--school",
        type=str,
        help="limits search to specified school of magic")
    list_parser.add_argument(
        "-co", "--component",
        nargs='+',
        help="limits search to specified components. \
            Ex: if using V, then any combination of components\
            including V will be returned")
    list_parser.add_argument(
        "-o", "--output",
        type=str,
        choices=["txt", "csv", "tsv", "json"],
        help="Changes the format that the data is outputted. \
                The txt option outputs the data as a table. Default: txt")
    list_parser.add_argument(
        "-sh", "--short",
        action='store_true',
        help="Removes the column used to limit search in the result set")

    return (spell_parser, get_spell_parser, list_parser)


def class_subcommand(subparsers: argparse.ArgumentParser) -> tuple:
    """Adds subcommands for the CLASS subcommands"""
    class_parser = subparsers.add_parser(
        "class",
        help="fetch class information",
        description="Fetches class information including\
                class descriptions, book source, and features")

    class_subparsers = class_parser.add_subparsers(
        help="command help",
        dest="subcommand")

    class_base_parser = class_subparsers.add_parser(
        "get",
        help="fetchs base class information. Ex: Wizard",
        description="Fetch information regarding the base class")
    class_base_parser.add_argument(
        "class_name",
        metavar="CLASS",
        type=str.lower,
        choices=DND_CLASSES,
        help=f"Name of the Dnd 5e class to pull data about.\
                \nOptions: {', '.join(DND_CLASSES)}")
    class_base_parser.add_argument(
        "-f", "--feature",
        nargs="+",
        help="Search for a class feature containing \
            the inputted value in the name")
    class_base_parser.add_argument(
        "-l", "--leveling",
        action='store_true',
        help="Search for a subclass feature containing \
            the inputted value in the name")
    class_base_parser.add_argument(
        "--list-subclasses",
        action='store_true',
        help="List all subclasses for the given class")
    class_base_parser.add_argument(
        "-o", "--output",
        type=str,
        choices=["txt", "csv", "tsv", "json"],
        help="Changes the format that the data is outputted. Default: txt")

    class_sub_parser = class_subparsers.add_parser(
        "subclass",
        help="fetchs subclass/archetype information. Ex: School of Conjuration Wizard",
        description="Fetch information regarding a specific subclass.")
    class_sub_parser.add_argument(
        "class_name",
        help="Parent class for subclass to look for")
    class_sub_parser.add_argument(
        "subclass",
        nargs="*",
        help="Subclass to search for. If no subclass is given, \
            then a list of available subclasses will be returned")
    class_sub_parser.add_argument(
        "-f", "--feature",
        nargs="+",
        help="Search for a subclass feature containing \
            the inputted value in the name")
    class_sub_parser.add_argument(
        "-o", "--output",
        type=str,
        choices=["txt", "csv", "tsv", "json"],
        help="Changes the format that the data is outputted. \
                The txt option outputs the data as a table. Default: txt")

    return (class_parser, class_base_parser, class_sub_parser)


def usage_and_error(data, parser) -> None:
    if data is None:
        parser.print_usage()
        sys.exit(1)

def list_subclasses(class_data: DnDClass | Subclass, args: argparse.Namespace) -> str:
    (features,) = [
        format_output.format_feature(feature, args.output, only_table=True)
        for feature in class_data.features
        if feature.table is not None
        and any(
            x in feature.title.lower()
            for x in ['artificer', 'path', 'college',
                      'domain', 'circle', 'tradition',
                      'oath', 'archetype', 'sorcerous', 'patron']
        )
    ]
    return features


def class_output(
    class_data: DnDClass | Subclass,
    parser,
    output_format: str,
    feature_flag: bool = False
) -> None:
    usage_and_error(class_data, parser)

    output = None
    if feature_flag:
        search_string = ' '.join(feature_flag)
        features = [
            format_output.format_feature(feature, output_format) for feature in class_data.features
            if search_string.lower() in feature.title.lower()
        ]

        if output_format == "json":
            features = json.loads('{"features": ' + f"[{','.join(features)}]" + "}")
            features = json.dumps(features, indent=4)
        else:
            features = ''.join(features)
        output = features

    elif hasattr(class_data, 'multiclass_requirement'):
        output = format_output.format_class(class_data, output_format)

    else:
        output = format_output.format_subclass(class_data, output_format)

    return output


def cli() -> None:
    """Contains all logic regarding use as a command line interface."""
    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler("test.log")
    file_handler.setLevel(logging.DEBUG)

    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        handlers=[stream_handler, file_handler]
    )

    parser = argparse.ArgumentParser(
        prog='dnd_search',
        description="This is meant to be a quick way to \
                search up either a spell or spell list \
                for a given DnD 5e class. It uses \
                https://dnd5e.wikidot.com to scrape information")
    subparsers = parser.add_subparsers(help="command help", dest="subparser_name")

    # For SPELL subcommands
    spell_parser, spell_get_parser, spell_list_parser = spell_subcommand(subparsers)

    # For CLASS subcommmand
    class_parser, class_base_parser, class_sub_parser = class_subcommand(subparsers)

    args = parser.parse_args()

    if len(sys.argv) <= 2:
        parser.parse_args([sys.argv[1], '--help'])

    elif args.subparser_name == "spell":
        output = None
        if args.subcommand == "get":
            spell_name = " ".join(args.spell_name)

            if spell_name == "":
                logging.error("No spell name was given.")
                spell_get_parser.print_usage()
                sys.exit(1)

            spell = spell_api.get_spell(" ".join(args.spell_name))
            usage_and_error(spell, spell_get_parser)
            output = format_output.format_spell(spell, args.output)

        elif args.subcommand == "list":
            class_name = args.class_name
            logging.debug(f"Fetching spell list for {class_name}")
            spell_list = spell_api.get_spell_list(class_name, args.short)
            usage_and_error(spell_list, spell_list_parser)
            output = format_output.format_spell_list(spell_list, args)

    elif args.subparser_name == "class":
        if args.subcommand == "get":
            class_name = args.class_name
            logging.debug(f"Fetching class data for {class_name}")
            class_data = class_api.get_class(class_name)
            if args.leveling:
                output = format_output.format_table(
                    class_data.leveling_table,
                    headers=class_data.leveling_headers,
                    output_format=args.output)
            elif args.list_subclasses:
                output = list_subclasses(class_data, args)

            else:
                output = class_output(class_data, class_base_parser, args.output, args.feature)

        elif args.subcommand == "subclass":
            class_name = args.class_name
            subclass = ' '.join(args.subclass)
            logging.debug(f"Fetching subclass data for {class_name}")

            if subclass == ' ':
                class_sub_parser.print_usage()

            if len(subclass) == 0:
                class_data = class_api.get_class(class_name)
                output = list_subclasses(class_data, args)
            else:
                class_data = class_api.get_subclass(class_name, subclass)
                output = class_output(class_data, class_sub_parser, args.output, args.feature)

    else:
        parser.parse_args(['--help'])

    print(output)


if __name__ == "__main__":
    signal(SIGPIPE, SIG_DFL)
    cli()
