"""Le relevé des projets nés du modèle, `poste/releve.py` : contre un faux `gh`
(`tests/faux_gh_api.py`) et un dépôt git de banc qui porte deux étiquettes.

Le banc et le faux se fabriquent une fois par module, et chaque scénario ne lance le relevé qu'une
fois : plusieurs tests lisent la même sortie. `v0.2.0`, la tête du banc, porte les scripts du
modèle tels qu'ils sont ; `v0.1.0` en porte des versions retouchées, pour que les verdicts
changent entre les deux.
"""

import base64
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from conftest import RACINE, SCRIPTS

sys.path.insert(0, str(RACINE / "poste"))
import releve

COMPTE = "compte-essai"
# Un texte unique, porté par les plans et les corps du banc : la sortie ne le cite jamais.
MARQUEUR = "Zorglub-7f3a9c"
# Une branche par défaut qui porte le marqueur : le relevé ne l'affiche jamais.
BRANCHE = f"principale-{MARQUEUR}"
FAUX = Path(__file__).resolve().parent / "faux_gh_api.py"
REGLE = "template/.github/{% if cible != 'donnees' %}modele{% endif %}/ruleset-main.json"
X_RENDU = (
    "template/.github/workflows/"
    "{% if cible == 'serveur' and nature == 'code' %}modele-x.yml{% endif %}"
)
CONSIGNER = "template/.claude/skills/{% if cible != 'donnees' %}consigner{% endif %}/SKILL.md"
INTERDITS = set('&|<>^%"\n\r')
LIMITES = (
    "relevé : fichiers gérés : seuls les dossiers exclus des formateurs (methode.md) sont "
    "comparés, pas le gabarit de PR ni les autres fichiers gérés hors d'eux"
)
CONTEXTES = [
    c["context"]
    for r in json.loads((RACINE / REGLE).read_text(encoding="utf-8"))["rules"]
    if r["type"] == "required_status_checks"
    for c in r["parameters"]["required_status_checks"]
]

COPIER_DU_BANC = (
    "_subdirectory: template\n"
    "_skip_if_exists:\n"
    "  - CLAUDE.md\n"
    '  - "docs/modele/seme.md"\n'
    "  # un commentaire dans la liste\n"
    "  - '.github/workflows/ci.yml'\n"
    "nom:\n"
    "  type: str\n"
)


def _plan(outils: str = "Aucun.") -> str:
    """Un plan en cours, sans « Effets cherchés » ni clôture : il passe par `--sans-lieux`, et
    refuserait s'il était neuf."""
    return (
        f"# Plan d'essai {MARQUEUR}\n\n"
        "## Mécanismes annoncés\n\nAucun.\n\n"
        f"## Outils et cas limites\n\n{outils}\n\n"
        "## Revues\n\n- La revue de la tâche : Tâche 1\n\n"
        f"### Tâche 1 : le travail {MARQUEUR}\n\nRien.\n"
    )


PLAN_EN_COURS = _plan()
PLAN_MAL_FORME = _plan(outils=f"- un outil sans séparateur {MARQUEUR}")
CORPS_AUCUN = f"Partie de #1, {MARQUEUR}.\n\n## Écarts à la spec\n\nAucun.\n"
CORPS_ACCORD = (
    f"## Écarts à la spec\n\n- un écart {MARQUEUR} — promesse : § 1 — accord : 13/11/2026\n"
)


def _remplacer(octets: bytes, ancien: str, nouveau: str) -> bytes:
    texte = octets.decode("utf-8")
    assert ancien in texte, ancien
    return texte.replace(ancien, nouveau, 1).encode("utf-8")


def _git(cwd, *args, env=None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, check=False)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return r.stdout.decode("utf-8")


def _ecrire(racine: Path, fichiers: dict) -> None:
    for chemin, contenu in fichiers.items():
        f = racine / chemin
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(contenu.encode("utf-8") if isinstance(contenu, str) else contenu)


def _blobs(racine: Path, version: str) -> dict:
    sortie = _git(racine, "ls-tree", "-r", "-z", "--full-tree", version)
    blobs = {}
    for entree in filter(None, sortie.split("\0")):
        meta, chemin = entree.split("\t", 1)
        blobs[chemin] = meta.split()[2]
    return blobs


def _env_git(home: Path) -> dict:
    """L'environnement des commits du banc : un dossier personnel vide, une identité d'essai."""
    home.mkdir(parents=True, exist_ok=True)
    return dict(
        os.environ,
        HOME=str(home),
        USERPROFILE=str(home),
        GIT_AUTHOR_NAME="Essai",
        GIT_AUTHOR_EMAIL="essai@example.com",
        GIT_COMMITTER_NAME="Essai",
        GIT_COMMITTER_EMAIL="essai@example.com",
    )


def _depot_minimal(racine: Path, fichiers: dict, env: dict) -> None:
    """Un dépôt git d'un seul commit, qui porte `fichiers`."""
    racine.mkdir()
    _git(racine, "init", "-q", "-b", "main", env=env)
    _git(racine, "config", "core.autocrlf", "false", env=env)
    _ecrire(racine, fichiers)
    _git(racine, "add", "--", *fichiers, env=env)
    _git(racine, "commit", "-q", "-m", "minimal", env=env)


