# Changelog

## [1.8.1](https://github.com/canonical/identity-team/compare/v1.8.0...v1.8.1) (2025-04-15)


### Bug Fixes

* move container structure tests to rock-build wf ([561fd6d](https://github.com/canonical/identity-team/commit/561fd6dff45195ba67706bf49a748ada305eacd8))

## [1.8.0](https://github.com/canonical/identity-team/compare/v1.7.7...v1.8.0) (2025-04-08)


### Features

* adjust rock publishing ([2461510](https://github.com/canonical/identity-team/commit/2461510896333ee6fa3a7141ee0c46fad8400a8b))
* introduce oci updater wf ([4267eb2](https://github.com/canonical/identity-team/commit/4267eb223e3763720f96c2027dd68b82e4319c0d))

## [1.7.7](https://github.com/canonical/identity-team/compare/v1.7.6...v1.7.7) (2025-04-04)


### Bug Fixes

* allow tox targets to be specified in ci ([a16520c](https://github.com/canonical/identity-team/commit/a16520cbfc4c95a172e9699564d274e781c9e267))
* specify tox targets for int and unit tests ([54fefed](https://github.com/canonical/identity-team/commit/54fefed6a7fd67e8dd0feb4d461d9c0411a692bf))

## [1.7.6](https://github.com/canonical/identity-team/compare/v1.7.5...v1.7.6) (2025-03-31)


### Bug Fixes

* drop charm-name input and infer it from charmcraft.yaml ([aaf2239](https://github.com/canonical/identity-team/commit/aaf2239d49017be82ce8ffb29f9071e76af9e9e5))
* move to self hosted runners ([f3d2ac3](https://github.com/canonical/identity-team/commit/f3d2ac3be2e9c1c81a306b1d1a3fdbdbf456c7ca))
* specify addons for microk8s ([d77470d](https://github.com/canonical/identity-team/commit/d77470d4e0eb25aadd682f5148f1e2ab87998bc7))
* specify node size as input ([d9be03c](https://github.com/canonical/identity-team/commit/d9be03c371e141c3b560f22c6f625cd390129e11))
* update k8s and juju versions ([7dd9e22](https://github.com/canonical/identity-team/commit/7dd9e22a4b2b161af5d8feb8e5aa9e9c5239f037))
* use self hosted runners to overcome disk issues when running integration tests ([a066c5a](https://github.com/canonical/identity-team/commit/a066c5a8a785c3d30c75c2d89c53353f4cabd6ce))

## [1.7.5](https://github.com/canonical/identity-team/compare/v1.7.4...v1.7.5) (2025-03-27)


### Bug Fixes

* add GH_TOKEN to address https://github.com/canonical/charmcraftcache/issues/1 ([511be98](https://github.com/canonical/identity-team/commit/511be98aaf4f4e350bece03e775d674712812b2d))
* use GH_TOKEN for ccc build ([0707d86](https://github.com/canonical/identity-team/commit/0707d867fa1ec0667a1b7ce58d6277458a72a4ad))

## [1.7.4](https://github.com/canonical/identity-team/compare/v1.7.3...v1.7.4) (2025-03-27)


### Bug Fixes

* remove CHARMCRAFT_CREDENTIALS from charm-pull-request ([3a6a4d4](https://github.com/canonical/identity-team/commit/3a6a4d471ecc00a5b3fe39b48df97bfbf01628cb))
* remove CHARMCRAFT_CREDENTIALS from charm-pull-request ([30c1589](https://github.com/canonical/identity-team/commit/30c15894893e713b9fd8a83ddc710be6ffc35422))

## [1.7.3](https://github.com/canonical/identity-team/compare/v1.7.2...v1.7.3) (2025-03-26)


### Bug Fixes

* adjust secrets for charm build ([133857e](https://github.com/canonical/identity-team/commit/133857e965dd1f3a6a2ddb9fb0b287de46616c4d))
* drop secret for charm-build ([64a9632](https://github.com/canonical/identity-team/commit/64a9632b5a62e55686bdb8693782536975068890))

## [1.7.2](https://github.com/canonical/identity-team/compare/v1.7.1...v1.7.2) (2025-03-26)


### Bug Fixes

* adjust build artifact name output ([f38acc4](https://github.com/canonical/identity-team/commit/f38acc4617e5eb77c0587c85e63abf7d1ffe2654))
* ensure artifact name is consistent ([542fdd8](https://github.com/canonical/identity-team/commit/542fdd84ef09db9bef611efba4871453f81069be))

## [1.7.1](https://github.com/canonical/identity-team/compare/v1.7.0...v1.7.1) (2025-03-25)


### Bug Fixes

* drop CHARMCRAFT_CREDENTIALS from build wf secrets ([ae5cbef](https://github.com/canonical/identity-team/commit/ae5cbef6cfe8b37109cb4ffeaa741fc1d5fb21ae)), closes [#24](https://github.com/canonical/identity-team/issues/24)

## [1.7.0](https://github.com/canonical/identity-team/compare/v1.6.0...v1.7.0) (2025-03-25)


### Features

* add cve label checker workflow ([ddcbf12](https://github.com/canonical/identity-team/commit/ddcbf12bcc3c679473842f14e23143b8aa3185f8))

## [1.6.0](https://github.com/canonical/identity-team/compare/v1.5.0...v1.6.0) (2025-03-21)


### Features

* **ci:** get charm and container logs on tests failure ([4429a38](https://github.com/canonical/identity-team/commit/4429a3807a4d6a7175ed2789110a7b20fd0012b3))
* **ci:** use charmcraftcache in integration tests ([341d5b8](https://github.com/canonical/identity-team/commit/341d5b838ae14a8828b06e3a293f47f706599bf7))


### Bug Fixes

* **ci:** require secrets on workflow call ([f52cfa1](https://github.com/canonical/identity-team/commit/f52cfa1341f939003fe09173d7de3644f2937852))

## [1.5.0](https://github.com/canonical/identity-team/compare/v1.4.2...v1.5.0) (2025-03-14)


### Features

* add charm build reusable workflow ([dfe91f1](https://github.com/canonical/identity-team/commit/dfe91f156c87b8ff6dc5e9ada5dae9cbde54faf5))
* add secscan reusable workflow ([a0c45ad](https://github.com/canonical/identity-team/commit/a0c45adf4760d880cc5472523a7262afe67ba72b))
* hook up secscan on charm publish ([c0b2f0a](https://github.com/canonical/identity-team/commit/c0b2f0a31b57b7546ac93f2da092acbffed2ce7d))
* use build workflow instead of upload-charm build ([bd17a3c](https://github.com/canonical/identity-team/commit/bd17a3c05f66c99886f9be64c0fe6fd382a23c62))


### Bug Fixes

* do no add tag and release on charm upload ([ebd4b1d](https://github.com/canonical/identity-team/commit/ebd4b1d3ee44eae6e6dff0b82b2fc938e7fdf113))
* use gh token for secscan issue creation ([0f8ae85](https://github.com/canonical/identity-team/commit/0f8ae853fe12034450d37681e348e6ab54fdab0b))
* use gh token for secscan issue creation ([c81ed96](https://github.com/canonical/identity-team/commit/c81ed961dd271bd7c79be2970dc0425efb7cfde3))

## [1.4.2](https://github.com/canonical/identity-team/compare/v1.4.1...v1.4.2) (2025-03-05)


### Bug Fixes

* add inputs for charm-deployment ([b56d179](https://github.com/canonical/identity-team/commit/b56d179019ac4d51529092bce579463c271eb608))

## [1.4.1](https://github.com/canonical/identity-team/compare/v1.4.0...v1.4.1) (2025-03-04)


### Bug Fixes

* use jq to parse git tag ([2490314](https://github.com/canonical/identity-team/commit/2490314a9662a42a7227fee48e3b81da773abfa0))

## [1.4.0](https://github.com/canonical/identity-team/compare/v1.3.0...v1.4.0) (2025-03-04)


### Features

* add charm deploy workflow ([5e71c36](https://github.com/canonical/identity-team/commit/5e71c366dce99d9ee76b9d0ce726033d9a01b027))
* set up the team umbrella repository ([008e719](https://github.com/canonical/identity-team/commit/008e719725edf30127554142c251712f7dda111a))
* use release please for charm releases ([5d4302f](https://github.com/canonical/identity-team/commit/5d4302f4c63586a04cc7bd4d507afda949d89afc))


### Bug Fixes

* adjust release-please manifest ([098c8ab](https://github.com/canonical/identity-team/commit/098c8ab3d3d57ce05e5b666ab98086cbcb99f676))
* secret name  within  can not be used since it would collide with system reserved name ([a699b8d](https://github.com/canonical/identity-team/commit/a699b8d2123f454233736286c2417b3f9613540e))

## [1.3.0](https://github.com/canonical/identity-team/compare/v1.2.0...v1.3.0) (2025-03-04)


### Features

* add charm deploy workflow ([5e71c36](https://github.com/canonical/identity-team/commit/5e71c366dce99d9ee76b9d0ce726033d9a01b027))
* set up the team umbrella repository ([008e719](https://github.com/canonical/identity-team/commit/008e719725edf30127554142c251712f7dda111a))
* use release please for charm releases ([5d4302f](https://github.com/canonical/identity-team/commit/5d4302f4c63586a04cc7bd4d507afda949d89afc))


### Bug Fixes

* adjust release-please manifest ([098c8ab](https://github.com/canonical/identity-team/commit/098c8ab3d3d57ce05e5b666ab98086cbcb99f676))

## [1.2.0](https://github.com/canonical/identity-team/compare/identity-hall-v1.1.0...identity-hall-v1.2.0) (2025-03-04)


### Features

* set up the team umbrella repository ([008e719](https://github.com/canonical/identity-team/commit/008e719725edf30127554142c251712f7dda111a))

## [1.1.0](https://github.com/canonical/identity-team/compare/identity-hall-v1.0.0...identity-hall-v1.1.0) (2024-08-14)


### Features

* set up the team umbrella repository ([008e719](https://github.com/canonical/identity-team/commit/008e719725edf30127554142c251712f7dda111a))
