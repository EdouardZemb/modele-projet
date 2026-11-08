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
from conftest import RACINE, REPONSES_SERVEUR, git, sans_echappatoire
from test_plan import A_PY, plan

SOCLE = ".github/workflows/modele-socle.yml"
CI = ".github/workflows/ci.yml"
TEXTE_PR = ".github/workflows/modele-texte-pr.yml"
# Les étapes du job `texte-pr`, dans leur ordre.
ETAPES_TEXTE_PR = (
    "Confidentialité et format du titre et du corps de la PR",
    "Les issues que la PR ferme (API)",
    "Les écarts à la spec et la tête relue",
)


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
    """Les contextes requis : chaque job du socle, appelé par `ci.yml`, et chaque job de
    `modele-texte-pr.yml`, qui tourne seul, sans préfixe."""
    rendu = rendre()
    jobs = charger(rendu, SOCLE)["jobs"].values()
    jobs_texte = charger(rendu, TEXTE_PR)["jobs"].values()
    ruleset = json.loads((rendu / ".github/modele/ruleset-main.json").read_text(encoding="utf-8"))
    regles = {r["type"]: r for r in ruleset["rules"]}
    contextes = {
        c["context"]
        for c in regles["required_status_checks"]["parameters"]["required_status_checks"]
    }
    assert contextes == {f"socle / {job['name']}" for job in jobs} | {
        job["name"] for job in jobs_texte
    }
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
        "BRANCHE_DEFAUT": "${{ github.event.repository.default_branch }}",
    }
    assert 'git log --format=%B "$BASE..HEAD" > "$RUNNER_TEMP/messages.txt"' in e["run"]
    assert 'git log --format=%B HEAD > "$RUNNER_TEMP/messages.txt"' in e["run"]
    assert 'confidentialite.py --exiger-prives --texte "$RUNNER_TEMP/messages.txt"' in e["run"]


def etape_texte_pr(rendu, nom):
    etapes = charger(rendu, TEXTE_PR)["jobs"]["texte-pr"]["steps"]
    (trouvee,) = [e for e in etapes if e.get("name") == nom]
    return trouvee


def test_texte_de_pr_dans_runner_temp(rendre):
    e = etape_texte_pr(rendre(), "Confidentialité et format du titre et du corps de la PR")
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


def _signaux(original, matcher="startup|resume", commande=None, retirer=False):
    doc = json.loads(original)
    (groupe,) = doc["hooks"]["SessionStart"]
    if retirer:
        del doc["hooks"]["SessionStart"]
    else:
        if matcher is None:
            groupe.pop("matcher", None)
        else:
            groupe["matcher"] = matcher
        if commande is not None:
            groupe["hooks"][0]["command"] = commande
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
        (
            "sans garde",
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [],
                        "SessionStart": json.loads(original)["hooks"]["SessionStart"],
                    }
                }
            ),
            1,
        ),
        ("sans signaux", _signaux(original, retirer=True), 1),
        ("signaux sans resume", _signaux(original, "startup"), 1),
        ("signaux universels", _signaux(original, "*"), 0),
        ("signaux sans matcher", _signaux(original, None), 0),
        ("signaux sans script", _signaux(original, commande="sh lancer.sh garde_claude.py"), 1),
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
    checkout, gitleaks, *_ = job["steps"]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}
    etapes_socle = charger(rendu, SOCLE)["jobs"]["secrets"]["steps"]
    (gitleaks_socle,) = [e for e in etapes_socle if "gitleaks" in e.get("uses", "")]
    assert gitleaks["uses"] == gitleaks_socle["uses"]
    assert gitleaks["env"] == gitleaks_socle["env"]
    assert "${{ secrets.GITHUB_TOKEN }}" in (rendu / HISTORIQUE).read_text(encoding="utf-8")


