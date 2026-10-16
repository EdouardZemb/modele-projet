"""La CI du socle, la règle de protection et Dependabot."""

import json
import re

import yaml

SOCLE = ".github/workflows/modele-socle.yml"
CI = ".github/workflows/ci.yml"


def charger(rendu, chemin):
    return yaml.safe_load((rendu / chemin).read_text(encoding="utf-8"))


def declencheurs(doc):
    # PyYAML lit la clé `on` comme True.
    return doc.get("on", doc.get(True))


def test_socle_reutilisable(rendre):
    doc = charger(rendre(), SOCLE)
    assert "workflow_call" in declencheurs(doc)
    assert set(doc["jobs"]) == {"secrets", "confidentialite"}
    for identifiant, job in doc["jobs"].items():
        assert job["name"] == identifiant


def test_actions_epinglees(rendre):
    rendu = rendre()
    for chemin in (rendu / ".github/workflows").glob("*.yml"):
        for uses in re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", chemin.read_text(encoding="utf-8"), re.MULTILINE):
            if not uses.startswith("./"):
                assert re.search(r"@[0-9a-f]{40}\b", uses), f"{chemin.name}: {uses}"


def test_expressions_github_intactes(rendre):
    rendu = rendre()
    assert "${{ github.ref }}" in (rendu / CI).read_text(encoding="utf-8")
    assert "${{ secrets.GITHUB_TOKEN }}" in (rendu / SOCLE).read_text(encoding="utf-8")


def test_ci_appelle_le_socle(rendre):
    job = charger(rendre(), CI)["jobs"]["socle"]
    assert job["uses"] == "./.github/workflows/modele-socle.yml"
    assert job["secrets"] == "inherit"


def test_ci_pousse_sur_branche_principale(rendre):
    doc = charger(rendre(branche_principale="principal"), CI)
    assert declencheurs(doc)["push"]["branches"] == ["principal"]


def test_ruleset_coherent(rendre):
    rendu = rendre()
    jobs = charger(rendu, SOCLE)["jobs"].values()
    ruleset = json.loads((rendu / ".github/modele/ruleset-main.json").read_text(encoding="utf-8"))
    regles = {r["type"]: r for r in ruleset["rules"]}
    contextes = {c["context"] for c in regles["required_status_checks"]["parameters"]["required_status_checks"]}
    assert contextes == {f"socle / {job['name']}" for job in jobs}
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert {"deletion", "non_fast_forward", "pull_request"} <= set(regles)


def test_dependabot(rendre):
    doc = charger(rendre(), ".github/dependabot.yml")
    (maj,) = [u for u in doc["updates"] if u["package-ecosystem"] == "github-actions"]
    assert maj["cooldown"]["default-days"] == 3
    assert maj["schedule"]["timezone"] == "Europe/Zurich"
