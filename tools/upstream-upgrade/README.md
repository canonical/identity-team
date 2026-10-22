# Rock Upstream Upgrade Tooling

Centralized automation for assessing upstream version upgrades in Canonical Identity rock repositories and opening upgrade validation issues on the charms that deploy them.

## What Is Auto-Detected

The script (`upstream_upgrade.py`) inspects the rock's `rockcraft.yaml` and each target charm's `charmcraft.yaml` automatically:

- **From `rockcraft.yaml`**:
  - `rock_image`: `ghcr.io/canonical/<name>`
  - `to` version: `version` field in `rockcraft.yaml`
  - `upstream_repo`: GitHub `<owner>/<repo>` from the main part's `source` URL
  - `tag_prefix`: tag prefix before the version in `source-tag` (e.g. `version/` or `v`)
  - `source_subdir`: `source-subdir` (e.g. `v2` for `glauth-rock`)
  - `service`: Pebble service name under `services:`
- **From each charm's `charmcraft.yaml`** (on `target-branch`, default `main`):
  - `from` version: parsed from `resources.<resource>.upstream-source` matching `<rock_image>:<version>`
  - `resource`: OCI image resource key (e.g. `oci-image` or `openfga-image`)
  - `app`: charm `name`
  - `container`: container name under `containers:`

## Per-Repository Configuration (`.github/upstream-upgrade.yaml`)

Each rock repository places a concise `.github/upstream-upgrade.yaml` file describing the charms that consume the rock and any upstream-specific settings:

```yaml
# Optional overrides (auto-detected from rockcraft.yaml if omitted):
# workload: hydra
# diffed_files:
#   - Dockerfile
# release_notes_path: null  # null/omitted uses GitHub Releases API
# trusted_link_hosts: []
# enforce_sequential_series: false

charms:
  - key: hydra
    repo: canonical/hydra-operator
    description: >-
      Kubernetes charm running Ory Hydra (`hydra serve all`). It configures Hydra
      via environment variables and config files in Pebble, manages PostgreSQL
      migrations, and exposes OAuth2/OIDC endpoints over ingress and charm relations.
    files:
      - charmcraft.yaml
      - src/charm.py
      - src/constants.py
      - src/cli.py
      - src/configs.py
      - src/services.py
```

## Reusable Workflows

### 1. Pull Request Analysis (`.github/workflows/upstream-upgrade.yaml`)

Comments on Renovate/upgrade PRs with build-input changes, CVE dependency override status (automatically pruning and committing satisfied overrides from `rockcraft.yaml`), and AI risk analysis:

```yaml
name: Upstream upgrade
run-name: Upstream upgrade analysis for PR ${{ github.event.pull_request.number }}

on:
  pull_request:
    paths:
      - "rockcraft.yaml"
      - ".github/upstream-upgrade.yaml"
      - ".github/workflows/upstream-upgrade.yaml"

concurrency:
  group: upstream-upgrade-${{ github.event.pull_request.number }}
  cancel-in-progress: true

permissions:
  contents: write
  pull-requests: write

jobs:
  analyse:
    uses: canonical/identity-team/.github/workflows/_rock-upstream-upgrade.yaml@main
    secrets: inherit
```

### 2. Charm Upgrade Issues (`.github/workflows/upstream-charm-issues.yaml`)

Manually triggered (`workflow_dispatch`) when the charms on `target-branch` (default `main`) are ready to move to the new rock version:

```yaml
name: Upstream charm upgrade issues
run-name: Charm upgrade issues for branch ${{ inputs.target-branch || 'main' }}

on:
  workflow_dispatch:
    inputs:
      target-branch:
        description: "Target branch in the charm repositories"
        type: string
        required: false
        default: "main"
      to-version:
        description: "Upstream version to move to (default: the one in rockcraft.yaml)"
        type: string
        required: false
        default: ""
      image:
        description: "Published image (default: the rock's image for that version)"
        type: string
        required: false
        default: ""
      dry-run:
        description: "Generate the issues without opening them"
        type: boolean
        required: false
        default: false

permissions:
  contents: read

jobs:
  open-issues:
    uses: canonical/identity-team/.github/workflows/_rock-upstream-charm-issues.yaml@main
    with:
      target-branch: ${{ inputs.target-branch }}
      to-version: ${{ inputs.to-version }}
      image: ${{ inputs.image }}
      dry-run: ${{ inputs.dry-run }}
    secrets: inherit
```

## Running Tests Locally

```bash
python3 -m unittest discover -s tools/upstream-upgrade/tests -v
```
