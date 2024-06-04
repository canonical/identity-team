# markdownlint-cli

The [`markdownlint-cli`](https://github.com/igorshubovych/markdownlint-cli) is a
linting tool for Markdown files. It's used as one of the pre-commit hooks in all
team-owned projects to guarantee consistent styles for documentation.

## Configuration

The `.markdownlint.yaml` and `.markdownlintignore` files are leveraged to
specify rules and ignored files respectively in each project's repository.

## Usage

Simply copy and paste the [sample configuration file](markdownlint.yaml) to the
root of target repository, and name the file as `.markdownlint.yaml`. With
the [pre-commit hook](https://github.com/igorshubovych/markdownlint-cli?tab=readme-ov-file#use-with-pre-commit)
enabled, changes of any Markdown documentation will be linted.
