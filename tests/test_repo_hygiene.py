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


class TestBrandAssets:
    """HACS fails validation without brand assets or a brands-repository entry.

    Rather than depend on a merged PR to home-assistant/brands, the assets ship
    locally under ``custom_components/nhs_give_blood/brand/``, which is the
    fallback HACS checks. Regenerate them with
    ``python scripts/make_brand_assets.py``.
    """

    BRAND = COMPONENT / "brand"

    REQUIRED = {
        "icon.png": (256, 256),
        "icon@2x.png": (512, 512),
        "dark_icon.png": (256, 256),
        "dark_icon@2x.png": (512, 512),
        "logo.png": (512, 128),
        "logo@2x.png": (1024, 256),
        "dark_logo.png": (512, 128),
        "dark_logo@2x.png": (1024, 256),
    }

    @pytest.mark.parametrize("name", sorted(REQUIRED))
    def test_asset_exists_with_the_expected_dimensions(self, name: str) -> None:
        from PIL import Image

        path = self.BRAND / name
        assert path.is_file(), f"{name} is missing; run scripts/make_brand_assets.py"
        with Image.open(path) as image:
            assert image.size == self.REQUIRED[name], f"{name} is {image.size}"

    def test_assets_have_an_alpha_channel(self) -> None:
        """Home Assistant composites these onto light and dark surfaces."""
        from PIL import Image

        for name in self.REQUIRED:
            with Image.open(self.BRAND / name) as image:
                assert image.mode == "RGBA", f"{name} is {image.mode}"

    def test_svg_sources_are_committed(self) -> None:
        """Artwork should be reviewable as text, not opaque binary history."""
        sources = {path.name for path in (self.BRAND / "src").glob("*.svg")}
        assert sources == {"icon.svg", "dark_icon.svg", "logo.svg", "dark_logo.svg"}

    def test_artwork_avoids_protected_nhs_identity(self) -> None:
        """This is an unofficial project.

        Reusing the NHS logo, wordmark or the NHS blue (#005EB8) would be a
        trademark problem and would imply endorsement that does not exist. The
        mark is a plain droplet in a neutral crimson.
        """
        for path in (self.BRAND / "src").glob("*.svg"):
            content = path.read_text().lower()
            assert "005eb8" not in content, f"{path.name} uses the NHS blue"
            assert "nhs" not in content, f"{path.name} references NHS identity"

    def test_generator_script_is_executable_and_documented(self) -> None:
        script = REPO_ROOT / "scripts" / "make_brand_assets.py"
        assert script.is_file()
        assert "rsvg-convert" in script.read_text(), "the dependency should be documented in the script"


class TestCiWiring:
    """Guards on the CI graph itself, which nothing else would catch."""

    @pytest.fixture(scope="class")
    def workflow(self) -> dict[str, Any]:
        import yaml

        return yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())

    #: Jobs that `pip install -r requirements_test.txt`, and so cannot run until
    #: the pinned client-library floor exists on PyPI.
    LIBRARY_DEPENDENT = ("typecheck", "pre-commit", "test")

    def test_preflight_job_exists(self, workflow: dict[str, Any]) -> None:
        assert "preflight" in workflow["jobs"]

    @pytest.mark.parametrize("job", LIBRARY_DEPENDENT)
    def test_library_dependent_jobs_wait_on_preflight(self, workflow: dict[str, Any], job: str) -> None:
        """Without this, a missing release surfaces as an opaque pip error."""
        needs = workflow["jobs"][job]["needs"]
        needs = [needs] if isinstance(needs, str) else needs
        assert "preflight" in needs, f"{job} installs the library but does not wait on preflight"

    def test_preflight_is_gated_by_the_aggregate_check(self, workflow: dict[str, Any]) -> None:
        """A check nobody gates on is decoration."""
        assert "preflight" in workflow["jobs"]["ci"]["needs"]
        assert "preflight=" in workflow["jobs"]["ci"]["steps"][0]["run"]

    def test_preflight_script_exists_and_is_syntactically_valid(self) -> None:
        script = REPO_ROOT / "scripts" / "check-library-published.sh"
        assert script.is_file()
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, check=False)
        assert result.returncode == 0, result.stderr.decode()

    def test_every_action_is_pinned_to_a_sha(self) -> None:
        """A floating tag is mutable, so a pinned SHA is the only reviewable form."""
        unpinned: list[str] = []
        for path in (REPO_ROOT / ".github" / "workflows").glob("*.yml"):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if not stripped.startswith("- uses:"):
                    continue
                reference = stripped.split("uses:", 1)[1].strip()
                if "@" not in reference:
                    unpinned.append(f"{path.name}:{number}: {reference}")
                    continue
                pin = reference.split("@", 1)[1].split()[0]
                # hacs/action is documented as @main upstream and publishes no
                # tags to pin against.
                if reference.startswith(("hacs/action", "home-assistant/actions")):
                    continue
                if not re.fullmatch(r"[0-9a-f]{40}", pin):
                    unpinned.append(f"{path.name}:{number}: {reference}")
        assert not unpinned, f"actions not pinned to a SHA: {unpinned}"


class TestScriptPortability:
    """Maintainer scripts must run on more than the integration's own Python.

    `pyproject.toml` targets py314 for `custom_components/`, and with that target
    ruff rewrites `except (A, B):` into PEP 758's unparenthesized `except A, B:`,
    which only Python 3.14 can parse. These scripts run under pre-commit's
    interpreter and under whatever a contributor happens to have, so that rewrite
    silently breaks them — it broke the pre-commit job once already.
    """

    #: The oldest interpreter these scripts should parse on. Home Assistant needs
    #: 3.14, but pre-commit and contributors' shells routinely have older.
    OLDEST_SUPPORTED = (3, 12)

    SCRIPTS = sorted((REPO_ROOT / "scripts").glob("*.py"))

    def test_scripts_exist(self) -> None:
        assert self.SCRIPTS

    @pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
    def test_no_version_specific_syntax(self, script: Path) -> None:
        """Compiled against the oldest supported grammar, not just parsed here."""
        source = script.read_text()
        try:
            compile(
                source,
                str(script),
                "exec",
                flags=__import__("ast").PyCF_ONLY_AST,
                dont_inherit=True,
            )
        except SyntaxError as error:  # pragma: no cover - the failure path
            pytest.fail(f"{script.name} does not parse: {error}")

        # The specific rewrite that bit us, checked textually because the running
        # interpreter is 3.14 and would happily parse it.
        offenders = [
            f"line {number}"
            for number, line in enumerate(source.splitlines(), start=1)
            if re.match(r"\s*except\s+[A-Za-z_][\w.]*\s*,", line)
        ]
        assert not offenders, (
            f"{script.name} uses PEP 758 unparenthesized `except A, B:` at "
            f"{offenders}, which Python < 3.14 cannot parse"
        )

    def test_ruff_is_configured_not_to_reintroduce_it(self) -> None:
        """A nested config is what stops `ruff format` undoing the fix.

        The rewrite comes from the formatter, not the linter, so a lint per-file
        ignore does not prevent it — only a lower `target-version` for this
        directory does.
        """
        import tomllib

        config_path = REPO_ROOT / "scripts" / ".ruff.toml"
        assert config_path.is_file(), "scripts/.ruff.toml pins the language target"
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
        target = config["target-version"]
        assert target < "py314", f"scripts target {target}, which permits PEP 758 rewrites"
        assert config["extend"].endswith("pyproject.toml"), "should inherit the root rules"
