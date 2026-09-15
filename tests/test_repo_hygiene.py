"""Repository hygiene tests.

Three classes of mistake these catch, all of which are easy to make and slow to
notice:

* a translation key added to one file but not the other, so the UI shows a raw key;
* a version bumped in ``manifest.json`` but not ``const.py``, so diagnostics lie;
* real PII committed into the repo, which the API's payloads make very easy.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "nhs_give_blood"


def _load_guard() -> ModuleType:
    """Import ``scripts/check_pii.py``, which isn't an installed module."""
    path = REPO_ROOT / "scripts" / "check_pii.py"
    spec = importlib.util.spec_from_file_location("check_pii_hass", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_pii_hass"] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def _flatten(node: Any, prefix: str = "") -> set[str]:
    """Every leaf path in a nested mapping, dotted."""
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                keys |= _flatten(value, child)
            else:
                keys.add(child)
    return keys


class TestManifest:
    """``manifest.json`` is what hassfest and HACS validate against."""

    @pytest.fixture
    def manifest(self) -> dict[str, Any]:
        return json.loads((COMPONENT / "manifest.json").read_text())

    def test_required_keys_are_present(self, manifest: dict[str, Any]) -> None:
        for key in (
            "domain",
            "name",
            "codeowners",
            "config_flow",
            "documentation",
            "iot_class",
            "issue_tracker",
            "requirements",
            "version",
        ):
            assert key in manifest, f"manifest.json is missing {key}"

    def test_domain_matches_the_package_directory(self, manifest: dict[str, Any]) -> None:
        assert manifest["domain"] == COMPONENT.name

    def test_iot_class_is_cloud_polling(self, manifest: dict[str, Any]) -> None:
        assert manifest["iot_class"] == "cloud_polling"

    def test_key_order_matches_home_assistant_convention(self, manifest: dict[str, Any]) -> None:
        """domain and name first, then alphabetical — what hassfest expects."""
        keys = list(manifest)
        assert keys[:2] == ["domain", "name"]
        assert keys[2:] == sorted(keys[2:])

    def test_library_is_pinned_as_a_floor(self, manifest: dict[str, Any]) -> None:
        requirement = next(item for item in manifest["requirements"] if "nhs-give-blood" in item)
        assert ">=" in requirement, "a floor pin lets HA resolve patches without a release here"

    def test_library_floor_matches_requirements_dev(self, manifest: dict[str, Any]) -> None:
        """Two files must move together, so assert they agree."""
        manifest_pin = next(item for item in manifest["requirements"] if "nhs-give-blood" in item)
        dev = (REPO_ROOT / "requirements_dev.txt").read_text()
        assert manifest_pin in dev, f"requirements_dev.txt does not pin {manifest_pin}"

    def test_version_matches_const(self, manifest: dict[str, Any]) -> None:
        """Diagnostics report `const.VERSION`; a drift makes bug reports misleading."""
        from custom_components.nhs_give_blood.const import VERSION

        assert manifest["version"] == VERSION

    def test_const_version_carries_the_release_please_marker(self) -> None:
        """Without the marker, release-please silently stops bumping const.py."""
        source = (COMPONENT / "const.py").read_text()
        assert re.search(r'VERSION:\s*Final\s*=\s*"[^"]+"\s*#\s*x-release-please-version', source)


class TestTranslations:
    """A key present in one file and not the other shows a raw key in the UI."""

    @pytest.fixture
    def strings(self) -> dict[str, Any]:
        return json.loads((COMPONENT / "strings.json").read_text())

    @pytest.fixture
    def english(self) -> dict[str, Any]:
        return json.loads((COMPONENT / "translations" / "en.json").read_text())

    def test_english_matches_strings_exactly(self, strings: dict[str, Any], english: dict[str, Any]) -> None:
        assert _flatten(english) == _flatten(strings)

    def test_every_error_and_abort_reason_is_translated(self, strings: dict[str, Any]) -> None:
        errors = strings["config"]["error"]
        aborts = strings["config"]["abort"]

        assert {"cannot_connect", "invalid_auth", "unknown"} <= set(errors)
        assert {"already_configured", "reauth_successful", "wrong_account"} <= set(aborts)

    def test_every_entity_has_a_translated_name(self, strings: dict[str, Any]) -> None:
        """A missing name renders as the translation key, which looks broken."""
        from custom_components.nhs_give_blood.binary_sensor import BINARY_SENSORS
        from custom_components.nhs_give_blood.sensor import SENSORS

        translated = strings["entity"]
        for description in SENSORS:
            assert description.translation_key in translated["sensor"], description.key
        for description in BINARY_SENSORS:
            assert description.translation_key in translated["binary_sensor"], description.key
        assert "appointments" in translated["calendar"]

    def test_icons_json_covers_every_entity(self) -> None:
        from custom_components.nhs_give_blood.binary_sensor import BINARY_SENSORS
        from custom_components.nhs_give_blood.sensor import SENSORS

        icons = json.loads((COMPONENT / "icons.json").read_text())["entity"]
        for description in SENSORS:
            assert description.translation_key in icons["sensor"], description.key
        for description in BINARY_SENSORS:
            assert description.translation_key in icons["binary_sensor"], description.key


class TestEntityDescriptions:
    """Catalogue-level invariants."""

    def test_sensor_keys_are_unique(self) -> None:
        from custom_components.nhs_give_blood.sensor import SENSORS

        keys = [description.key for description in SENSORS]
        assert len(keys) == len(set(keys))

    def test_binary_sensor_keys_are_unique(self) -> None:
        from custom_components.nhs_give_blood.binary_sensor import BINARY_SENSORS

        keys = [description.key for description in BINARY_SENSORS]
        assert len(keys) == len(set(keys))

    def test_translation_keys_match_entity_keys(self) -> None:
        """Divergence here makes the catalogue hard to reason about."""
        from custom_components.nhs_give_blood.binary_sensor import BINARY_SENSORS
        from custom_components.nhs_give_blood.sensor import SENSORS

        for description in (*SENSORS, *BINARY_SENSORS):
            assert description.translation_key == description.key, description.key

    def test_shrinkable_attributes_only_name_keys_the_sensor_produces(self) -> None:
        """A stale name would silently disable the byte-budget protection."""
        from custom_components.nhs_give_blood.sensor import SENSORS

        for description in SENSORS:
            if not description.shrinkable_attributes:
                continue
            assert description.attributes_fn is not None, description.key


class TestNoWriteOperations:
    """The integration is read-only, and that has to stay verifiable.

    The library can book and cancel appointments. Exposing that through an entity
    or action would put an irreversible real-world change behind anything that can
    call a service — which is a very different risk class from reading data.
    """

    def test_no_module_calls_a_write_endpoint(self) -> None:
        forbidden = ("async_book_appointment", "async_reschedule_appointment", "async_cancel_appointment")
        offenders: list[str] = []

        for path in COMPONENT.rglob("*.py"):
            source = path.read_text()
            offenders.extend(f"{path.relative_to(REPO_ROOT)}: {name}" for name in forbidden if name in source)

        assert not offenders, f"write operations referenced: {offenders}"

    def test_no_services_yaml_is_shipped(self) -> None:
        assert not (COMPONENT / "services.yaml").exists()


class TestPiiGuard:
    """The guard must pass over its own repository."""

    def test_no_findings_in_tree(self) -> None:
        paths = [
            path
            for pattern in ("*.py", "*.md", "*.json", "*.toml", "*.yaml", "*.yml", "*.txt")
            for path in REPO_ROOT.rglob(pattern)
            if not guard.should_skip(path.relative_to(REPO_ROOT))
        ]
        findings = {
            f"{path.relative_to(REPO_ROOT)}:{number}: {finding}"
            for path in paths
            for number, finding in guard.scan_file(path)
        }
        assert not findings, f"PII guard found issues in-tree: {sorted(findings)}"

    def test_guard_still_catches_real_values(self) -> None:
        """A guard that has quietly stopped working is worse than none."""
        assert guard.scan_line('email = "real.person@gmail.com"')  # pii-allow - invented negative case
        assert guard.scan_line('"postcode": "AB12 3CD"')  # pii-allow - invented negative case
        assert guard.scan_line('"donorID": "D1234567"')  # pii-allow - invented negative case

    def test_env_file_is_not_tracked_by_git(self) -> None:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            pytest.skip("not a git working tree")
        tracked = {Path(name) for name in result.stdout.split("\0") if name}
        offenders = {path for path in tracked if path.name.endswith(".env") and path.name != ".env.example"}
        assert not offenders, f"credential file(s) tracked: {sorted(map(str, offenders))}"

    def test_gitignore_excludes_credentials(self) -> None:
        patterns = {line.strip() for line in (REPO_ROOT / ".gitignore").read_text().splitlines()}
        assert ".env" in patterns or "*.env" in patterns
