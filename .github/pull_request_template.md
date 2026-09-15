## What changed

<!-- One paragraph. Why, not just what. -->

## Checks

- [ ] `pytest` passes
- [ ] `ruff check . && ruff format --check .` clean
- [ ] `mypy` clean
- [ ] Conventional Commit title (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)

## If this touches entities

- [ ] Added to `strings.json`, `translations/en.json` and `icons.json`
- [ ] New list-valued attributes go through `helpers.limit_attributes`
- [ ] Value functions tolerate a missing or malformed field

## If this touches anything that reads donor data

- [ ] No PII in states, attributes, logs or diagnostics
- [ ] Test fixtures use reserved placeholder values only
