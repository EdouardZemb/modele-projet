"""Le dépôt modèle applique ses propres garde-fous, à sa racine."""

import json
import re

import yaml
from conftest import RACINE

CI = RACINE / ".github/workflows/ci.yml"


def test_ruleset_du_depot_modele():
    ruleset = json.loads((RACINE / ".github/ruleset-main.json").read_text(encoding="utf-8"))
    regles = {r["type"]: r for r in ruleset["rules"]}
    contextes = {
        c["context"]
        for c in regles["required_status_checks"]["parameters"]["required_status_checks"]
    }
    assert contextes == {
        "tests (ubuntu-latest)",
        "tests (windows-latest)",
        "secrets",
        "confidentialite",
        "mecanique",
        "fausse-app",
    }

    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    produits = set()
    for job in jobs.values():
        oses = job.get("strategy", {}).get("matrix", {}).get("os")
        if oses:
            produits |= {f"{job['name']} ({os})" for os in oses}
        else:
            produits.add(job["name"])
    assert contextes <= produits


def test_mecanique_et_fausse_app_dans_la_ci_du_depot_modele():
    """R17 : seul le job mecanique lance les bats ; fausse-app passe l'action d'image d'un rendu."""
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]

    def commandes(job):
        return [e["run"] for e in jobs[job]["steps"] if "run" in e]

    (pytest_tests,) = [c for c in commandes("tests") if "pytest" in c]
    assert pytest_tests == "python -m pytest -q --ignore=tests/test_mecanique.py"
    installation = next(c for c in commandes("tests") if "sans_saut=" in c)
    listes = [set(s.split(",")) for s in re.findall(r"sans_saut=(\S+)", installation)]
    # Windows, puis Ubuntu. bash : les étapes de CI lancées par test_ci_serveur.py (R20).
    assert listes == [
        {"sops", "age", "age-keygen", "powershell", "bash"},
        {"sops", "age", "age-keygen", "pwsh", "shellcheck", "bash"},
    ]

    mecanique = jobs["mecanique"]
    assert mecanique["runs-on"] == "ubuntu-latest"
    (bats,) = [e for e in mecanique["steps"] if "test_mecanique" in e.get("run", "")]
    assert bats["run"] == "python -m pytest -q tests/test_mecanique.py"
    assert bats["env"] == {"MODELE_TESTS_SANS_SAUT": "1"}

    fausse_app = jobs["fausse-app"]
    assert fausse_app["runs-on"] == "ubuntu-latest"
    texte = "\n".join(commandes("fausse-app"))
    for fragment in (
        "copier copy --vcs-ref HEAD --defaults --trust",
        "--data nom=fausse-app",
        "--data cible=serveur",
        "--data bloc_ports=4310",
        # explicite : la preuve de la sauvegarde ne dépend pas d'un défaut de copier.yml (R20)
        "--data sauvegardes=true",
        ". rendu",
        "cp tests/modele/fausse-app/* rendu/",
    ):
        assert fragment in texte, fragment
    (construire,) = [e for e in fausse_app["steps"] if "uses" in e and "modele-image" in e["uses"]]
    assert construire == {
        "uses": "./rendu/.github/actions/modele-image-construire",
        "with": {"dossier": "rendu"},
    }
    rendu_avant = [
        i for i, e in enumerate(fausse_app["steps"]) if "copier copy" in e.get("run", "")
    ]
    assert rendu_avant and rendu_avant[0] < fausse_app["steps"].index(construire)
    # L'épreuve du ménage des images (#19), sur le vrai Docker du job, après la construction.
    (epreuve,) = [e for e in fausse_app["steps"] if "epreuve-menage" in e.get("run", "")]
    assert epreuve["run"] == "bash tests/modele/epreuve-menage.sh rendu"
    assert fausse_app["steps"].index(construire) < fausse_app["steps"].index(epreuve)
    # Le registre et les conteneurs de l'épreuve sont retirés quoi qu'il arrive, puis la fausse app :
    # ce dernier retrait ferme le job.
    (menage,) = [e for e in fausse_app["steps"] if "epreuve-registre" in e.get("run", "")]
    assert menage["if"] == "always()"
    assert "docker rm -f -v epreuve-registre epreuve-conteneur" in menage["run"]
    assert fausse_app["steps"].index(epreuve) < fausse_app["steps"].index(menage)
    assert fausse_app["steps"][-1]["if"] == "always()"
    assert fausse_app["steps"][-1]["run"] == "docker rm -f -v fausse-app"
    assert fausse_app["steps"].index(menage) < len(fausse_app["steps"]) - 1


