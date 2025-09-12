# External Groups management

- Status: proposed
- Tags: [identity-platform, cip, groups]

## Context
We need to decide how we are going to use groups from external sources (IdPs and other APIs) to populate our tokens and make authorization decisions.

## Decision
- If admins want to use external groups to allow or deny acccess to users to certain apps, they will need to pre-populate the Groups API with those groups. Unknown groups will be passed through in the token, but they will not be taken into account by the CIP.
- Allow by default is the industry standard, but it is configurable. In an enterprise settings, people will usually use deny by default. Its ok to deny by default, as it is easier to implement, and iterate on it
- The groups in the admin UI will used as they are in the token. The admin UI will not implement group "aliasing" (renaming of the token groups) or group "nesting" (group "A" and group "B" from the token will be mapped to group "C" for the admin UI). We may have to implement this in the future.

## Links <!-- optional -->
- [LXD supports group aliasing](https://documentation.ubuntu.com/lxd/latest/explanation/authorization/#use-groups-defined-by-the-identity-provider)