@pytest.fixture(scope="module")
def banc(tmp_path_factory):
    """Le dépôt git du banc : `copier.yml`, les scripts du modèle, un fichier sous chacun des six
    chemins gérés, un semé sous l'un d'eux, `.claude/settings.json`, un fichier rendu. Trois
    étiquettes : `v0.0.9`, dont les scripts plantent ; `v0.1.0` ; `v0.2.0`, la tête."""
    racine = tmp_path_factory.mktemp("banc")
    env = _env_git(tmp_path_factory.mktemp("home-vide"))
    _git(racine, "init", "-q", "-b", "main", env=env)
    _git(racine, "config", "core.autocrlf", "false", env=env)
    # une version dont `plan.py` plante (code 1, sans la ligne de refus) et dont `texte_pr.py`
    # sort par un code hors de {0, 1}
    _ecrire(
        racine,
        {
            "copier.yml": COPIER_DU_BANC,
            "template/scripts/modele/plan.py": 'raise RuntimeError("boum")\n',
            "template/scripts/modele/texte_pr.py": "import sys\n\nsys.exit(3)\n",
        },
    )
    _git(racine, "add", "--", "copier.yml", "template", env=env)
    _git(racine, "commit", "-q", "-m", "v0.0.9", env=env)
    _git(racine, "tag", "v0.0.9", env=env)
    scripts = {
        f"template/scripts/modele/{f.name}": f.read_bytes()
        for f in SCRIPTS.iterdir()
        if f.is_file()
    }
    plan_v1 = _remplacer(
        scripts["template/scripts/modele/plan.py"],
        'OUTILS: "forme attendue',
        'OUTILS: "forme ancienne',
    )
    # le résumé d'avant le compte des effets : le relevé ne le compare pas
    plan_v1 = _remplacer(plan_v1, "{comptes[EFFETS]} effets, ", "")
    texte_pr_v1 = _remplacer(
        scripts["template/scripts/modele/texte_pr.py"],
        "r\"accord(?: d'edouard)?[ \\t]*:",
        "r\"accord d'edouard[ \\t]*:",
    )
    # une version qui ne lit pas encore les fermetures
    texte_pr_v1 = _remplacer(texte_pr_v1, "total = _fermees(fermetures)", "total = 0")
    regle_v1 = json.dumps(
        {
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {"required_status_checks": [{"context": "socle / secrets"}]},
                }
            ]
        }
    )
    v1 = {
        **scripts,
        "copier.yml": COPIER_DU_BANC,
        "template/scripts/modele/plan.py": plan_v1,
        "template/scripts/modele/texte_pr.py": texte_pr_v1,
        "template/scripts/modele/reglages.py.jinja": (
            scripts["template/scripts/modele/reglages.py.jinja"] + b"# ancienne\n"
        ),
        "template/.githooks/pre-commit": "v1\n",
        "template/docs/modele/methode.md": "méthode v1\n",
        "template/docs/modele/seme.md": "semé v1\n",
        REGLE: regle_v1,
        "template/.github/workflows/modele-socle.yml": "socle v1\n",
        X_RENDU: "x v1\n",
        CONSIGNER: "consigner\n",
        "template/.claude/settings.json": "{}\n",
        "template/README.md.jinja": "readme v1\n",
    }
    _ecrire(racine, v1)
    _git(racine, "add", "--", "copier.yml", "template", env=env)
    _git(racine, "commit", "-q", "-m", "v0.1.0", env=env)
    _git(racine, "tag", "v0.1.0", env=env)
    v2 = {
        **scripts,
        "template/.githooks/pre-commit": "v2\n",
        "template/docs/modele/methode.md": "méthode v2\n",
        "template/docs/modele/seme.md": "semé v2\n",
        "template/docs/modele/nouveau.md": "nouveau\n",
        REGLE: (RACINE / REGLE).read_bytes(),
        "template/.github/workflows/modele-socle.yml": "socle v2\n",
        X_RENDU: "x v2\n",
        "template/.claude/settings.json": '{"a": 1}\n',
        "template/README.md.jinja": "readme v2\n",
    }
    _ecrire(racine, v2)
    _git(racine, "add", "--", "template", env=env)
    _git(racine, "commit", "-q", "-m", "v0.2.0", env=env)
    _git(racine, "tag", "v0.2.0", env=env)
    return SimpleNamespace(racine=racine, v1=_blobs(racine, "v0.1.0"), v2=_blobs(racine, "v0.2.0"))


@pytest.fixture(scope="module")
def faux(tmp_path_factory):
    """Le faux `gh` : un `.cmd` sous Windows, un script `sh` exécutable ailleurs. Python s'y lance
    par `-I -S` : le faux n'a besoin ni de `site` ni des variables `PYTHON*`, et chaque appel
    démarre plus vite, ce que la durée du fichier demande."""
    dossier = tmp_path_factory.mktemp("faux")
    if sys.platform == "win32":
        f = dossier / "gh.cmd"
        f.write_text(f'@"{sys.executable}" -I -S "{FAUX}" %*\r\n', encoding="utf-8")
    else:
        f = dossier / "gh"
        f.write_text(f'#!/bin/sh\nexec "{sys.executable}" -I -S "{FAUX}" "$@"\n', encoding="utf-8")
        f.chmod(0o755)
    return f


# --- les réponses du faux ----------------------------------------------------------------------


def cle(point: str, **parametres) -> str:
    if not parametres:
        return point
    return point + "?" + "&".join(sorted(f"{k}={v}" for k, v in parametres.items()))


def ok(sortie) -> dict:
    return {"code": 0, "sortie": sortie}


def erreur(status: int) -> dict:
    """Une erreur de `gh api` : le JSON sur la sortie standard, le texte sur la sortie
    d'erreur, l'un et l'autre porteurs du marqueur, que la sortie ne cite pas."""
    return {
        "code": 1,
        "sortie": {"message": f"Erreur {MARQUEUR}", "status": str(status)},
        "erreur": f"gh: Erreur {MARQUEUR} (HTTP {status})\n",
    }


def b64(octets: bytes, largeur: int = 60) -> str:
    """Le base64 que rend l'API, coupé de fins de ligne."""
    texte = base64.b64encode(octets).decode("ascii")
    return "\n".join(texte[i : i + largeur] for i in range(0, len(texte), largeur)) + "\n"


def depot(nom: str, prive: bool = False, archive: bool = False, branche: str = "main") -> dict:
    return {
        "name": nom,
        "private": prive,
        "archived": archive,
        "default_branch": branche,
        "owner": {"login": COMPTE},
    }


def copier_answers(
    commit: str,
    cible: str = "aucune",
    nature: str | None = "code",
    fusion: str = "session",
    src: str = "gh:EdouardZemb/modele-projet",
) -> str:
    lignes = [
        "# Écrit par Copier. Ne pas modifier à la main.",
        f"_commit: {commit}",
        f"_src_path: {src}",
        "branche_principale: main",
        f"cible: {cible}",
        "compte: EdouardZemb",
        "description: Un projet d'essai",
        f"fusion: {fusion}",
        "nom: essai",
    ]
    if nature is not None:
        lignes.append(f"nature: {nature}")
    return "\n".join(lignes) + "\n"


