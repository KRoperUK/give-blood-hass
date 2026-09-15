#!/usr/bin/env bash
# Assert that ruff and bandit are pinned to the same version in
# requirements_test.txt and .pre-commit-config.yaml.
#
# CI installs from requirements_test.txt while contributors run pre-commit, so a
# drift between the two means "clean locally, failing in CI" — which wastes more
# time than any lint rule saves.
set -euo pipefail

fail=0

check() {
  local tool="$1" repo_marker="$2"
  local req precommit

  req="$(grep -oE "^${tool}==[0-9.]+" requirements_test.txt | cut -d= -f3 || true)"
  precommit="$(grep -A2 "${repo_marker}" .pre-commit-config.yaml | grep -oE 'rev: v?[0-9]+\.[0-9]+\.[0-9]+' | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)"

  if [[ -z "$req" ]]; then
    echo "::error::could not find a ${tool}== pin in requirements_test.txt"
    fail=1
    return
  fi
  if [[ -z "$precommit" ]]; then
    echo "::error::could not find a ${tool} rev in .pre-commit-config.yaml"
    fail=1
    return
  fi
  if [[ "$req" != "$precommit" ]]; then
    echo "::error::${tool} pin mismatch: requirements_test.txt has ${req}, .pre-commit-config.yaml has ${precommit}"
    fail=1
    return
  fi
  echo "${tool} pinned consistently at ${req}"
}

check ruff "ruff-pre-commit"
check bandit "PyCQA/bandit"

exit "$fail"
