#!/usr/bin/env python3

import logging
import re

from bs4 import BeautifulSoup, NavigableString

import dnd_search.api as api
from dnd_search.dnd_data import Feature, Subclass, DnDClass
from dnd_search.format_output import format_error

def table_to_list(input_str: NavigableString) -> list:
    """
    Converts a NavigableString string into a list of strings containing the text of each table cell

    Args:
        input_str: HTML string containing an HTML Table to convert

    Returns:
        A 2D list containing all the text elements contained within the HTML table
    """
    if input_str is None:
        return None

    table = [
        [col.text for col in row.find_all(["th", "td"])]
        for row in input_str.find_all("tr")
    ]
    row_length = max([len(row) for row in table])

    return [
        row for row in table if len(row) == row_length
    ]


def separate_section(sections: list) -> list[list]:
    """
    Takes a list of Tags/NavigableStrings and then splits the list whenever a header element is encountered.
    I.e. any html element starting with h[1-5] splits the sections

    Args:
        section: A section containing relevant tags that need to be sorted

    Return:
        A 2D list containing the separated sections
    """
    features = []
    previous_index = 0

    for index, section in enumerate(sections):
        if "h" in section.name \
                and len(sections[previous_index:index]) > 0:
            features.append(sections[previous_index:index])
            previous_index = index

    return features


def group_features_by_header(feature_list: list, skip_first: bool = False) -> list[Feature]:
    """
    Groups the different tags from the feature list by the header element.
    If will split the list at any point it encounters a header.

    Args:
        feature_list: List of tags to parse through and separate.
        skip_first: Check to skip the first element in the feature_list

    Returns:
        A list containing feature objects with info such as feature name and description
    """
    features = []

    if skip_first:
        logging.info("Skipping first row of table")
        feature_list = feature_list[1:]

    for feature in feature_list:
        feature_title, feature_table = [None] * 2
        feature_desc = ""

        for tag in feature:
            if "h" in tag.name:
                feature_title = tag.text

            elif tag.name == "p":
                feature_desc = f"{feature_desc}{tag.text}\n\n"

            elif "ul" in tag.name:
                for t in [t for t in tag if t != '\n']:
                    feature_desc = f"{feature_desc.strip()}\n\t• {t.text.strip()}"
                feature_desc = f"{feature_desc}\n\n"

            elif "table" in tag.name:
                feature_table = table_to_list(tag)

        f = Feature(feature_title, feature_desc, feature_table)
        features.append(f)
    return features


def get_class(class_name: str) -> DnDClass:
    """
    Pulls the base class details including the description,
    multiclass requirements, leveling table, and features.

    The class features includes information such as Hit Dice,
    Proficiencies, Subclasses/Archetypes, and Spell Casting

    Args:
        class_name: Name of the DnD 5e class you would like to pull data for

    Returns:
        An object containing the class' description, multiclass requirements, leveling table, and features
    """
    uri = f"{api.WIKIDOT_URI}/{class_name.lower()}"
    try:
        content = api.api_call(uri)
    except AssertionError:
        output = format_error("class", class_name.title())
        logging.error(output)
        return None

    soup = BeautifulSoup(content, "html.parser")
    name = soup.find(class_="page-title").text
    sections = [
        section for section
        in soup.find(id="page-content")
        if section is not None
        and section != '\n'
        and section.name != 'br'
    ]

    for index in range(0, len(sections[:3])):
        if 'multiclass' in sections[index].text:
            break

    description = ' '.join([tag.text for tag in sections[:index]])
    multiclass = sections[index].text
    leveling_table = sections[index+1]
    features = sections[index+2:]
    leveling_headers, *leveling_table = table_to_list(leveling_table)
    class_components = DnDClass(name, description, multiclass, leveling_headers, leveling_table, None)

    features = list(
        next(
            feature for feature in features if feature != '\n'
        ).find_all(["h1", "h3", "h5", "p", "ul", "table"])
    )

    class_features = separate_section(features)
    class_components.features = group_features_by_header(class_features, skip_first=True)
    logging.debug(f"Created object for class {class_name}")

    return class_components


def get_subclass(class_name: str, subclass: str) -> DnDClass:
    """
    Pulls the subclass details including the description and features.

    Args:
        class_name: Name of the DnD 5e class you would like to pull data for
        subclass: Name of the subclass to pull data for

    Returns:
        An object containing the subclass' description and features
    """
    uri = f"{api.WIKIDOT_URI}/{class_name.lower()}:{subclass.replace(' ', '-').lower()}"
    try:
        content = api.api_call(uri)
    except AssertionError:
        output = format_error("subclass", f"{class_name.title()}|{subclass.title()}")
        logging.error(output)
        return None

    soup = BeautifulSoup(content, "html.parser")
    name = soup.find(class_="page-title").text
    name = re.sub(f"^{class_name.title()}.*:", "", name).strip()

    *description, features = [
        section for section
        in soup.find(id="page-content")
        if section is not None and section != '\n'
    ]
    if isinstance(description, list):
        description = ' '.join([tag.text for tag in description])
    else:
        description = description.text
    subclass_features = separate_section(features.find_all(["p", "h3"]))
    source, *features = group_features_by_header(subclass_features)
    source = re.sub("^Source.*:", "", source.description).strip()
    logging.debug(f"Created object for subclass {class_name}:{name}")

    return Subclass(class_name.title(), name, description, source, features)