def contenu(texte: str) -> dict:
    return ok({"content": b64(texte.encode("utf-8")), "encoding": "base64"})


def api(nom: str, suite: str = "", **parametres) -> str:
    return cle(f"repos/{COMPTE}/{nom}{suite}", **parametres)


def reponses_de_base(nom: str, answers: str) -> dict:
    return {api(nom, "/contents/.copier-answers.yml", ref="main"): contenu(answers)}


def arbre(entrees: dict, tronque: bool = False) -> dict:
    """L'arbre d'un projet, `{chemin: sha}` ; un sha `None` est un dossier."""
    return ok(
        {
            "sha": "e" * 40,
            "tree": [
                {"path": p, "type": "tree" if s is None else "blob", "sha": s or "d" * 40}
                for p, s in entrees.items()
            ],
            "truncated": tronque,
        }
    )


def projet_clair(nom: str, prive: bool = False) -> dict:
    """Un projet à la version de la tête, qui n'a rien à lire : un plan en cours, aucune PR, une
    règle aux contrôles gérés et à un contrôle propre."""
    return {
        **reponses_de_base(nom, copier_answers("v0.2.0")),
        api(nom, "/git/trees/main", recursive="1"): arbre(
            {".claude/plans": None, ".claude/plans/plan-a.md": "a" * 40}
        ),
        api(nom, "/git/blobs/" + "a" * 40): contenu(PLAN_EN_COURS),
        api(nom, "/pulls", state="open", per_page="100"): ok([[]]),
        api(nom, "/pulls", state="all", per_page="50"): ok([]),
        api(nom, "/rules/branches/main"): ok(
            [
                {"type": "deletion"},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [
                            {"context": c} for c in [*CONTEXTES, "tests (propre)"]
                        ]
                    },
                },
            ]
        ),
    }


def pr(numero: int, corps: str, auteur: str = "auteur-essai") -> dict:
    return {
        "number": numero,
        "body": corps,
        "user": {"login": auteur},
        "title": f"Une PR {MARQUEUR}",
        "head": {"sha": f"{numero:x}" * 40, "ref": f"lot/{MARQUEUR}"},
    }


def fermetures(numero: int, total: int = 0) -> dict:
    return {
        "number": numero,
        "closingIssuesReferences": {
            "totalCount": total,
            "nodes": [{"number": 1}] if total else [],
        },
    }


def regle(*contextes: str) -> list:
    """Une règle de branche dont les contrôles requis sont `contextes`."""
    return [
        {"type": "deletion"},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": c} for c in contextes]},
        },
    ]


def projet(
    nom: str,
    version: str = "v0.2.0",
    entrees: dict | None = None,
    blobs: dict | None = None,
    ouvertes: dict | None = None,
    prs: dict | None = None,
    regles: list | None = None,
) -> dict:
    """Les réponses d'un projet sur `main` : son arbre, ses blobs, ses PR ouvertes et leurs
    fichiers, ses dernières PR et leurs fermetures (aucune), sa règle (aucune par défaut)."""
    ouvertes = ouvertes or {}
    prs = prs or {}
    reponses = {
        **reponses_de_base(nom, copier_answers(version)),
        api(nom, "/git/trees/main", recursive="1"): arbre(entrees or {}),
        api(nom, "/pulls", state="open", per_page="100"): ok([[{"number": n} for n in ouvertes]]),
        api(nom, "/pulls", state="all", per_page="50"): ok([pr(n, c) for n, c in prs.items()]),
        api(nom, "/rules/branches/main"): ok(regles or []),
    }
    for sha, texte in (blobs or {}).items():
        reponses[api(nom, "/git/blobs/" + sha)] = contenu(texte)
    for n, fichiers in ouvertes.items():
        reponses[api(nom, f"/pulls/{n}/files", per_page="100")] = ok([fichiers])
    if prs:
        reponses[cle("graphql", query=releve.REQUETE, owner=COMPTE, name=nom, n="50")] = ok(
            {"data": {"repository": {"pullRequests": {"nodes": [fermetures(n) for n in prs]}}}}
        )
    return reponses


