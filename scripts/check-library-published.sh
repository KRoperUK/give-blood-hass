#!/usr/bin/env bash
# Assert that the client-library floor pinned by this repo exists on PyPI.
#
# The floor appears in two files that must agree: manifest.json (what Home
# Assistant installs at runtime) and requirements_dev.txt (what CI installs).
# When it names a version PyPI does not have, every job that installs the library
# fails with an opaque pip resolution error. This produces one legible message
# instead, and names the fix.
#
# The recurring mistake it catches in a paired repo: raising the floor here before
# the library release that satisfies it has actually published.
set -euo pipefail

MANIFEST="custom_components/nhs_give_blood/manifest.json"
PACKAGE="nhs-give-blood"

requirement="$(python -c "
import json, sys
manifest = json.load(open('$MANIFEST'))
for item in manifest['requirements']:
    if item.startswith('$PACKAGE'):
        print(item)
        sys.exit(0)
sys.exit('no $PACKAGE requirement found in $MANIFEST')
")"

floor="${requirement#*>=}"
echo "manifest.json pins: $requirement"
echo "required floor:     $floor"

# Compared with packaging rather than sorted as strings: "0.10.0" sorts below
# "0.9.0" lexically, which would pass a floor it should fail.
python - "$floor" <<'PYTHON'
import json
import sys
import urllib.error
import urllib.request

from packaging.version import InvalidVersion, Version

floor_raw = sys.argv[1]
package = "nhs-give-blood"

try:
    floor = Version(floor_raw)
except InvalidVersion:
    sys.exit(f"::error::could not parse the pinned floor {floor_raw!r} as a version")

url = f"https://pypi.org/pypi/{package}/json"
try:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed https URL
        payload = json.load(response)
except urllib.error.HTTPError as error:
    if error.code == 404:
        print(
            f"::error::{package} is not on PyPI yet, so nothing can satisfy the "
            f">={floor} floor this repository pins.\n"
            "Publish the library first: merge the open release pull request in "
            "KRoperUK/give-blood-py, which publishes to PyPI via trusted publishing. "
            "This job will then pass without any change here."
        )
        sys.exit(1)
    raise
except urllib.error.URLError as error:
    # A network blip must not look like a missing release.
    sys.exit(f"::error::could not reach PyPI to check {package}: {error}")

published = []
for raw in payload.get("releases", {}):
    try:
        published.append(Version(raw))
    except InvalidVersion:
        continue

usable = sorted(version for version in published if version >= floor)
if not usable:
    newest = max(published) if published else None
    print(
        f"::error::{package} is on PyPI, but no release satisfies the >={floor} floor "
        f"this repository pins. Newest published: {newest}.\n"
        "Either publish the library release that satisfies it, or lower the floor in "
        f"{'custom_components/nhs_give_blood/manifest.json'} and requirements_dev.txt "
        "(both must move together)."
    )
    sys.exit(1)

print(f"satisfied by:       {', '.join(str(version) for version in usable[:5])}")
print(f"OK: {package}>={floor} is installable from PyPI")
PYTHON
