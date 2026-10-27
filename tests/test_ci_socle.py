"""La CI du socle, la règle de protection et Dependabot."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import REPONSES_SERVEUR, git

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
        for uses in re.findall(
            r"^\s*(?:-\s*)?uses:\s*(\S+)", chemin.read_text(encoding="utf-8"), re.MULTILINE
        ):
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
    contextes = {
        c["context"]
        for c in regles["required_status_checks"]["parameters"]["required_status_checks"]
    }
    assert contextes == {f"socle / {job['name']}" for job in jobs}
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert {"deletion", "non_fast_forward", "pull_request"} <= set(regles)


@pytest.mark.parametrize("cible", ["aucune", "serveur"])
def test_dependabot(rendre, cible):
    doc = charger(
        rendre(**(REPONSES_SERVEUR if cible == "serveur" else {})), ".github/dependabot.yml"
    )
    (maj,) = [u for u in doc["updates"] if u["package-ecosystem"] == "github-actions"]
    assert maj["cooldown"]["default-days"] == 3
    assert maj["schedule"]["timezone"] == "Europe/Zurich"
    assert {u["package-ecosystem"] for u in doc["updates"]} <= {"github-actions", "docker"}
    # En cible serveur, les images : le Dockerfile du projet et celui de l'image de test.
    docker = [u for u in doc["updates"] if u["package-ecosystem"] == "docker"]
    assert sorted(u["directory"] for u in docker) == (
        ["/", "/tests/deploiement"] if cible == "serveur" else []
    )
    for u in docker:
        assert u["schedule"] == maj["schedule"]
        assert u["cooldown"] == maj["cooldown"]
        assert u["commit-message"] == maj["commit-message"]
        # Une majeure d'image de base est une décision, pas une mise à jour de routine (R93).
        assert u["ignore"] == [
            {"dependency-name": "*", "update-types": ["version-update:semver-major"]}
        ]


# --- revue finale du lot 1 : messages de commit (I4), $RUNNER_TEMP (L.35), garde branché (m4),
# historique complet (I7) ---

HISTORIQUE = ".github/workflows/modele-historique.yml"
SH = shutil.which("sh") or (
    r"C:\Program Files\Git\bin\sh.exe"
    if Path(r"C:\Program Files\Git\bin\sh.exe").exists()
    else None
)


def etape(rendu, nom):
    etapes = charger(rendu, SOCLE)["jobs"]["confidentialite"]["steps"]
    (trouvee,) = [e for e in etapes if e.get("name") == nom]
    return trouvee


def test_messages_de_commit_examines(rendre):
    e = etape(rendre(), "Confidentialité des messages de commit")
    assert e["env"] == {
        "MOTIFS_INTERDITS": "${{ secrets.MOTIFS_INTERDITS }}",
        "DEPOT_PRIVE": "${{ github.event.repository.private }}",
    }
    assert 'git log --format=%B "$BASE..HEAD" > "$RUNNER_TEMP/messages.txt"' in e["run"]
    assert 'git log --format=%B HEAD > "$RUNNER_TEMP/messages.txt"' in e["run"]
    assert 'confidentialite.py --exiger-prives --texte "$RUNNER_TEMP/messages.txt"' in e["run"]


def test_texte_de_pr_dans_runner_temp(rendre):
    e = etape(rendre(), "Confidentialité et format du titre et du corps de la PR")
    assert '> "$RUNNER_TEMP/pr.txt"' in e["run"]
    assert '--texte "$RUNNER_TEMP/pr.txt"' in e["run"]
    assert "pr.txt\n" not in e["run"].replace('"$RUNNER_TEMP/pr.txt"', "")


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_etape_des_messages_refuse_un_motif(rendre, env_isole, tmp_path):
    rendu = rendre()
    run = etape(rendu, "Confidentialité des messages de commit")["run"]
    env = env_isole()
    git(rendu, env, "init", "-q", "-b", "main")
    git(rendu, env, "config", "core.autocrlf", "false")
    git(rendu, env, "add", "-A")
    git(rendu, env, "commit", "-q", "-m", "feat: base")
    base = git(rendu, env, "rev-parse", "HEAD").strip()
    git(rendu, env, "commit", "-q", "--allow-empty", "-m", "feat: x\n\nnoeud 192.168" + ".1.20")
    temp = tmp_path / "runner-temp"
    temp.mkdir()
    env.update(
        MOTIFS_INTERDITS="motif-essai",
        RUNNER_TEMP=str(temp),
        PATH=str(Path(sys.executable).parent) + os.pathsep + env["PATH"],
    )

    def lancer_etape(base):
        return subprocess.run(
            [SH, "-c", run],
            check=False,
            cwd=rendu,
            env={**env, "BASE": base},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    for b in (base, "0" * 40):  # une plage, puis la base nulle (tout l'historique)
        r = lancer_etape(b)
        assert r.returncode == 1, (b, r.stderr)
        assert "messages.txt:3 — adresse IP privée" in r.stderr
        assert "192.168" not in r.stdout + r.stderr
    git(rendu, env, "commit", "-q", "--allow-empty", "-m", "feat: propre")
    apres_le_constat = git(rendu, env, "rev-parse", "HEAD~1").strip()
    assert lancer_etape(apres_le_constat).returncode == 0


def script_du_garde(rendu):
    run = etape(rendu, "Le garde de Claude est branché")["run"]
    assert run.startswith("python - <<'FIN'\n")
    return run.split("\n", 1)[1].rsplit("FIN", 1)[0]


def _avec_matcher(original, matcher):
    doc = json.loads(original)
    doc["hooks"]["PreToolUse"][0]["matcher"] = matcher
    return json.dumps(doc)


def _desactive(original):
    doc = json.loads(original)
    doc["disableAllHooks"] = True
    return json.dumps(doc)


def test_etape_du_garde_branche(rendre):
    rendu = rendre()
    reglages = rendu / ".claude/settings.json"
    original = reglages.read_text(encoding="utf-8")
    cas = [
        ("intact", original, 0),
        ("conflit", "<<<<<<< avant\n" + original + "=======\n{}\n>>>>>>> après\n", 1),
        ("sans garde", '{"hooks": {"PreToolUse": []}}', 1),
        ("absent", None, 1),
        # relecture de la vague, n5 : l'ancien matcher, ou les hooks coupés, ne passent plus
        ("ancien matcher", _avec_matcher(original, "Bash|PowerShell"), 1),
        ("matcher Bash seul", _avec_matcher(original, "Bash"), 1),
        ("matcher universel", _avec_matcher(original, "*"), 0),
        ("matcher sans MCP", _avec_matcher(original, "Bash|PowerShell|Monitor"), 0),
        ("hooks coupés", _desactive(original), 1),
    ]
    for nom, contenu, attendu in cas:
        if contenu is None:
            reglages.unlink(missing_ok=True)
        else:
            reglages.write_text(contenu, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-"],
            input=script_du_garde(rendu),
            check=False,
            cwd=rendu,
            capture_output=True,
            text=True,
        )
        assert r.returncode == attendu, (nom, r.stderr)


def test_historique_complet(rendre):
    rendu = rendre()
    doc = charger(rendu, HISTORIQUE)
    on = declencheurs(doc)
    assert set(on) == {"workflow_dispatch", "schedule"}
    assert on["schedule"] == [{"cron": "0 5 * * 1"}]
    assert doc["permissions"] == {"contents": "read"}
    assert set(doc["jobs"]) == {"historique"}
    job = doc["jobs"]["historique"]
    assert job["name"] == "historique"
    checkout, gitleaks = job["steps"]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}
    etapes_socle = charger(rendu, SOCLE)["jobs"]["secrets"]["steps"]
    (gitleaks_socle,) = [e for e in etapes_socle if "gitleaks" in e.get("uses", "")]
    assert gitleaks["uses"] == gitleaks_socle["uses"]
    assert gitleaks["env"] == gitleaks_socle["env"]
    assert "${{ secrets.GITHUB_TOKEN }}" in (rendu / HISTORIQUE).read_text(encoding="utf-8")


def test_historique_hors_contextes_requis(rendre):
    rendu = rendre()
    ruleset = json.loads((rendu / ".github/modele/ruleset-main.json").read_text(encoding="utf-8"))
    regles = {r["type"]: r for r in ruleset["rules"]}
    contextes = {
        c["context"]
        for c in regles["required_status_checks"]["parameters"]["required_status_checks"]
    }
    assert contextes == {"socle / secrets", "socle / confidentialite"}


def test_la_porte_recoit_la_visibilite_reelle(rendre):
    """En CI, la visibilité réelle du dépôt l'emporte sur reglages.py (relecture de la vague, n1)."""
    etapes = charger(rendre(), SOCLE)["jobs"]["confidentialite"]["steps"]
    portes = [e for e in etapes if "confidentialite.py" in e.get("run", "")]
    assert [e["name"] for e in portes] == [
        "Confidentialité du diff",
        "Confidentialité des messages de commit",
        "Confidentialité et format du titre et du corps de la PR",
    ]
    for e in portes:
        assert e["env"]["DEPOT_PRIVE"] == "${{ github.event.repository.private }}", e["name"]


def test_secrets_chiffres_controles(rendre):
    etapes = charger(rendre(), SOCLE)["jobs"]["secrets"]["steps"]
    python = next(i for i, e in enumerate(etapes) if "setup-python" in e.get("uses", ""))
    controle = next(
        i
        for i, e in enumerate(etapes)
        if e.get("run") == "python scripts/modele/verifier_secrets.py"
    )
    assert python < controle
    depot = yaml.safe_load(Path(CI).read_text(encoding="utf-8"))["jobs"]["secrets"]["steps"]
    assert any(e.get("run") == "python template/scripts/modele/verifier_secrets.py" for e in depot)