def test_claude_md_du_depot_modele():
    premiere = (RACINE / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[0]
    assert premiere == "@template/docs/modele/methode.md"


def test_hooks_du_depot_modele():
    hooks = sorted((RACINE / ".githooks").iterdir())
    assert {h.name for h in hooks} == {"pre-commit", "commit-msg", "pre-push"}
    for hook in hooks:
        assert "template/scripts/modele/" in hook.read_text(encoding="utf-8"), hook.name
    pre_commit = (RACINE / ".githooks/pre-commit").read_text(encoding="utf-8")
    assert "template/scripts/modele/masques.py" in pre_commit
    assert pre_commit.index("masques.py") < pre_commit.index("confidentialite.py")
    assert "--branche main" in (RACINE / ".githooks/pre-push").read_text(encoding="utf-8")


def test_settings_du_depot_modele():
    reglage = json.loads((RACINE / ".claude/settings.json").read_text(encoding="utf-8"))
    crochet = reglage["hooks"]["PreToolUse"][0]
    assert crochet["matcher"] == "Bash|PowerShell|Monitor|mcp__.*"
    assert "template/scripts/modele/garde_claude.py" in crochet["hooks"][0]["command"]
    assert "--branche main --fusion session" in crochet["hooks"][0]["command"]
    (groupe,) = reglage["hooks"]["SessionStart"]
    assert groupe["matcher"] == "startup|resume"
    (signaux,) = groupe["hooks"]
    assert signaux["timeout"] == 30
    assert "template/scripts/modele/signaux.py" in signaux["command"]
    assert signaux["command"].endswith("--branche main")


def test_dependabot_du_depot_modele():
    """Les épinglages du dépôt et des workflows gérés (revue finale, I6) montent dans la même PR.

    Une PR par dossier ne peut pas passer : test_ci_du_depot_modele_suit_le_socle exige les mêmes
    étapes des deux côtés.
    """
    doc = yaml.safe_load((RACINE / ".github/dependabot.yml").read_text(encoding="utf-8"))
    actions = [u for u in doc["updates"] if u["package-ecosystem"] == "github-actions"]
    assert len(actions) == 1
    assert actions[0]["directories"] == ["/", "/template/.github/workflows"]
    assert "directory" not in actions[0]
    groupes = actions[0]["groups"]
    assert [g["group-by"] for g in groupes.values()] == ["dependency-name"]
    assert list((RACINE / "template/.github/workflows").glob("*.yml"))
    # L'image de la fausse app, épinglée par empreinte, suit aussi ses versions (V8), sans majeure.
    (docker,) = [u for u in doc["updates"] if u["package-ecosystem"] == "docker"]
    assert docker["directory"] == "/tests/modele/fausse-app"
    assert (RACINE / "tests/modele/fausse-app/Dockerfile").is_file()
    for cle in ("schedule", "cooldown", "commit-message"):
        assert docker[cle] == actions[0][cle]
    assert docker["ignore"] == [
        {"dependency-name": "*", "update-types": ["version-update:semver-major"]}
    ]


def test_historique_du_depot_modele():
    racine = (RACINE / ".github/workflows/historique.yml").read_text(encoding="utf-8")
    modele = (RACINE / "template/.github/workflows/modele-historique.yml").read_text(
        encoding="utf-8"
    )
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
        {**e, "run": e["run"].replace("scripts/modele/", "template/scripts/modele/")}
        if "run" in e
        else e
        for e in socle["jobs"]["confidentialite"]["steps"]
    ]
    assert racine["jobs"]["confidentialite"]["steps"] == attendues


def test_liste_d_alignement():
    texte = (RACINE / "docs/aligner.md").read_text(encoding="utf-8")
    assert texte.splitlines()[0] == "# Aligner un projet existant sur le modèle"
    for fragment in (
        "copier copy --defaults --vcs-ref",
        "git diff --name-only",
        "@docs/modele/methode.md",
        "needs:",
        "edited",
        "`.claude/settings.local.json` et `__pycache__/`",
        "`.githooks` et `scripts/modele`",
        "excluent les chemins",
        "extensions.worktreeConfig",
        "--app dependabot",
        "squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY",
        "ruleset-main.json",
        "gh workflow run modele-historique.yml",
        "en avance rapide",
        "--dry-run",
        "aucune PR",
        "## Avant de passer un dépôt privé en public",
        "visibilite=public",
        "git log -p --all --no-textconv --no-ext-diff --format='%H%n%B'",
        "--exiger-prives --public --texte",
        "commit unique propre",
        "gh run list --branch",
        "--exiger-prives --index",
        ".gitleaksignore",
        # passer en cible serveur (lot 2)
        "## Passer en cible `serveur`",
        "--data cible=serveur",
        "modele-image-construire",
        "modele-version.yml",
        "se fusionne à la main",
        "--data fusion=<session|edouard>",
        "que le modèle ne sème pas",
        # V10 : les fichiers semés que le projet a déjà ne reçoivent rien de copier update
        "les deux blocs `package-ecosystem: docker` de `.github/dependabot.yml`",
        "a déjà un `docs/exploitation.md`",
        # I3 : activer les sauvegardes sur un projet en service
        "### Activer les sauvegardes sur un projet en service",
        "--data sauvegardes=true",
        "`SAUVEGARDER=<mots>` et `VERIFIER=<mots>`",
        "`HC_TEST_RESTAURATION`",
        "`TEST_RESTAURATION` à `projets/<nom>.env`",
        "Le premier déploiement ne prend pas d'instantané",
        # C0 : un état qu'une restauration ne doit pas défaire
        "déclare `REPORTER` et `REPORTER_SECTION` dans `deploiement/projet.env`",
        # revue finale du lot 2 (M6) : le tunnel d'un projet, ses instantanés d'avant l'alignement
        "**Un projet qui a déjà son propre tunnel**",
        "`--remove-orphans`",
        "« Faire passer une route d'un tunnel à un autre »",
        "**Les instantanés d'avant l'alignement**",
        # tout l'ancien deploiement/ : l'ancien restaurer.sh charge sa lib.sh à côté de lui
        "archive <commit> deploiement | tar -x -C <dossier temporaire>",
    ):
        assert fragment in texte, fragment
    # le seul script ne suffit pas, il lui faut son arbre (revue des corrections du lot 2, I2)
    assert ":deploiement/restaurer.sh` dans un fichier temporaire" not in texte
    # avant le commit, --diff compare <base>...HEAD et n'examine rien (LE-15)
    assert "--exiger-prives --diff" not in texte
    # la liste suit la méthode, qui n'indexe que par chemins explicites
    for tout_indexer in ("git add -A", "git add ."):
        assert tout_indexer not in texte, tout_indexer
    assert "git add -- <chemins>" in texte
    for lien in ("CLAUDE.md", "README.md"):
        assert "docs/aligner.md" in (RACINE / lien).read_text(encoding="utf-8"), lien
