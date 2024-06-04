# Ruff

The `ruff` is a Python linter and formater written in Rust, which shows much
faster than most of existing Python linters and formatters.

## Installation

Ruff can be installed via `pip`:

```shell
pip install ruff
```

> ⚠️ **NOTE**
>
> The team-owned Python projects usually come with a tox env to automatically
> install ruff. Please see the `CONTRIBUTING.md` in each repository.
> Ruff also provides an officially
> supported [VS Code extension](https://github.com/astral-sh/ruff-vscode).

## Configuration

All the team-owned Python projects use the `pyproject.toml` to configure ruff.
Here is a piece of ruff configuration with explanations.

> ⚠️ **NOTE**
>
> The `{}` is served as a placeholder that should be replaced accordingly in
> each repository.

```toml
[tool.ruff]
# Default settings: https://docs.astral.sh/ruff/configuration/
# Settings: https://docs.astral.sh/ruff/settings/
line-length = 99
include = ["pyproject.toml", "src/**/*.py", "tests/**/*.py", "lib/charms/{lib folder}/**/*.py"]
# A list of file patterns to omit besides the files specified by `exclude`
extend-exclude = ["__pycache__", "*.egg_info"]
# Enable preview mode since the "CPY" rule is not stable yet
preview = true

[tool.ruff.lint]
# Rules: https://docs.astral.sh/ruff/rules/
select = [
    "E", # PEP8 Error
    "W", # PEP8 Warning
    "F", # Pyflakes
    "C", # Pylint Convention
    "N", # PEP8-naming
    "D", # Pydocstle
    "CPY" # flake8-copyright
]
ignore = [
    "D100", # Missing docstring in public module
    "D101", # Missing docstring in public class
    "D102", # Missing docstring in public method
    "D103", # Missing docstring in public function
    "D104", # Missing docstring in public package
    "D105", # Missing docstring in magic method
    "D107", # Missing docstring in __init__
    "D203", # 1 blank line required before class docstring
    "D204", # 1 blank line required after class docstring
    "D213", # Multi-line docstring summary should start at the second line
    "D215", # Section underline is over-indented
    "D400", # First line should end with a period
    "D404", # First word of the docstring should not be "This"
    "D406", # Section name should end with a newline
    "D407", # Missing dashed underline after section
    "D408", # Section underline should be in the line following the section's name
    "D409", # Section underline should match the length of its name
    "D413", # Missing blank line after last section
    "N818", # Exception name should be named with an Error suffix
]

[tool.ruff.lint.flake8-copyright]
author = "Canonical Ltd."

[tool.ruff.lint.mccabe]
# Max allowed McCabe complexity
max-complexity = 10

[tool.ruff.lint.pydocstyle]
convention = "google"
```