def reponses_completes(banc) -> dict:
    """Six dépôts sur deux pages : `alpha`, public, en `v0.1.0` ; `beta`, privé, à la tête ;
    `gamma`, archivé ; `delta`, sans `.copier-answers.yml` ; `epsilon`, d'un autre modèle ;
    `zeta-donnees`, privé, en cible `donnees`, sans `nature`."""
    page1 = [
        depot("alpha"),
        depot("beta", prive=True, branche=BRANCHE),
        depot("gamma", archive=True),
    ]
    page2 = [depot("delta"), depot("epsilon"), depot("zeta-donnees", prive=True)]
    v1 = banc.v1
    zeta = (
        "# Écrit par Copier. Ne pas modifier à la main.\n"
        "_commit: v0.1.0\n"
        "_src_path: gh:EdouardZemb/modele-projet\n"
        "cible: donnees\n"
        "cible_code: serveur\n"
        "description: 'Le dépôt d''essai, dont la description\n"
        "  court sur deux lignes'\n"
        "fusion: session\n"
    )
    beta = (
        "# Écrit par Copier.\n"
        "_commit: v0.2.0\n"
        '_src_path: "gh:EdouardZemb/modele-projet"\n'
        "cible: aucune\n"
        "nature: donnees\n"
        'fusion: "edouard"\n'
    )
    fichiers_de_7 = [{"filename": f"src/f{i}.py", "status": "modified"} for i in range(30)]
    return {
        cle("user/repos", affiliation="owner", per_page="100"): ok([page1, page2]),
        # alpha
        **reponses_de_base("alpha", copier_answers("v0.1.0")),
        api("alpha", "/git/trees/main", recursive="1"): arbre(
            {
                "README.md": "5" * 40,
                ".githooks/pre-commit": "1" * 40,
                "docs/modele/methode.md": v1["template/docs/modele/methode.md"],
                "docs/modele/seme.md": "2" * 40,
                ".github/modele/ruleset-main.json": v1[REGLE],
                ".claude/settings.json": "3" * 40,
                "scripts/modele/plan.py": v1["template/scripts/modele/plan.py"],
                "scripts/modele/texte_pr.py": v1["template/scripts/modele/texte_pr.py"],
                "scripts/modele/reglages.py": "4" * 40,
                ".claude/plans": None,
                ".claude/plans/sous": None,
                ".claude/plans/plan-b.md": "b" * 40,
                ".claude/plans/sous/plan-a.md": "a" * 40,
                ".claude/plans/notes.txt": "c" * 40,
            }
        ),
        api("alpha", "/git/blobs/" + "a" * 40): contenu(PLAN_EN_COURS),
        api("alpha", "/git/blobs/" + "b" * 40): contenu(PLAN_MAL_FORME),
        api("alpha", "/pulls", state="open", per_page="100"): ok(
            [[{"number": 7}, {"number": 8}, {"number": 9}]]
        ),
        api("alpha", "/pulls/7/files", per_page="100"): ok(
            [fichiers_de_7, [{"filename": ".claude/plans/neuf.md", "status": "added"}]]
        ),
        api("alpha", "/pulls/8/files", per_page="100"): ok(
            [
                [
                    {
                        "filename": ".claude/plans/renomme.md",
                        "status": "renamed",
                        "previous_filename": ".claude/plans/ancien.md",
                    }
                ]
            ]
        ),
        api("alpha", "/pulls/9/files", per_page="100"): ok(
            [[{"filename": ".claude/plans/plan-b.md", "status": "modified"}]]
        ),
        api("alpha", "/pulls", state="all", per_page="50"): ok(
            [
                pr(6, CORPS_AUCUN),
                pr(5, CORPS_ACCORD),
                pr(4, CORPS_ACCORD, auteur="dependabot[bot]"),
                pr(3, CORPS_AUCUN),
                pr(2, CORPS_AUCUN),
            ]
        ),
        cle("graphql", query=releve.REQUETE, owner=COMPTE, name="alpha", n="50"): ok(
            {
                "data": {
                    "repository": {
                        "pullRequests": {
                            "nodes": [
                                fermetures(2),
                                fermetures(4),
                                fermetures(5),
                                fermetures(6, total=1),
                            ]
                        }
                    }
                }
            }
        ),
        api("alpha", "/rules/branches/main"): ok(
            [
                {"type": "deletion"},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [
                            {"context": "socle / secrets"},
                            {"context": "socle / confidentialite"},
                            {"context": "tests (propre)"},
                        ]
                    },
                },
            ]
        ),
        # beta
        api("beta", "/contents/.copier-answers.yml", ref=BRANCHE): contenu(beta),
        api("beta", f"/git/trees/{BRANCHE}", recursive="1"): arbre({"README.md": "5" * 40}),
        api("beta", "/pulls", state="open", per_page="100"): ok([[]]),
        api("beta", "/pulls", state="all", per_page="50"): ok([]),
        api("beta", f"/rules/branches/{BRANCHE}"): ok([]),
        # delta, epsilon
        api("delta", "/contents/.copier-answers.yml", ref="main"): erreur(404),
        **reponses_de_base("epsilon", copier_answers("v0.1.0", src="gh:quelquun/autre-modele")),
        # zeta-donnees
        **reponses_de_base("zeta-donnees", zeta),
        api("zeta-donnees", "/git/trees/main", recursive="1"): arbre(
            {
                ".githooks/pre-commit": v1["template/.githooks/pre-commit"],
                "docs/modele/methode.md": v1["template/docs/modele/methode.md"],
                ".github/workflows/modele-socle.yml": v1[
                    "template/.github/workflows/modele-socle.yml"
                ],
                "scripts/modele/plan.py": v1["template/scripts/modele/plan.py"],
                "scripts/modele/texte_pr.py": v1["template/scripts/modele/texte_pr.py"],
            }
        ),
        api("zeta-donnees", "/pulls", state="open", per_page="100"): ok([[]]),
        api("zeta-donnees", "/pulls", state="all", per_page="50"): ok([]),
        api("zeta-donnees", "/rules/branches/main"): ok([]),
    }


# --- le lancement ------------------------------------------------------------------------------


def lancer(faux, banc, reponses: dict, dossier: Path, *options, tempdir=None):
    """Le relevé, lancé dans le processus contre le faux `gh` : (code, sortie, appels)."""
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / "reponses.json"
    fichier.write_text(json.dumps(reponses), encoding="utf-8")
    journal = dossier / "journal.jsonl"
    journal.write_text("", encoding="utf-8")
    anciens = {k: os.environ.get(k) for k in ("FAUX_GH_REPONSES", "FAUX_GH_JOURNAL")}
    ancien_tempdir = tempfile.tempdir
    os.environ["FAUX_GH_REPONSES"] = str(fichier)
    os.environ["FAUX_GH_JOURNAL"] = str(journal)
    if tempdir is not None:
        tempfile.tempdir = str(tempdir)
    sortie = io.StringIO()
    try:
        with contextlib.redirect_stdout(sortie):
            code = releve.main(
                [*options, "--compte", COMPTE, "--gh", str(faux), "--clone", str(banc.racine)]
            )
    finally:
        tempfile.tempdir = ancien_tempdir
        for k, v in anciens.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    appels = [json.loads(ligne) for ligne in journal.read_text(encoding="utf-8").splitlines()]
    return code, sortie.getvalue(), appels


@pytest.fixture(scope="module")
def complet(banc, faux, tmp_path_factory):
    """Le relevé des six dépôts, une fois pour le module, son dossier temporaire sous `tmp`."""
    dossier = tmp_path_factory.mktemp("complet")
    tmp = dossier / "temporaire-du-releve"
    tmp.mkdir()
    code, sortie, appels = lancer(faux, banc, reponses_completes(banc), dossier, tempdir=tmp)
    return SimpleNamespace(
        code=code,
        sortie=sortie,
        lignes=sortie.splitlines(),
        appels=appels,
        dossier=dossier,
        tmp=tmp,
    )


@pytest.fixture(scope="module")
def clair(banc, faux, tmp_path_factory):
    """Le relevé d'un seul projet, qui n'a rien à lire."""
    dossier = tmp_path_factory.mktemp("clair")
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok([[depot("clair")]]),
        **projet_clair("clair"),
    }
    code, sortie, appels = lancer(faux, banc, reponses, dossier)
    return SimpleNamespace(code=code, sortie=sortie, lignes=sortie.splitlines(), appels=appels)


