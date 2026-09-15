#!/usr/bin/env bash
# Assert that the client-library floor pinned by this repo is installable.
#
# The floor appears in two files that must agree: manifest.json (what Home
# Assistant installs at runtime) and requirements_dev.txt (what CI installs).
# When it names a version PyPI does not have, every job that installs the library
# fails with an opaque pip resolution error. This produces one legible message
# instead, and names the fix.
#
# The recurring mistake it catches in a paired repo: raising the floor here before
# the library release that satisfies it has actually published.
#
# Resolution is delegated to pip rather than modelled locally. pip is the
# authority on whether a requirement is installable, it already understands PEP
# 440 ordering (a hand-rolled comparison gets "0.10.0" versus "0.9.0" wrong), and
# it needs nothing installed beyond the interpreter.
#
# `pip download` rather than `pip install --dry-run`: the latter treats an
# already-installed copy as satisfying the requirement, so it passes locally
# against an editable checkout while the package is absent from PyPI. That is a
# false pass, which is worse than no check at all. `download` always resolves
# against the index and proves the artifact is actually fetchable.
set -euo pipefail

MANIFEST="custom_components/nhs_give_blood/manifest.json"
PACKAGE="nhs-give-blood"

requirement="$(python -c "
import json, sys
manifest = json.load(open('$MANIFEST'))
for item in manifest['requirements']:
    if item.startswith('$PACKAGE'):
        print(item)
        break
else:
    sys.exit('no $PACKAGE requirement found in $MANIFEST')
")"

echo "manifest.json pins: $requirement"

# requirements_dev.txt must pin the same floor; they are installed by different
# consumers (Home Assistant at runtime, CI at test time) and drifting apart means
# testing something users never get.
if ! grep -qF "$requirement" requirements_dev.txt; then
    echo "::error::requirements_dev.txt does not pin '$requirement'. The manifest and"
    echo "::error::requirements_dev.txt floors must move together."
    exit 1
fi
echo "requirements_dev.txt agrees"

destination="$(mktemp -d)"
trap 'rm -rf "$destination"' EXIT

# --no-deps keeps the check about this package rather than its dependency tree.
if output="$(python -m pip download --no-deps --no-cache-dir --quiet --dest "$destination" "$requirement" 2>&1)"; then
    resolved="$(basename "$(find "$destination" -type f \( -name '*.whl' -o -name '*.tar.gz' \) -print -quit)")"
    echo "OK: $requirement is installable from PyPI (resolved ${resolved:-an artifact})"
    exit 0
fi

echo "$output" | tail -5

if echo "$output" | grep -qiE "no matching distribution|could not find a version"; then
    cat >&2 <<EOF
::error::Nothing on PyPI satisfies '$requirement', which this repository pins.
::error::
::error::If the library has not been released yet, publish it first: merge the open
::error::release pull request in KRoperUK/give-blood-py, which publishes to PyPI via
::error::trusted publishing. This job then passes with no change here.
::error::
::error::If the floor was raised ahead of a release, either publish that release or
::error::lower the floor in both $MANIFEST and requirements_dev.txt.
EOF
    exit 1
fi

# Anything else — no pip in the interpreter, a network failure, a PyPI outage — is
# not a missing release and must not be reported as one. Saying "not published"
# when the real cause is a broken runner would send someone off to publish a
# release that already exists.
if echo "$output" | grep -qiE "no module named pip"; then
    echo "::error::This interpreter has no pip, so '$requirement' could not be checked." >&2
    echo "::error::That is an environment problem, not a missing release." >&2
    exit 1
fi

echo "::error::Could not check '$requirement' against PyPI. Judging by the pip output" >&2
echo "::error::above this is a network or PyPI availability problem, not a missing release." >&2
exit 1
