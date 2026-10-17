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