@pytest.fixture(scope="module")
def causes(banc, faux, tmp_path_factory):
    """Six projets : cinq ont chacun une seule cause du code 1, le dernier rien à lire."""
    dossier = tmp_path_factory.mktemp("causes")
    noms = ("c-fichiers", "c-ouvertes", "c-plans", "c-regle", "c-rien", "c-textes")
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok(
            [[depot(nom, prive=nom != "c-regle") for nom in noms]]
        ),
        **projet(
            "c-plans",
            "v0.1.0",
            entrees={".claude/plans/plan-b.md": "b" * 40},
            blobs={"b" * 40: PLAN_MAL_FORME},
        ),
        **projet(
            "c-ouvertes",
            ouvertes={1: [{"filename": ".claude/plans/neuf.md", "status": "added"}]},
        ),
        **projet("c-textes", "v0.1.0", prs={5: CORPS_ACCORD}),
        **projet("c-regle", regles=regle("socle / secrets")),
        **projet("c-fichiers", "v0.1.0", entrees={".githooks/pre-commit": "1" * 40}),
        **projet("c-rien"),
    }
    code, sortie, appels = lancer(faux, banc, reponses, dossier)
    return SimpleNamespace(code=code, sortie=sortie, lignes=sortie.splitlines(), appels=appels)


def lignes_de(lignes: list, nom: str, rubrique: str) -> list:
    debut = f"relevé : {nom} : {rubrique} : "
    return [ligne.removeprefix(debut) for ligne in lignes if ligne.startswith(debut)]


# --- les tests ---------------------------------------------------------------------------------


def test_releve_projets(complet):
    lignes = complet.lignes
    assert "relevé : alpha : v0.1.0, cible aucune, nature code, fusion session" in lignes
    assert "relevé : beta : v0.2.0, cible aucune, nature donnees, fusion edouard" in lignes
    # la cible `donnees` n'a pas de ligne `nature` : sa nature est `donnees`
    assert "relevé : zeta-donnees : v0.1.0, cible donnees, nature donnees, fusion session" in lignes
    for nom in ("gamma", "delta", "epsilon"):
        assert not any(ligne.startswith(f"relevé : {nom} :") for ligne in lignes), nom
    # deux pages de `user/repos`, l'archivé compris : six dépôts examinés
    assert lignes[-1] == "relevé : 6 dépôts examinés, 3 projets, 2 lus, 1 non relevés, 1 à lire"
    assert lignes[-2] == LIMITES
    # l'archivé n'est pas lu
    assert not any("gamma" in json.dumps(appel["args"]) for appel in complet.appels)
    # chaque appel a vu son entrée fermée : le faux, qui la lit jusqu'à la fin, a répondu
    assert complet.code == releve.EXIT_A_LIRE


def test_releve_reponses():
    texte = (
        "# Écrit par Copier. Ne pas modifier à la main.\n"
        "_commit: v0.10.0\n"
        "_src_path: gh:EdouardZemb/modele-projet\n"
        "description: 'Le dépôt d''essai, dont la description\n"
        "  court sur deux lignes'\n"
        "# un commentaire\n"
        'fusion: "ed\\"ou\\\\ard"\n'
        "nom: essai\n"
    )
    reponses = releve._lire_reponses(texte)
    assert reponses == {
        "_commit": "v0.10.0",
        "_src_path": "gh:EdouardZemb/modele-projet",
        "description": "Le dépôt d'essai, dont la description court sur deux lignes",
        "fusion": 'ed"ou\\ard',
        "nom": "essai",
    }
    # comme un vrai lecteur de YAML
    assert reponses == yaml.safe_load(texte)
    assert releve._semes(COPIER_DU_BANC) == [
        "CLAUDE.md",
        "docs/modele/seme.md",
        ".github/workflows/ci.yml",
    ]
    copier = (RACINE / "copier.yml").read_text(encoding="utf-8")
    assert releve._semes(copier) == yaml.safe_load(copier)["_skip_if_exists"]


def test_releve_arguments(complet):
    assert complet.appels
    for appel in complet.appels:
        args = appel["args"]
        assert not any(INTERDITS & set(a) for a in args), args
        assert "--jq" not in args, args
        assert args[0] == "api", args
        assert appel["GH_PAGER"] == "", args
        if args[1] != "graphql":
            assert args[2:4] == ["-X", "GET"], args
    # aucun refus du faux : aucune ligne « erreur 2 » ni « erreur ? »
    assert "erreur" not in complet.sortie


def test_releve_plans(complet, clair):
    alpha = lignes_de(complet.lignes, "alpha", "plans")
    # le plan d'un sous-dossier, lu par son blob, en base64 coupé ; un `.txt` n'est pas un plan
    assert "sous/plan-a.md : même verdict" in alpha
    assert "sous/plan-a.md : refuserait s'il était neuf" in alpha
    assert (
        "sous/plan-a.md : neuf : section « Effets cherchés » absente (titre de niveau 2)" in alpha
    )
    assert "plan-b.md : verdict changé" in alpha
    assert (
        "plan-b.md : version du projet : Outils et cas limites, ligne 2 : forme ancienne : "
        "- <outil> — <cas limite> — <test>, ou « Aucun. » seul"
    ) in alpha
    assert (
        "plan-b.md : tête : Outils et cas limites, ligne 2 : forme attendue : - <outil>"
        " — <cas limite> — <test>, ou « Aucun. » seul"
    ) in alpha
    assert not any("notes.txt" in ligne for ligne in alpha)
    # « refuserait s'il était neuf » est une information : le code reste à 0
    assert lignes_de(clair.lignes, "clair", "plans")[:2] == [
        "plan-a.md : même verdict",
        "plan-a.md : refuserait s'il était neuf",
    ]
    assert clair.code == releve.EXIT_RIEN


def test_releve_pr_ouvertes(complet):
    ouvertes = lignes_de(complet.lignes, "alpha", "PR ouvertes")
    assert ouvertes == [
        # en seconde page de ses fichiers
        "PR 7 : ajoute un plan : neuf.md",
        # un plan renommé compte pour un ajout
        "PR 8 : ajoute un plan : renomme.md",
        "3 ouvertes, 2 ajoutent un plan",
    ]
    assert lignes_de(complet.lignes, "beta", "PR ouvertes") == ["0 ouvertes, 0 ajoutent un plan"]
    assert complet.code == releve.EXIT_A_LIRE


