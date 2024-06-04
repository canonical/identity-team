# pre-commit

The `pre-commit` tool helps identify issues before a contribution is made to a
project. The Identity team uses it in several different projects to discover and
resolve small issues in source code, documentation, and tool configurations.

## Installation

Use the `pip` to install the pre-commit package manager:

```shell
pip install pre-commit
```

> ⚠️ **NOTE**
>
> The team-owned projects usually come with a tox env to automatically install
> the pre-commit. Please see the `CONTRIBUTING.md` in each repository.

## Usage

Simply copy and paste the sample pre-commit configuration file of the
corresponding project type (e.g. `pre-commit-config-{type}.yaml`) to the root of
target repository, and name the file as `.pre-commit-config.yaml`.

Install the hooks in the target repository by:

```shell
pre-commit install -t commit-msg
```

> ⚠️ **NOTE**
>
> The team-owned projects usually come with a tox env to automatically install
> the hooks. Please see the `CONTRIBUTING.md` in each repository.

## Hooks Update

[Renovate](https://github.com/renovatebot/renovate) is configured in each
repository to automatically update the pre-commit hooks. Please find more
information [HERE](https://docs.renovatebot.com/modules/manager/pre-commit/).
