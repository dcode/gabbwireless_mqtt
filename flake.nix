{
  inputs = {
    utils.url = "github:numtide/flake-utils";
  };
  outputs =
    {
      self,
      nixpkgs,
      utils,
    }:
    utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonPackages = pkgs.python3Packages;
      in
      {
        devShells.default =
          with pkgs;
          pkgs.mkShell {
            venvDir = "./.venv";
            buildInputs = [
              act
              pre-commit
              shellcheck
              yamllint
              hadolint
              nodePackages.prettier
              jq
              pythonPackages.python

              # This executes some shell code to initialize a venv in $venvDir before
              # dropping into the shell
              pythonPackages.venvShellHook
            ];
            # Run this command, only after creating the virtual environment
            postVenvCreation = ''
              unset SOURCE_DATE_EPOCH
              pip install -r requirements.txt
            '';
            # Now we can execute any commands within the virtual environment.
            # This is optional and can be left out to run pip manually.
            postShellHook = ''
              # allow pip to install wheels
              unset SOURCE_DATE_EPOCH
            '';
          };
      }
    );
}