def test_releve_textes(complet):
    textes = lignes_de(complet.lignes, "alpha", "textes")
    assert "PR 6 : passait, refuse" in textes
    # la fermeture lue par GraphQL arrive à `texte_pr.py` de la tête
    assert (
        "PR 6 : tête : texte de la PR : ferme une issue : ligne « Tête relue : <SHA complet> »"
        " absente"
    ) in textes
    assert "PR 5 : refusait, passe" in textes
    # un verdict qui ne change pas ne s'affiche pas ; l'auteur `dependabot[bot]`, pris par REST,
    # est exempté par les deux versions
    assert not any(t.startswith(("PR 2 ", "PR 4 ")) for t in textes)
    # absente de la réponse GraphQL
    assert "PR 3 : non relevés (absente de la réponse GraphQL)" in textes
    assert textes[-1] == "4 PR lues, 2 verdicts changés, 1 non relevées"
    graphql = [appel["args"] for appel in complet.appels if appel["args"][1] == "graphql"]
    assert len(graphql) == 1 and "name=alpha" in graphql[0]


def test_releve_regle(complet, clair):
    assert lignes_de(complet.lignes, "alpha", "règle") == [
        "contrôle géré absent : texte-pr",
        "contrôle propre : tests (propre)",
    ]
    assert lignes_de(complet.lignes, "beta", "règle") == ["aucune règle"]
    assert lignes_de(clair.lignes, "clair", "règle") == [
        "contrôle propre : tests (propre)",
        "contrôles gérés présents",
    ]
    assert clair.code == releve.EXIT_RIEN


def test_releve_fichiers_geres(complet):
    assert lignes_de(complet.lignes, "alpha", "fichiers gérés") == [
        ".githooks/pre-commit : modifié dans le projet",
        # le dossier `{% if cible != 'donnees' %}modele{% endif %}`, évalué
        ".github/modele/ruleset-main.json : identique",
        ".github/workflows/modele-socle.yml : absent du projet",
        ".github/workflows/modele-x.yml : non comparé (rendu)",
        "docs/modele/methode.md : identique",
        "docs/modele/nouveau.md : nouveau dans le modèle",
        "scripts/modele/plan.py : identique",
        "scripts/modele/reglages.py : non comparé (rendu)",
        "scripts/modele/texte_pr.py : identique",
    ]
    # en cible `donnees`, le dossier conditionnel n'est pas rendu
    zeta = lignes_de(complet.lignes, "zeta-donnees", "fichiers gérés")
    assert ".githooks/pre-commit : identique" in zeta
    assert not any("ruleset-main.json" in ligne for ligne in zeta)
    assert lignes_de(complet.lignes, "beta", "fichiers gérés") == ["aucun changé depuis v0.2.0"]
    # un semé, `.claude/settings.json` et un fichier hors des chemins gérés sont écartés
    for ecarte in ("seme.md", "settings.json", "README.md"):
        assert ecarte not in complet.sortie, ecarte
    assert LIMITES in complet.lignes


def test_releve_depuis_et_prs(banc, faux, tmp_path):
    """`--depuis` ouvre l'intervalle des fichiers gérés pour tous, mais chacun se compare encore au
    modèle à la version du projet ; `--prs N` donne la page des PR et la requête GraphQL."""
    v2 = banc.v2
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok([[depot("sigma", prive=True)]]),
        **reponses_de_base("sigma", copier_answers("v0.2.0")),
        api("sigma", "/git/trees/main", recursive="1"): arbre(
            {
                ".githooks/pre-commit": v2["template/.githooks/pre-commit"],
                "docs/modele/methode.md": banc.v1["template/docs/modele/methode.md"],
            }
        ),
        api("sigma", "/pulls", state="open", per_page="100"): ok([[]]),
        api("sigma", "/pulls", state="all", per_page="5"): ok([pr(1, CORPS_AUCUN)]),
        cle("graphql", query=releve.REQUETE, owner=COMPTE, name="sigma", n="5"): ok(
            {"data": {"repository": {"pullRequests": {"nodes": [fermetures(1)]}}}}
        ),
        api("sigma", "/rules/branches/main"): ok([]),
    }
    code, sortie, _ = lancer(faux, banc, reponses, tmp_path, "--depuis", "v0.1.0", "--prs", "5")
    geres = lignes_de(sortie.splitlines(), "sigma", "fichiers gérés")
    assert ".githooks/pre-commit : identique" in geres
    assert "docs/modele/methode.md : modifié dans le projet" in geres
    # présent à la version du projet, absent du projet : il n'est plus nouveau
    assert "docs/modele/nouveau.md : absent du projet" in geres
    assert lignes_de(sortie.splitlines(), "sigma", "textes") == [
        "1 PR lues, 0 verdicts changés, 0 non relevées"
    ]
    assert code == releve.EXIT_A_LIRE


def test_releve_erreur_passagere(banc, faux, tmp_path):
    """Un 403, un 502 sur `.copier-answers.yml`, un 502 sur l'arbre : trois projets non relevés,
    jamais pris pour des dépôts qui ne sont pas des projets ; le suivant est lu."""
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok(
            [[depot("eta"), depot("iota"), depot("kappa"), depot("theta", prive=True)]]
        ),
        api("eta", "/contents/.copier-answers.yml", ref="main"): erreur(403),
        api("theta", "/contents/.copier-answers.yml", ref="main"): erreur(502),
        **reponses_de_base("iota", copier_answers("v0.2.0")),
        api("iota", "/git/trees/main", recursive="1"): erreur(502),
        **projet_clair("kappa"),
    }
    code, sortie, _ = lancer(faux, banc, reponses, tmp_path)
    lignes = sortie.splitlines()
    assert "relevé : eta : non relevé : réponses : erreur 403" in lignes
    assert "relevé : theta : non relevé : réponses : erreur 502" in lignes
    assert "relevé : iota : non relevé : arbre : erreur 502" in lignes
    assert "relevé : kappa : plans : plan-a.md : même verdict" in lignes
    # le message de l'erreur, sur l'une et l'autre sortie de `gh`, n'est jamais cité
    assert MARQUEUR not in sortie
    assert lignes[-1] == "relevé : 4 dépôts examinés, 4 projets, 1 lus, 3 non relevés, 0 à lire"
    assert code == releve.EXIT_A_LIRE


