"""Documentation hygiene tests.

The docs site is published to give-blood-hass.kroper.uk on every push to main, so
a broken nav entry or a dropped CNAME becomes a live problem rather than a local
one. These checks are cheap enough to run with the rest of the suite.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
CONFIG = REPO_ROOT / "zensical.toml"
SITE_DOMAIN = "give-blood-hass.kroper.uk"


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    """The parsed zensical configuration."""
    with CONFIG.open("rb") as handle:
        return tomllib.load(handle)["project"]


def _nav_pages(node: Any) -> list[str]:
    """Every markdown path referenced by the nav tree, at any depth."""
    pages: list[str] = []
    if isinstance(node, str):
        if node.endswith(".md"):
            pages.append(node)
    elif isinstance(node, list):
        for item in node:
            pages.extend(_nav_pages(item))
    elif isinstance(node, dict):
        for value in node.values():
            pages.extend(_nav_pages(value))
    return pages


class TestConfig:
    """The site configuration itself."""

    def test_site_url_matches_the_published_domain(self, config: dict[str, Any]) -> None:
        assert config["site_url"].rstrip("/").endswith(SITE_DOMAIN)

    def test_repo_links_are_set(self, config: dict[str, Any]) -> None:
        """`content.action.edit` renders a broken link without these."""
        assert config["repo_url"].startswith("https://github.com/")
        assert config["edit_uri"]

    def test_copyright_carries_the_disclaimer(self, config: dict[str, Any]) -> None:
        """It renders in every page footer, which is where it needs to be."""
        assert "not affiliated" in config["copyright"].lower()
        assert "nhs blood and transplant" in config["copyright"].lower()

    def test_custom_palette_has_its_stylesheet(self, config: dict[str, Any]) -> None:
        """`primary = "custom"` silently falls back without the CSS variables."""
        palettes = config["theme"]["palette"]
        if not any(entry.get("primary") == "custom" for entry in palettes):
            pytest.skip("no custom palette configured")
        assert "stylesheets/extra.css" in config["extra_css"]
        assert (DOCS / "stylesheets" / "extra.css").is_file()

    def test_mermaid_fence_is_restored(self, config: dict[str, Any]) -> None:
        """Declaring superfences replaces zensical's default custom_fences."""
        superfences = config["markdown_extensions"]["pymdownx"]["superfences"]
        names = {fence["name"] for fence in superfences.get("custom_fences", [])}
        assert "mermaid" in names


class TestPages:
    """Nav and file consistency."""

    def test_every_nav_page_exists(self, config: dict[str, Any]) -> None:
        missing = [page for page in _nav_pages(config["nav"]) if not (DOCS / page).is_file()]
        assert not missing, f"nav references missing pages: {missing}"

    def test_every_page_is_in_the_nav(self, config: dict[str, Any]) -> None:
        """An orphan page is only reachable by URL, so it may as well not exist."""
        navigated = set(_nav_pages(config["nav"]))
        on_disk = {str(path.relative_to(DOCS)) for path in DOCS.rglob("*.md") if "includes" not in path.parts}
        assert on_disk == navigated, f"nav and docs/ disagree: {on_disk ^ navigated}"

    def test_there_is_a_home_page(self) -> None:
        assert (DOCS / "index.md").is_file()

    def test_every_page_has_a_heading(self) -> None:
        """A page without an H1 gets an unhelpful auto-generated nav title."""
        for path in DOCS.rglob("*.md"):
            lines = [line for line in path.read_text().splitlines() if line.strip()]
            body = [line for line in lines if not line.startswith("---")]
            assert any(line.startswith("# ") for line in body[:12]), path.name


class TestCustomDomain:
    """The CNAME is what keeps the custom domain bound across deployments."""

    def test_cname_exists_and_matches(self) -> None:
        cname = DOCS / "CNAME"
        assert cname.is_file(), "docs/CNAME is required or GitHub Pages drops the custom domain"
        assert cname.read_text().strip() == SITE_DOMAIN

    def test_cname_is_a_single_bare_hostname(self) -> None:
        """GitHub Pages rejects a scheme, a path, or multiple lines."""
        content = DOCS / "CNAME"
        lines = [line for line in content.read_text().splitlines() if line.strip()]
        assert len(lines) == 1
        assert "://" not in lines[0]
        assert "/" not in lines[0]

    def test_the_workflow_verifies_the_domain(self) -> None:
        """A silent CNAME loss unbinds the domain, so CI asserts on it."""
        workflow = (REPO_ROOT / ".github" / "workflows" / "docs.yml").read_text()
        assert "site/CNAME" in workflow
        assert SITE_DOMAIN in workflow


class TestLinks:
    """Internal link integrity."""

    def test_relative_markdown_links_resolve(self) -> None:
        pattern = re.compile(r"\]\((?!https?://|mailto:|#)([^)#]+\.md)(?:#[^)]*)?\)")
        broken: list[str] = []

        for path in DOCS.rglob("*.md"):
            for target in pattern.findall(path.read_text()):
                if not (path.parent / target).resolve().is_file():
                    broken.append(f"{path.relative_to(REPO_ROOT)} -> {target}")

        assert not broken, f"broken internal links: {broken}"

    def test_docs_are_reachable_from_the_readme(self) -> None:
        assert SITE_DOMAIN in (REPO_ROOT / "README.md").read_text()


class TestAccuracy:
    """Cheap guards against the docs drifting from the code."""

    def test_documented_entity_ids_exist_in_the_catalogue(self) -> None:
        """Catches a renamed sensor that the entity reference still advertises."""
        from custom_components.nhs_give_blood.binary_sensor import BINARY_SENSORS
        from custom_components.nhs_give_blood.sensor import SENSORS

        known = {f"sensor.nhs_give_blood_{description.key}" for description in SENSORS}
        known |= {f"binary_sensor.nhs_give_blood_{description.key}" for description in BINARY_SENSORS}
        known |= {"calendar.nhs_give_blood_appointments"}

        # Entity ids are derived from translated names, so a handful legitimately
        # differ from their description key.
        aliases = {"sensor.nhs_give_blood_can_book_from": "sensor.nhs_give_blood_bookable_from"}

        pattern = re.compile(r"\b((?:sensor|binary_sensor|calendar)\.nhs_give_blood_[a-z0-9_]+)\b")
        unknown: set[str] = set()
        for path in (*DOCS.rglob("*.md"), REPO_ROOT / "README.md"):
            for entity_id in pattern.findall(path.read_text()):
                resolved = aliases.get(entity_id, entity_id)
                if resolved not in known and entity_id not in known:
                    unknown.add(f"{path.name}: {entity_id}")

        assert not unknown, f"docs mention unknown entities: {sorted(unknown)}"

    def test_documented_ha_floor_matches_hacs_json(self) -> None:
        import json

        floor = json.loads((REPO_ROOT / "hacs.json").read_text())["homeassistant"]
        major_minor = ".".join(floor.split(".")[:2])
        installation = (DOCS / "installation.md").read_text()
        assert major_minor in installation, f"installation.md does not mention the {floor} floor"

    def test_read_only_stance_is_documented(self) -> None:
        """The design decision and the enforcing test must not drift apart."""
        design = (DOCS / "design.md").read_text().lower()
        assert "read-only" in design
        assert "cancel" in design
