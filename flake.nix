{
  description = "CLI tool for searching D&D 5e content from dnd5e.wikidot.com";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    treefmt-nix.url = "github:numtide/treefmt-nix";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      treefmt-nix,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        dnd-search = python.pkgs.buildPythonApplication {
          pname = "dnd-search";
          version = "1.1.1";
          pyproject = true;

          src = ./.;

          build-system = [ python.pkgs.hatchling ];

          dependencies = with python.pkgs; [
            click
            requests
            beautifulsoup4
            lxml
            rich
          ];

          meta = {
            description = "CLI tool for searching D&D 5e content";
            license = pkgs.lib.licenses.mit;
            mainProgram = "dnd-search";
          };
        };

        treefmtEval = treefmt-nix.lib.evalModule pkgs {
          projectRootFile = "flake.nix";
          programs = {
            nixfmt.enable = true;
            ruff-format.enable = true;
          };
        };
      in
      {
        packages = {
          default = dnd-search;
          dnd-search = dnd-search;
        };

        apps.default = {
          type = "app";
          program = "${dnd-search}/bin/dnd-search";
        };

        devShells.default = pkgs.mkShell {
          packages = [ dnd-search ];
        };

        formatter = treefmtEval.config.build.wrapper;

        checks.formatting = treefmtEval.config.build.check self;
      }
    );
}