def test_releve_version_absente(banc, faux, tmp_path):
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok([[depot("omega")]]),
        **reponses_de_base("omega", copier_answers("v9.9.9")),
    }
    code, sortie, appels = lancer(faux, banc, reponses, tmp_path)
    lignes = sortie.splitlines()
    assert (
        "relevé : omega : non relevé : version absente du clone, lancer git fetch --tags" in lignes
    )
    assert lignes[-1] == "relevé : 1 dépôts examinés, 1 projets, 0 lus, 1 non relevés, 0 à lire"
    assert code == releve.EXIT_A_LIRE
    # le projet s'arrête là : son arbre n'est pas lu
    assert len(appels) == 2


def test_releve_arbre_tronque(banc, faux, tmp_path):
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok([[depot("psi")]]),
        **reponses_de_base("psi", copier_answers("v0.2.0")),
        api("psi", "/git/trees/main", recursive="1"): arbre({"README.md": "5" * 40}, tronque=True),
    }
    code, sortie, _ = lancer(faux, banc, reponses, tmp_path)
    assert "relevé : psi : non relevé : arbre tronqué" in sortie.splitlines()
    assert code == releve.EXIT_A_LIRE


def test_releve_extraction(banc, tmp_path):
    """Seuls les `*.py` d'une version s'extraient, jamais un `.jinja`, octet pour octet, par
    `git show` ; le `plan.py` extrait s'exécute, avec son voisin."""
    tete = tmp_path / "tete"
    tete.mkdir()
    noms = releve._extraire(banc.racine, "v0.2.0", tete)
    attendus = sorted(f.name for f in SCRIPTS.iterdir() if f.is_file() and f.suffix == ".py")
    assert noms == attendus
    assert sorted(f.name for f in tete.iterdir()) == attendus
    assert (tete / "plan.py").read_bytes() == (SCRIPTS / "plan.py").read_bytes()
    ancienne = tmp_path / "ancienne"
    ancienne.mkdir()
    releve._extraire(banc.racine, "v0.1.0", ancienne)
    assert (ancienne / "plan.py").read_bytes() != (tete / "plan.py").read_bytes()
    (tmp_path / "plan.md").write_text(PLAN_EN_COURS, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", "-B", str(tete / "plan.py"), "plan.md", "--sans-lieux"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert "plan : plan.md : 0 mécanismes, lieux non ouverts" in r.stdout.decode("utf-8")


def test_releve_codes(banc, faux, tmp_path, capsys, clair, complet):
    assert clair.code == releve.EXIT_RIEN
    assert complet.code == releve.EXIT_A_LIRE
    hors = tmp_path / "hors"
    hors.mkdir()
    nu = tmp_path / "nu"
    nu.mkdir()
    _git(nu, "init", "-q")
    # chaque refus dit sa raison : un refus venu d'ailleurs, comme le faux lancé sans réponses,
    # ne passe pas pour celui du cas
    cas = [
        (["--gh", str(tmp_path / "absent"), "--clone", str(banc.racine)], "gh introuvable"),
        (["--gh", str(faux), "--clone", str(hors)], "pas un clone du modèle"),
        (["--gh", str(faux), "--clone", str(nu)], "pas un clone du modèle"),
        (["--gh", str(faux), "--clone", str(banc.racine), "--prs", "0"], "--prs de 1 à 100"),
        (["--gh", str(faux), "--clone", str(banc.racine), "--prs", "101"], "--prs de 1 à 100"),
        (["--gh", str(faux), "--clone", str(banc.racine), "--prs", "abc"], "(voir --help)"),
        (["--gh", str(faux), "--clone", str(banc.racine), "--depuis", "v9.9.9"], "--depuis"),
    ]
    for options, raison in cas:
        assert releve.main(["--compte", COMPTE, *options]) == releve.EXIT_USAGE, options
        sortie = capsys.readouterr()
        assert sortie.out == "", options
        assert sortie.err.startswith("relevé : usage invalide"), options
        assert raison in sortie.err, options
    # `gh` sans accès : la liste des dépôts refusée
    reponses = {cle("user/repos", affiliation="owner", per_page="100"): erreur(401)}
    code, sortie, appels = lancer(faux, banc, reponses, tmp_path / "sans-acces")
    assert code == releve.EXIT_USAGE
    assert sortie == ""
    assert "gh sans accès (dépôts : erreur 401)" in capsys.readouterr().err
    assert len(appels) == 1
    # une erreur passagère sur la liste des dépôts n'est pas une erreur d'usage
    reponses = {cle("user/repos", affiliation="owner", per_page="100"): erreur(502)}
    code, sortie, _ = lancer(faux, banc, reponses, tmp_path / "passagere")
    assert code == releve.EXIT_A_LIRE
    assert sortie.splitlines() == ["relevé : non relevé : dépôts : erreur 502"]
    assert capsys.readouterr().err == ""
    # un clone dont la tête ne dit pas ses contrôles gérés : absent, vide, illisible
    env = _env_git(tmp_path / "home")
    for nom, regle_de_la_tete in (
        ("sans-regle", None),
        ("regle-vide", '{"rules": []}'),
        ("regle-illisible", "{pas du JSON"),
    ):
        clone = tmp_path / nom
        fichiers = {"copier.yml": COPIER_DU_BANC, "template/scripts/modele/plan.py": ""}
        if regle_de_la_tete is not None:
            fichiers[REGLE] = regle_de_la_tete
        _depot_minimal(clone, fichiers, env)
        options = ["--compte", COMPTE, "--gh", str(faux), "--clone", str(clone)]
        assert releve.main(options) == releve.EXIT_USAGE, nom
        sortie = capsys.readouterr()
        assert sortie.out == "", nom
        assert "contrôles gérés illisibles dans la tête du clone" in sortie.err, nom


def test_releve_sortie_sans_contenu(complet, tmp_path_factory):
    """Le marqueur est dans les plans, les corps et les titres des PR, le nom de leur branche, la
    branche par défaut de `beta` et le message d'une erreur de `gh` : la sortie ne le cite pas."""
    assert MARQUEUR not in complet.sortie
    # la branche qui le porte a bien été lue
    assert any(BRANCHE in " ".join(appel["args"]) for appel in complet.appels)
    base = tmp_path_factory.getbasetemp()
    for chemin in (base, complet.dossier, complet.tmp):
        for forme in (str(chemin), chemin.as_posix(), chemin.name):
            assert forme not in complet.sortie, forme
    # le dossier temporaire du relevé est retiré
    assert list(complet.tmp.iterdir()) == []


def test_releve_causes_du_code_1(causes):
    """Chacune des cinq causes du code 1, seule dans son projet : un relevé qui en oublierait une
    compterait un projet à lire de moins."""
    lignes = causes.lignes
    assert "relevé : c-plans : plans : plan-b.md : verdict changé" in lignes
    assert "relevé : c-ouvertes : PR ouvertes : PR 1 : ajoute un plan : neuf.md" in lignes
    assert "relevé : c-textes : textes : PR 5 : refusait, passe" in lignes
    assert "relevé : c-regle : règle : contrôle géré absent : texte-pr" in lignes
    assert (
        "relevé : c-fichiers : fichiers gérés : .githooks/pre-commit : modifié dans le projet"
    ) in lignes
    assert lignes[-1] == "relevé : 6 dépôts examinés, 6 projets, 6 lus, 0 non relevés, 5 à lire"
    assert causes.code == releve.EXIT_A_LIRE


def test_releve_resultat_d_un_script():
    """Un vrai refus finit par la ligne de refus du script ; un code 1 sans elle est un plantage,
    et tout autre code qu'un 0 ou un 1, une erreur d'usage ou un plantage."""
    refus = "plan : refus"
    assert releve._resultat(None, refus) is None
    assert releve._resultat((0, ["plan : x"]), refus) == (0, ["plan : x"])
    assert releve._resultat((1, ["plan : x", refus]), refus) == (1, ["plan : x", refus])
    assert releve._resultat((1, ["plan : x"]), refus) is None
    assert releve._resultat((1, []), refus) is None
    assert releve._resultat((1, [refus, "plan : x"]), refus) is None
    for code in (2, 3, 64, -1):
        assert releve._resultat((code, ["plan : x", refus]), refus) is None, code


def test_releve_script_en_echec(banc, faux, tmp_path):
    """`plan.py` qui plante, `texte_pr.py` qui sort par 3, et deux `texte_pr.py` en erreur
    d'usage (une PR sans auteur) : non relevés, jamais lus comme des verdicts."""
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok(
            [[depot("rho", prive=True), depot("tau", prive=True)]]
        ),
        **projet(
            "rho",
            "v0.0.9",
            entrees={".claude/plans/plan-a.md": "a" * 40},
            blobs={"a" * 40: PLAN_EN_COURS},
            prs={1: CORPS_AUCUN},
        ),
        **projet("tau", prs={2: CORPS_AUCUN}),
    }
    reponses[api("tau", "/pulls", state="all", per_page="50")] = ok(
        [{**pr(2, CORPS_AUCUN), "user": None}]
    )
    code, sortie, _ = lancer(faux, banc, reponses, tmp_path)
    lignes = sortie.splitlines()
    assert lignes_de(lignes, "rho", "plans") == [
        "plan-a.md : non relevé (plan.py en échec : version du projet)"
    ]
    assert lignes_de(lignes, "rho", "textes")[0] == (
        "PR 1 : non relevés (texte_pr.py en échec : version du projet)"
    )
    assert lignes_de(lignes, "tau", "textes")[0] == (
        "PR 2 : non relevés (texte_pr.py en échec : version du projet, tête)"
    )
    assert lignes[-1] == "relevé : 2 dépôts examinés, 2 projets, 0 lus, 2 non relevés, 0 à lire"
    assert code == releve.EXIT_A_LIRE


