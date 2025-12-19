#!/usr/bin/env bash

# Helper script for updating the PAT/SCORECARD Tokens in all our repos.
# When creating a new repo we need to:
# 1. Update the tokens
# 2. Regenerate the token
# 3. Update this script to include the new repo
# 4. Use this script to update the tokens in all our repos
# 5. Update the script in the repo

# fail and early return if one or both env var are not set
if ! ([ -n "$PAT_TOKEN" ] && [ -n "$SCORECARD_TOKEN" ])
then
  echo "please set both env var needed"
  echo "- PAT_TOKEN"
  echo "- SCORECARD_TOKEN"
  exit 1
fi

source "$(dirname "$0")/repos_list.sh"


for repo in "${repos[@]}"; do
    gh secret -R https://github.com/canonical/$repo set PAT_TOKEN -b $PAT_TOKEN || true
    gh secret -R https://github.com/canonical/$repo set SCORECARD_TOKEN -b $SCORECARD_TOKEN || true
done

