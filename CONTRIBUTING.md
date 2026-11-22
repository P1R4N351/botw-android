# Contributing

[MAINTENANCE.md](MAINTENANCE.md) is the reference for how this repository is organised: the branches (`common` builds
both apps), the per-game variables in `games/games.toml` (a new difference between the games is added there first,
then read from it), building, releasing and testing.

- **Never commit game files, keys or dumps.** The repository holds no game content (README, *Legal*): no game program,
  art, text, audio, shaders, keys or system files, and nothing derived from them. Signing keys never enter git either.
- **Upstream PRs carry no GPL code.** A change meant for upstream ([AurelioB/totk-android](https://github.com/AurelioB/totk-android))
  is made on a branch from `upstream/main`. The Eden Duo companion (`games/totk/duo/`, GPL-3.0-or-later; see
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)) and the Bifrost bridge stay out of it.
- **Cherry-picks use `-x`**, so the copied commit names its origin; carried upstream features keep their authors.
- **Run the tests** before sending a change: `LC_ALL=C.UTF-8 tools/check_all.sh`. Some unit tests fail on a pristine
  tree on machines without the macOS tools; compare with the previous result, not with zero.