def test_releve_plan_py_qui_ne_se_lance_pas(banc, faux, tmp_path, monkeypatch):
    """Un `plan.py` qui ne se lance pas, aux trois passages : ni « même verdict », ni « refuserait
    s'il était neuf », mais un plan non relevé."""
    lancer_vrai = releve._Releve._lancer

    def sans_plan_py(self, script, args, cwd, env=None):
        return None if script.name == "plan.py" else lancer_vrai(self, script, args, cwd, env)

    monkeypatch.setattr(releve._Releve, "_lancer", sans_plan_py)
    reponses = {
        cle("user/repos", affiliation="owner", per_page="100"): ok([[depot("clair")]]),
        **projet_clair("clair"),
    }
    code, sortie, _ = lancer(faux, banc, reponses, tmp_path)
    lignes = sortie.splitlines()
    assert lignes_de(lignes, "clair", "plans") == [
        "plan-a.md : non relevé (plan.py en échec : version du projet, tête, tête par --neuf)"
    ]
    assert lignes[-1] == "relevé : 1 dépôts examinés, 1 projets, 0 lus, 1 non relevés, 0 à lire"
    assert code == releve.EXIT_A_LIRE


def test_releve_dossier_temporaire_non_retire(banc, faux, tmp_path, monkeypatch):
    """Le dossier temporaire, qui porte des plans privés, ne se retire pas : une ligne fixe le dit,
    sans son chemin, et le code passe à 1."""

    def verrouille(*args, **kwargs):
        raise PermissionError("verrouillé")

    monkeypatch.setattr(releve.shutil, "rmtree", verrouille)
    temporaire = tmp_path / "base-du-releve"
    temporaire.mkdir()
    reponses = {cle("user/repos", affiliation="owner", per_page="100"): ok([[]])}
    code, sortie, _ = lancer(faux, banc, reponses, tmp_path / "faux", tempdir=temporaire)
    lignes = sortie.splitlines()
    assert lignes[-2] == "relevé : 0 dépôts examinés, 0 projets, 0 lus, 0 non relevés, 0 à lire"
    assert lignes[-1] == "relevé : dossier temporaire non retiré"
    assert code == releve.EXIT_A_LIRE
    assert len(list(temporaire.iterdir())) == 1
    for forme in (str(temporaire), temporaire.as_posix(), temporaire.name):
        assert forme not in sortie, forme
