{
  pkgs ? import <nixpkgs> { },
}:
let
  dnd-search = pkgs.python3Packages.buildPythonApplication {
    pname = "dnd-search";
    version = "1.1.1";
    pyproject = true;

    src = ./.;

    build-system = [ pkgs.python3Packages.hatchling ];

    dependencies = with pkgs.python3Packages; [
      click
      requests
      beautifulsoup4
      lxml
      rich
    ];
  };
in
pkgs.mkShell {
  packages = [ dnd-search ];
}
