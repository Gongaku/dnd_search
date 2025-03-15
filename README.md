# DND_Search
**Quickly search for something during your next session**

## Purpose
During my own sessions, I've found that I needed to quickly search up the effects for various player class features and of numerous spells. I always forget how to calculate my Spell DC for some reason...

This is meant as a means to alleviate that issue. Although I'm weird in write my Dnd notes in Vim.

## Usage
```sh
usage: dnd_search [-h] {spell,class} ...

This is meant to be a quick way to search up either a spell or spell list for a given DnD 5e class. It uses
https://dnd5e.wikidot.com to scrape information

positional arguments:
  {spell,class}  command help
    spell        fetch spell information
    class        fetch class information

options:
  -h, --help     show this help message and exit
```

* You can quickly search up spells and spell lists using the `spell` subcommand. While getting class and subclass information using the `class` subcommand.
