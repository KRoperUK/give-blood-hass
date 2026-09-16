# Contributing

## Setup

Home Assistant 2026.8+ requires Python 3.14.

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pre-commit install          # installs both pre-commit and pre-push hooks
```

To develop against a local library checkout instead of the published wheel:

```bash
pip install -e ../give-blood-py
```

## The one rule that matters most

**Never commit real donor data.** Every account endpoint in this API returns the donor's name, address,
phone number, date of birth and donor ID, and an access token in a test fixture is a live credential.

Four layers guard this, and all four run automatically:

| Layer | Catches |
|---|---|
| `scripts/check_pii.py` (pre-commit + CI) | Emails, UK postcodes, UK phone numbers, JWTs, Bearer tokens, NHSBT donor/donation IDs, credential assignments |
| `detect-secrets` (pre-commit + CI) | High-entropy secrets, against the audited `.secrets.baseline` |
| `bandit` (pre-commit + CI) | Insecure code patterns in the integration |
| `tests/test_repo_hygiene.py` and `tests/test_diagnostics.py` | Real values in-tree, and PII escaping into diagnostics |

Reserved substitutes to use in tests and docs:

| Kind | Value | Why it's safe |
|---|---|---|
| Email | `donor@example.invalid` | RFC 6761 reserves `.invalid` |
| Postcode | `SW1A 1AA`, or any `ZZ99 …` | Royal Mail reserves the `ZZ99` outcode |
| Phone | `07700900000` | Ofcom's reserved drama range |
| Donor ID | `D0000000` | |
| Donation ID | `G000000000000X` | |
| Token | anything starting `synthetic` | |

If a finding is genuinely safe, add a `pii-allow` comment to that line — and say why.

## Checks

```bash
pytest                                        # 263 tests, 80% coverage floor
ruff check . && ruff format --check .
mypy                                          # strict
bandit -c bandit.yaml -r custom_components
bash scripts/check-tool-pins.sh
bash scripts/package-hacs-zip.sh
```

CI additionally runs HACS validation and hassfest, both of which are release blockers because releases
ship as a zip asset.

### The `preflight` job

`typecheck`, `pre-commit`, `test` and `test-floor` all install
[`nhs-give-blood`](https://github.com/KRoperUK/give-blood-py) from PyPI, so they cannot run until the
floor pinned in `manifest.json` has actually been published. The `preflight` job checks that first and
skips them rather than letting them fail with an opaque pip resolution error.

If you see `preflight` red with *"Nothing on PyPI satisfies …"*, the library release has not caught up
with the floor. Either publish it, or lower the floor in **both** `manifest.json` and
`requirements_dev.txt` — the check asserts they agree, because Home Assistant installs one at runtime
and CI installs the other, and drift means testing something users never get.

### The `test-floor` job

`hacs.json` and `manifest.json` declare Home Assistant **2026.8.0** as the minimum, and before this job
nothing tested it. `pytest-homeassistant-custom-component` pins the Home Assistant release it is built
against, so `requirements_test.txt`'s floor resolves to the *newest* Home Assistant: every other job has
only ever run against that, which made the floor an assertion rather than a verified fact.

The job installs `pytest-homeassistant-custom-component==0.13.354` — the last release paired with exactly
`homeassistant==2026.8.0`; `0.13.355` moved on to 2026.8.1 — then asserts the installed Home Assistant
really is 2026.8.x before running the suite. That assertion is the point: if the pin stops resolving to
the floor, the leg fails loudly instead of quietly re-testing the newest release under a floor's name.

**The mapping needs maintaining.** When the support window moves, find the phacc release that pairs with
the new floor and update the pin in `.github/workflows/ci.yml`:

```bash
curl -s https://pypi.org/pypi/pytest-homeassistant-custom-component/0.13.354/json \
  | python -c "import json,sys; print([d for d in json.load(sys.stdin)['info']['requires_dist'] if d.startswith('homeassistant')])"
```

## Testing approach

Tests patch `GiveBloodApiClient` (the adapter), not HTTP. The library has its own suite covering
transport, retry, and token behaviour; duplicating it here would test the library twice and the
integration once. What matters on this side is how Home Assistant reacts to each adapter outcome:

- `CannotConnect` → `UpdateFailed`, entities unavailable, retry, **no reauth prompt**
- `InvalidAuth` → `ConfigEntryAuthFailed`, reauth flow opens, **no backoff**
- A degraded snapshot → still a successful poll; core entities stay available

Those three behaviours are the integration's contract. Changes to them need tests.

## Three constraints that are easy to break

**The recorder's 16,384-byte attribute limit.** Home Assistant silently discards an entity's *entire*
attribute dict above that size — nothing is logged, and the attributes vanish after a restart. Any new
list-valued attribute must go through `helpers.limit_attributes` with its key named in
`shrinkable_attributes`. `tests/test_sensor.py` asserts every entity stays under budget.

**The options-versus-data reload loop.** `async_reload_entry` compares options against a snapshot taken
at setup. Without that comparison, the coordinator's post-poll token write would reload the entry on
every poll: reload → poll → tokens rotate → update entry → reload. Do not remove the guard.

**Read-only.** `tests/test_repo_hygiene.py::TestNoWriteOperations` fails if any module references
`async_book_appointment`, `async_reschedule_appointment` or `async_cancel_appointment`. That test is
load-bearing, not decorative — see [Why it is read-only](README.md#why-it-is-read-only). If you want to
change this, open an issue first; it is a design decision, not an oversight.

## Adding an entity

1. Add a description to `SENSORS` or `BINARY_SENSORS`. Value functions must tolerate a
   partially-populated payload — every field in this API is optional in practice, and a raised exception
   inside `native_value` breaks the whole state write.
2. Use `helpers.safe_number` / `safe_datetime` / `safe_state` rather than raw values.
3. Keep `translation_key == key`; a hygiene test enforces it.
4. Add entries to **both** `strings.json` and `translations/en.json`, plus `icons.json`. Parity tests
   enforce all three.
5. Add a test asserting the state.

## Version bumps

Do not edit versions by hand. release-please bumps `manifest.json` (`$.version`) and `const.py` (via the
`# x-release-please-version` marker) from Conventional Commit messages, then attaches the HACS zip to
the release.

The library floor is pinned in two files that must move together: `manifest.json` `requirements` and
`requirements_dev.txt`. A hygiene test asserts they agree.

## Commits

Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). `feat:` is a minor bump,
`fix:` a patch, `feat!:` or a `BREAKING CHANGE:` footer a major.
