"""Le dépôt modèle applique ses propres garde-fous, à sa racine."""

import json

import yaml
from conftest import RACINE

CI = RACINE / ".github/workflows/ci.yml"


def test_ruleset_du_depot_modele():
    ruleset = json.loads((RACINE / ".github/ruleset-main.json").read_text(encoding="utf-8"))
    regles = {r["type"]: r for r in ruleset["rules"]}
    contextes = {c["context"] for c in regles["required_status_checks"]["parameters"]["required_status_checks"]}
    assert contextes == {"tests (ubuntu-latest)", "tests (windows-latest)", "secrets", "confidentialite"}

    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    produits = set()
    for job in jobs.values():
        oses = job.get("strategy", {}).get("matrix", {}).get("os")
        if oses:
            produits |= {f"{job['name']} ({os})" for os in oses}
        else:
            produits.add(job["name"])
    assert contextes <= produits


def test_claude_md_du_depot_modele():
    premiere = (RACINE / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[0]
    assert premiere == "@template/docs/modele/methode.md"


def test_hooks_du_depot_modele():
    hooks = sorted((RACINE / ".githooks").iterdir())
    assert {h.name for h in hooks} == {"pre-commit", "commit-msg", "pre-push"}
    for hook in hooks:
        assert "template/scripts/modele/" in hook.read_text(encoding="utf-8"), hook.name
    assert "--branche main" in (RACINE / ".githooks/pre-push").read_text(encoding="utf-8")


def test_settings_du_depot_modele():
    reglage = json.loads((RACINE / ".claude/settings.json").read_text(encoding="utf-8"))
    crochet = reglage["hooks"]["PreToolUse"][0]
    assert crochet["matcher"] == "Bash|PowerShell|Monitor|mcp__.*"
    assert "template/scripts/modele/garde_claude.py" in crochet["hooks"][0]["command"]


def test_dependabot_du_depot_modele():
    """Le second bloc tient à jour les épinglages des workflows gérés (revue finale, I6)."""
    doc = yaml.safe_load((RACINE / ".github/dependabot.yml").read_text(encoding="utf-8"))
    dossiers = [u["directory"] for u in doc["updates"] if u["package-ecosystem"] == "github-actions"]
    assert dossiers == ["/", "/template/.github/workflows"]
    assert list((RACINE / "template/.github/workflows").glob("*.yml"))


def test_historique_du_depot_modele():
    racine = (RACINE / ".github/workflows/historique.yml").read_text(encoding="utf-8")
    modele = (RACINE / "template/.github/workflows/modele-historique.yml").read_text(encoding="utf-8")
    assert racine.split("\n", 1)[1] == modele.split("\n", 1)[1]


def test_ci_du_depot_modele_revoit_une_pr_modifiee():
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    on = doc.get("on", doc.get(True))
    assert on["pull_request"]["types"] == ["opened", "synchronize", "reopened", "edited"]


def test_ci_du_depot_modele_suit_le_socle():
    """Les étapes du job confidentialite du dépôt modèle sont celles du socle, chemins préfixés."""
    socle = yaml.safe_load(
        (RACINE / "template/.github/workflows/modele-socle.yml").read_text(encoding="utf-8")
    )
    racine = yaml.safe_load(CI.read_text(encoding="utf-8"))
    attendues = [
        {**e, "run": e["run"].replace("scripts/modele/", "template/scripts/modele/")} if "run" in e else e
        for e in socle["jobs"]["confidentialite"]["steps"]
    ]
    assert racine["jobs"]["confidentialite"]["steps"] == attendues
