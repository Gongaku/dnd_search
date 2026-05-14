# TODO

- [x] Add URL column when using the "-d/--details" flags for all plural commands like there is for the "items" command. Ensure that this column is hidden if the "-d/--details" flag was not used.
- [x] Add Quick Links command that is separate from the subclasses (Continue with current prompt)
- [x] Update class command to have an initial section with a cyan border. This section should include the class name, description, multiclass requirements ("You must have a ..."), Hit Points (hit dice, hit points at 1st level, hit points at higher levels), Proficencies, and equipment.
- [ ] Add a different dnd-search script that searches "dnd2024.wikidot.com" instead of "dnd5e.wikidot.com". This should have the same commands and general architecture.
- [x] Add a way to package the script as a binary
- [x] Create a GitHub Actions workflow that will update the version in the pyproject.toml file on to match current commit tag if it doesn't match, then package the script as a binary for Linux, MacOS, and Windows in the "Releases" section.
