import dnd_search.api as api
import logging
import re
from bs4 import BeautifulSoup
from dnd_search.dnd_data import Spell
from dnd_search.format_output import format_error

def get_spell(spell_name: str) -> Spell:
    """
    Scrapes the wikidot link for the specified spell. It
    follows the /spell:spell_name format.

    Args:
        spell_name (str): Name of DnD 5e spell

    Returns:
        Spell: Spell object containing all specified information
    """
    uri = f"{api.WIKIDOT_URI}/spell:{spell_name.replace(" ", "-").replace("/", "-").lower()}"
    try:
        content = api.api_call(uri)
    except AssertionError:
        output = format_error("spell", spell_name.title())
        logging.error(output)
        return None

    soup = BeautifulSoup(content, "html.parser")
    name = soup.find(class_="page-title").text
    source, level, school, casting_time, \
        spell_range, components, effect, higher_level_effect = [''] * 8
    classes = []

    for d in soup.find(id="page-content").find_all(["p", "ul"]):
        text = d.text + "\n"
        text = text.replace("\u2019", "'")

        if re.match("Source", text):
            source = re.search("(?<=Source: ).*", text).group()

        elif re.match("[0-9]", text):
            level, school = re\
                .search("(^[0-9].*level) (.*)", text)\
                .groups()
        elif re.search("cantrip$", text):
            school, level = re\
                .search("(.*) (cantrip)$", text)\
                .groups()

        elif re.match("Spell Lists", text):
            text = text[text.index(".")+1:]
            classes = [c.strip() for c in text.split(",")]

        elif "Casting Time: " in text:
            pattern = re.compile(
                "(?<=Casting Time: ).*|"
                "(?<=Range: ).*|"
                "(?<=Components: ).*|"
                "(?<=Duration: ).*"
            )
            casting_time, spell_range, components, duration = \
                re.findall(pattern, text)

        elif d.name == "ul":
            # effect = f"{effect}\t• {text.strip()}\n"
            effect = f"{effect}\t* {text.strip()}\n"

        else:
            if "At Higher Levels." in text:
                text = text.replace("At Higher Levels.", "").strip()
                higher_level_effect = f"{text}\n"
            else:
                effect = f"{effect}{text}\n"

    return Spell(
        name,
        source,
        level.capitalize(),
        school.capitalize(),
        casting_time,
        spell_range,
        duration,
        components,
        effect,
        higher_level_effect,
        classes
    )

def get_spell_list(class_name: str, trim_output: bool = False) -> list[Spell]:
    """
    Scrapes the wikidot link for different spell lists.
    If no class_name is provided, then it will list all
    DnD 5e spells on wikidot.

    Args:
        class_name (str): Name of the Dnd Player Character Class

    Returns:
        list[Spell]: A list containing abbreviated spell information.
                          Does not include spell effect.
    """
    class_name = f":{class_name.lower()}" if class_name else ""
    uri = f"{api.WIKIDOT_URI}/spells{class_name}"
    try:
        content = api.api_call(uri)
    except AssertionError:
        output = format_error("class", class_name.title())
        logging.error(output)
        return None

    soup = BeautifulSoup(content, "html.parser")
    spells = soup.find_all("tr")

    level = -1
    spell_list = []
    for spell in spells:
        tags = [tag.name for tag in spell]
        if "th" in tags:
            level += 1
            continue
        name, school, casting_time, spell_range, duration, components = \
            spell.text.split("\n")[1:-1]
        if trim_output:
            name = truncate_string(name, 15)
            school = school[:3]
            casting_time = re.sub("R$", "(Rit)", casting_time)
            casting_time = re.sub("Bonus", "B", casting_time)
            casting_time = re.sub("Minute", "Min", casting_time)
            duration = truncate_string(duration, 10)
        else:
            if "R" in casting_time:
                casting_time = re.sub("R$", "(Ritual)", casting_time)
            if re.search("[CDGT]+$", school):
                school = re.sub("[CDGT]+$", "", school)
        spell_range = re.sub("[ -]+f[eo]+t", " ft", spell_range)
        level_name = "Cantrip" if level == 0 else level

        s = Spell(
            name,
            None,
            level_name,
            school,
            casting_time,
            spell_range,
            duration,
            components,
            None,
            None,
            None
        )

        spell_list.append(s)

    return spell_list


def truncate_string(input_str: str, max_length: int = 10) -> str:
    """
    Truncates string and replaces character overflow with an ellipsis.

    If string is less than the max_length, then nothing is changed.

    Args:
        input_str (str): String to try to truncate.
        max_length (int): Sets the maximum length of attempting to truncate the string

    Returns:
        str: updated string
    """
    str_end = "..."

    if len(input_str) > max_length:
        return input_str[:max_length - len(str_end)]+str_end

    return input_str