def test_historique_lance_la_porte(rendre):
    """Après gitleaks, la porte relit l'historique ; Python est posé comme dans le socle."""
    rendu = rendre()
    etapes = charger(rendu, HISTORIQUE)["jobs"]["historique"]["steps"]
    noms = [e.get("name") for e in etapes]
    (rang,) = [i for i, n in enumerate(noms) if n == "Confidentialité de l'historique"]
    (python_socle,) = [
        e
        for e in charger(rendu, SOCLE)["jobs"]["confidentialite"]["steps"]
        if e.get("uses", "").startswith("actions/setup-python@")
    ]
    assert etapes[rang - 1] == python_socle
    porte = etapes[rang]
    assert porte["run"] == (
        "python scripts/modele/confidentialite.py --exiger-prives --historique "
        "--acceptes .github/constats-acceptes.txt"
    )
    assert porte["env"] == {"MOTIFS_INTERDITS": "${{ secrets.MOTIFS_INTERDITS }}"}
    # la visibilité et la branche par défaut viennent de l'API, avant la porte, jamais de
    # github.event.repository (absent d'un déclenchement planifié)
    (lecture,) = [e for e in etapes[:rang] if e.get("name") == "Visibilité du dépôt"]
    assert lecture["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "set -euo pipefail" in lecture["run"]
    assert "gh api" in lecture["run"]
    assert "DEPOT_PRIVE=" in lecture["run"] and "BRANCHE_DEFAUT=" in lecture["run"]
    assert '>> "$GITHUB_ENV"' in lecture["run"]
    assert "github.event.repository" not in (rendu / HISTORIQUE).read_text(encoding="utf-8")


def test_historique_hors_contextes_requis(rendre):
    rendu = rendre()
    ruleset = json.loads((rendu / ".github/modele/ruleset-main.json").read_text(encoding="utf-8"))
    regles = {r["type"]: r for r in ruleset["rules"]}
    contextes = {
        c["context"]
        for c in regles["required_status_checks"]["parameters"]["required_status_checks"]
    }
    assert contextes == {"socle / secrets", "socle / confidentialite", "texte-pr"}


def test_la_porte_recoit_la_visibilite_et_la_branche_par_defaut(rendre):
    """En CI, la visibilité réelle l'emporte, et la nature se lit sur la branche par défaut : dans
    le socle, pour le diff et les messages de commit ; dans `texte-pr`, pour le texte de la PR."""
    rendu = rendre()
    etapes = charger(rendu, SOCLE)["jobs"]["confidentialite"]["steps"]
    portes = [e for e in etapes if "confidentialite.py" in e.get("run", "")]
    assert [e["name"] for e in portes] == [
        "Confidentialité du diff",
        "Confidentialité des messages de commit",
    ]
    etapes_texte = charger(rendu, TEXTE_PR)["jobs"]["texte-pr"]["steps"]
    portes_texte = [e for e in etapes_texte if "confidentialite.py" in e.get("run", "")]
    assert [e["name"] for e in portes_texte] == [
        "Confidentialité et format du titre et du corps de la PR"
    ]
    for e in portes + portes_texte:
        assert e["env"]["DEPOT_PRIVE"] == "${{ github.event.repository.private }}", e["name"]
        branche = e["env"]["BRANCHE_DEFAUT"]
        assert branche == "${{ github.event.repository.default_branch }}", e["name"]


def test_etape_de_la_documentation(rendre):
    """La licence et la carte de la racine : la dernière étape du job `confidentialite`, pour qu'un
    refus n'arrête pas le contrôle du garde, avec la visibilité et la branche par défaut que lit la
    nature. Le job garde son seul `setup-python`. L'étape entière : un `continue-on-error` ou un
    `if:` ferait taire le refus."""
    etapes = charger(rendre(), SOCLE)["jobs"]["confidentialite"]["steps"]
    assert etapes[-1] == {
        "name": "La documentation de la racine (licence, carte)",
        "env": {
            "DEPOT_PRIVE": "${{ github.event.repository.private }}",
            "BRANCHE_DEFAUT": "${{ github.event.repository.default_branch }}",
        },
        "run": "python scripts/modele/documentation.py",
    }
    assert sum("setup-python" in e.get("uses", "") for e in etapes) == 1


ETAPE_DES_PLANS = "Les plans (.claude/plans)"
# Un plan conforme : il cite la ligne 2 de `src/a.py`, et chacune de ses tâches a une case.
PLAN_CONFORME = plan(meca="- `src/a.py:2` — `def f(` — la fonction existe déjà.")
RESUME_CONFORME = "1 mécanismes vérifiés, 0 non vérifiés, 0 outils, 1 revues"


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_etape_des_plans(rendre, env_isole, tmp_path):
    """Les plans d'une PR : l'étape précède la dernière, « La documentation de la racine », sans
    second `setup-python` ni échappatoire. Le runner la lance par `bash -e`, le socle ne déclarant
    pas de shell ; le test la lance par `sh -e` (`dash` sous Ubuntu), plus strict. Elle vérifie en
    entier chaque plan que la PR ajoute, et sans ouvrir ses lieux chaque plan qu'elle modifie,
    dont les numéros de ligne dérivent avec le code. Une base nulle ne contrôle
    rien ; une base inconnue arrête l'étape, au lieu de passer sur une liste vide. `-z` garde un
    nom non ASCII tel quel, la pathspec descend dans un sous-dossier, et chaque plan est lu, même
    après un refus, la liste des plans modifiés comprise. Un plan renommé compte pour ajouté
    (`--no-renames`)."""
    rendu = rendre()
    job = charger(rendu, SOCLE)["jobs"]["confidentialite"]
    noms = [e.get("name") for e in job["steps"]]
    assert noms[-2:] == [ETAPE_DES_PLANS, "La documentation de la racine (licence, carte)"]
    assert sum("setup-python" in e.get("uses", "") for e in job["steps"]) == 1
    sans_echappatoire(job, ETAPE_DES_PLANS)
    run = etape(rendu, ETAPE_DES_PLANS)["run"]
    env = env_isole()
    git(rendu, env, "init", "-q", "-b", "main")
    git(rendu, env, "config", "core.autocrlf", "false")
    (rendu / "src").mkdir()
    (rendu / "src/a.py").write_bytes(A_PY.encode("utf-8"))
    git(rendu, env, "add", "-A")
    git(rendu, env, "commit", "-q", "-m", "feat: base")
    base = git(rendu, env, "rev-parse", "HEAD").strip()
    temp = tmp_path / "runner-temp"
    temp.mkdir()
    env.update(
        RUNNER_TEMP=str(temp),
        PATH=str(Path(sys.executable).parent) + os.pathsep + env["PATH"],
    )

    def commit(depuis, fichiers):
        """Un commit sur `depuis` qui écrit `fichiers` ({chemin : texte}) ; il rend son SHA."""
        git(rendu, env, "checkout", "-q", "--detach", depuis)
        for chemin, texte in fichiers.items():
            (rendu / chemin).parent.mkdir(parents=True, exist_ok=True)
            (rendu / chemin).write_bytes(texte.encode("utf-8"))
        git(rendu, env, "add", "-A")
        git(rendu, env, "commit", "-q", "--allow-empty", "-m", "feat: essai")
        return git(rendu, env, "rev-parse", "HEAD").strip()

    def lancer(base):
        r = subprocess.run(
            [SH, "-e", "-c", run],
            check=False,
            cwd=rendu,
            env={**env, "BASE": base},
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return r.returncode, r.stdout + r.stderr

    commit(base, {".claude/plans/a.md": "# Un plan sans ses sections\n"})
    code, sortie = lancer(base)
    assert code != 0, sortie
    assert "plan : .claude/plans/a.md : section « Mécanismes annoncés » absente" in sortie, sortie
    commit(base, {"src/b.py": "x = 1\n"})
    assert lancer(base)[0] == 0
    code, sortie = lancer("0" * 40)
    assert code == 0, sortie
    assert "Base nulle : plans non contrôlés." in sortie, sortie
    code, sortie = lancer("1234abcd" * 5)  # une base absente du dépôt
    assert code != 0, sortie
    commit(base, {".claude/plans/réécriture.md": PLAN_CONFORME})
    code, sortie = lancer(base)
    assert code == 0, sortie
    assert f"plan : .claude/plans/réécriture.md : {RESUME_CONFORME}" in sortie, sortie
    commit(base, {".claude/plans/x/b.md": PLAN_CONFORME})
    code, sortie = lancer(base)
    assert code == 0, sortie
    assert f"plan : .claude/plans/x/b.md : {RESUME_CONFORME}" in sortie, sortie
    commit(base, {".claude/plans/a.md": "# Un plan\n", ".claude/plans/b.md": PLAN_CONFORME})
    code, sortie = lancer(base)
    assert code != 0, sortie
    assert f"plan : .claude/plans/b.md : {RESUME_CONFORME}" in sortie, sortie
    # La liste des plans modifiés passe même après le refus d'un plan ajouté : `a.md` ajouté et
    # refusé, `b.md`, présent dans la base, modifié et conforme.
    avec_b = commit(base, {".claude/plans/b.md": PLAN_CONFORME})
    commit(
        avec_b,
        {
            ".claude/plans/a.md": "# Un plan\n",
            ".claude/plans/b.md": PLAN_CONFORME.replace("- [ ]", "- [x]", 1),
        },
    )
    code, sortie = lancer(avec_b)
    assert code != 0, sortie
    assert "plan : .claude/plans/a.md : section « Mécanismes annoncés » absente" in sortie, sortie
    assert "plan : .claude/plans/b.md : 1 mécanismes, lieux non ouverts" in sortie, sortie
    # Une PR d'implémentation modifie son plan avec le code qu'il cite : deux lignes en tête du
    # fichier, une case cochée. Le plan modifié passe ; ajouté par ce même commit, il refuse.
    avec_le_plan = commit(base, {".claude/plans/p.md": PLAN_CONFORME})
    derive = {
        "src/a.py": "# un\n# deux\n" + A_PY,
        ".claude/plans/p.md": PLAN_CONFORME.replace("- [ ]", "- [x]", 1),
    }
    commit(avec_le_plan, derive)
    code, sortie = lancer(avec_le_plan)
    assert code == 0, sortie
    assert "plan : .claude/plans/p.md : 1 mécanismes, lieux non ouverts" in sortie, sortie
    commit(base, derive)
    code, sortie = lancer(base)
    assert code != 0, sortie
    assert "extrait absent de src/a.py:2" in sortie, sortie
    # Un plan renommé, puis rendu non conforme (un lieu faux), est un plan ajouté : sans
    # `--no-renames`, git le dirait renommé, ni ajouté ni modifié, et aucune liste ne le lirait.
    git(rendu, env, "checkout", "-q", "--detach", avec_le_plan)
    git(rendu, env, "mv", ".claude/plans/p.md", ".claude/plans/q.md")
    faux = PLAN_CONFORME.replace("`src/a.py:2`", "`src/a.py:3`", 1)
    assert faux != PLAN_CONFORME
    (rendu / ".claude/plans/q.md").write_bytes(faux.encode("utf-8"))
    git(rendu, env, "add", ".claude/plans/q.md")
    git(rendu, env, "commit", "-q", "-m", "feat: le plan renommé")
    renommes = git(
        rendu, env, "diff", "--name-status", "--diff-filter=R", f"{avec_le_plan}...HEAD"
    )
    assert renommes.startswith("R") and ".claude/plans/q.md" in renommes, renommes
    code, sortie = lancer(avec_le_plan)
    assert code != 0, sortie
    attendu = "plan : .claude/plans/q.md : Mécanismes annoncés, ligne 2 : extrait absent de "
    assert attendu + "src/a.py:3" in sortie, sortie


def test_texte_pr_yml(rendre):
    """Le workflow du texte de la PR, seul à écouter `edited` (AM-2) : la confidentialité et le
    format du titre et du corps, déplacés du socle, puis les écarts à la spec et la tête relue
    (`texte_pr.py`), qui lit le corps dans son environnement, jamais dans ses arguments."""
    gabarit = RACINE / "template" / TEXTE_PR
    # il porte des expressions de GitHub : il n'est pas un gabarit Jinja, et il est rendu tel quel
    assert not gabarit.name.endswith(".jinja")
    texte_gabarit = gabarit.read_text(encoding="utf-8")
    assert "${{" in texte_gabarit
    assert "{%" not in texte_gabarit and "{#" not in texte_gabarit
    rendu = rendre()
    texte = (rendu / TEXTE_PR).read_text(encoding="utf-8")
    assert texte == texte_gabarit
    assert texte.splitlines()[0] == (
        "# Géré par le modèle — ne pas modifier ici (docs/modele/methode.md)."
    )
    # le `ci.yml` d'un projet déjà né, semé, écoute encore `edited` jusqu'à ce qu'il le retire ;
    # le workflow lui-même est géré : « ce fichier est semé » se lisait comme s'il parlait de lui
    entete = " ".join(ligne[1:].strip() for ligne in texte.splitlines() if ligne.startswith("#"))
    assert (
        "Le `ci.yml` d'un projet est semé : à sa mise à jour, un projet déjà né en retire `edited` "
        "lui-même"
    ) in entete
    assert "ce fichier est semé" not in entete.lower()

    # chaque action épinglée par SHA, celui du socle
    socle = dict(
        re.findall(r"uses:\s*([^@\s]+)@([0-9a-f]{40})", (rendu / SOCLE).read_text("utf-8"))
    )
    actions = re.findall(r"^\s*(?:-\s*)?uses:\s*(\S+)", texte, re.MULTILINE)
    assert actions
    for uses in actions:
        action, _, sha = uses.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", sha), uses
        assert socle.get(action) == sha, uses

    doc = yaml.safe_load(texte)
    assert declencheurs(doc) == {
        "pull_request": {"types": ["opened", "edited", "synchronize", "reopened"]}
    }
    assert doc["concurrency"] == {"group": "texte-pr-${{ github.ref }}", "cancel-in-progress": True}
    assert doc["permissions"] == {"contents": "read", "pull-requests": "read", "issues": "read"}
    assert list(doc["jobs"]) == ["texte-pr"]
    job = doc["jobs"]["texte-pr"]
    assert job["name"] == "texte-pr"
    (checkout,) = [e for e in job["steps"] if e.get("uses", "").startswith("actions/checkout@")]
    assert checkout["with"]["fetch-depth"] == 0  # la nature se lit sur la branche par défaut

    # aucune échappatoire : un job sauté ou une étape tolérée compteraient « succès »
    sans_echappatoire(job, *ETAPES_TEXTE_PR)
    noms = [e.get("name") for e in job["steps"]]
    assert [n for n in noms if n in ETAPES_TEXTE_PR] == list(ETAPES_TEXTE_PR)

    deplacee = etape_texte_pr(rendu, "Confidentialité et format du titre et du corps de la PR")
    assert 'python scripts/modele/commits.py --titre "$TITRE"' in deplacee["run"].splitlines()
    api = etape_texte_pr(rendu, "Les issues que la PR ferme (API)")
    assert api["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "DEPOT": "${{ github.repository }}",
        "NUMERO": "${{ github.event.pull_request.number }}",
    }
    # la réponse de l'API, écrite dans le fichier que lit l'étape du script, plus bas
    ecrits = re.findall(r'> ("\$RUNNER_TEMP/[^"]*")', api["run"])
    assert ecrits == ['"$RUNNER_TEMP/fermetures.json"'], ecrits
    for fragment in (
        "closingIssuesReferences",
        "totalCount",
        "-f owner=",  # -F changerait en booléen ou en nombre un dépôt nommé `true` ou `null`
        "-f name=",
        "-F n=",
        "|| true",  # le code de gh mis de côté : c'est texte_pr.py qui juge la réponse
    ):
        assert fragment in api["run"], fragment
    script = etape_texte_pr(rendu, "Les écarts à la spec et la tête relue")
    assert script["env"] == {
        "CORPS": "${{ github.event.pull_request.body }}",
        "AUTEUR": "${{ github.event.pull_request.user.login }}",
        "TETE": "${{ github.event.pull_request.head.sha }}",
    }
    assert script["run"] == (
        'python scripts/modele/texte_pr.py --fermetures "$RUNNER_TEMP/fermetures.json"'
    )
    assert script["run"].endswith(" --fermetures " + ecrits[0])  # le fichier que l'API a écrit
    for e in job["steps"]:
        for ligne in e.get("run", "").splitlines():
            if "texte_pr.py" in ligne:
                assert "CORPS" not in ligne, ligne


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
