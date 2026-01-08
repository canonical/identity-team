#!/usr/bin/env bash

# Helper script for updating the DEV_MODEL_UUID/STG_MODEL_UUID Secrets in operator/integrator repos.

# fail and early return if one or both env var are not set
if ! ([ -n "$DEV_MODEL_UUID" ] && [ -n "$STG_MODEL_UUID" ])
then
  echo "please set both env var needed"
  echo "- DEV_MODEL_UUID"
  echo "- STG_MODEL_UUID"
  exit 1
fi

source "$(dirname "$0")/repos_list.sh"

for repo in "${charms[@]}"; do
    echo "Updating secrets for $repo"
    gh secret -R https://github.com/canonical/$repo set DEV_MODEL_UUID -b "$DEV_MODEL_UUID" || true
    gh secret -R https://github.com/canonical/$repo set STG_MODEL_UUID -b "$STG_MODEL_UUID" || true
done
