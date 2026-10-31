"""Banc d'essai : rend le modèle Copier dans un dossier temporaire."""

import os
import re
import secrets
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import copier
import pytest

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = RACINE / "template/scripts/modele"

# Les scripts du modèle sont importés directement par les tests.
sys.path.insert(0, str(SCRIPTS))

REGISTRE_ENTETE = "| N° | Famille | Date | Constat | Motif | Prévention | Critère de sortie | État |"

# Les numéros du plan d'un lot (ses décisions, ses tâches, les points de ses revues) ne vivent que
# dans le plan, qui disparaît à la clôture : aucun fichier distribué ne les cite.
RENVOI_AU_PLAN = re.compile(
    r"\b(?:Ruling|ruling) \d|\bP[1-8]\b|\btâche \d|\b[Dd]écision \d+ du lot|\bReview Focus\b"
    r"|\bconstat \d"
)

REPONSES_PAR_DEFAUT = {
    "nom": "essai",
    "description": "Projet d'essai",
    "cible": "aucune",
    "branche_principale": "main",
    "fusion": "session",
}

ALPHABET_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def cle_age_de_test() -> str:
    """Une clé publique age fabriquée au moment du test, jamais une clé du parc (M-0006, § 9).

    Par `age-keygen` s'il est là (l'identité privée n'est pas gardée), sinon `age1` et 58
    caractères tirés au hasard dans l'alphabet bech32 : la forme suffit au rendu."""
    age_keygen = shutil.which("age-keygen")
    if age_keygen:
        r = subprocess.run([age_keygen], capture_output=True, text=True, check=False)
        trouvee = re.search(r"^# public key: (age1[0-9a-z]{58})$", r.stdout, re.MULTILINE)
        if r.returncode == 0 and trouvee:
            return trouvee.group(1)
    return "age1" + "".join(secrets.choice(ALPHABET_BECH32) for _ in range(58))


CLE_SERVEUR_DE_TEST = cle_age_de_test()
CLE_HORS_LIGNE_DE_TEST = cle_age_de_test()
INSTANCE_DE_TEST = {
    "bloc_ports": 4310,
    "domaine": "exemple.org",
    "cle_serveur": CLE_SERVEUR_DE_TEST,
    "cle_hors_ligne": CLE_HORS_LIGNE_DE_TEST,
}

# Le mode à un dépôt : un projet `serveur` de nature `donnees` (d'avant M-0006) porte son instance,
# le domaine, le bloc de ports et les clés du parc.
REPONSES_SERVEUR = {
    **REPONSES_PAR_DEFAUT,
    "cible": "serveur",
    "nature": "donnees",
    "sauvegardes": True,
    **INSTANCE_DE_TEST,
}

# Le mode à deux dépôts : un dépôt de code `serveur` n'a rien de l'instance (M-0006, § 4).
REPONSES_SERVEUR_CODE = {
    **REPONSES_PAR_DEFAUT,
    "cible": "serveur",
    "nature": "code",
    "sauvegardes": True,
}

# Le dépôt de données d'un projet `serveur` : il porte l'instance du projet `essai`.
REPONSES_DONNEES_SERVEUR = {
    **REPONSES_PAR_DEFAUT,
    "nom": "essai-donnees",
    "cible": "donnees",
    "cible_code": "serveur",
    **INSTANCE_DE_TEST,
}


@pytest.fixture
def rendre(tmp_path):
    """Donne rendre(**reponses) -> Path, un rendu neuf du modèle depuis HEAD."""
    compteur = {"n": 0}

    def _rendre(**reponses):
        compteur["n"] += 1
        destination = tmp_path / f"rendu-{compteur['n']}"
        donnees = {**REPONSES_PAR_DEFAUT, **reponses}
        with warnings.catch_warnings():
            # Copier signale un dépôt local « sale » : c'est voulu, on teste le travail en cours.
            warnings.filterwarnings("ignore", message=".*dirty.*", category=Warning)
            warnings.filterwarnings("ignore", category=copier.errors.DirtyLocalWarning)
            copier.run_copy(
                str(RACINE),
                destination,
                data=donnees,
                vcs_ref="HEAD",
                defaults=True,
                unsafe=True,
                quiet=True,
            )
        return destination

    return _rendre


def fichiers_texte(racine: Path) -> list[Path]:
    """Tous les fichiers hors .git/, binaires exclus (octet nul dans les 8 premiers Kio)."""
    resultat = []
    for chemin in sorted(racine.rglob("*")):
        if not chemin.is_file() or ".git" in chemin.relative_to(racine).parts:
            continue
        with chemin.open("rb") as f:
            if b"\0" in f.read(8192):
                continue
        resultat.append(chemin)
    return resultat


@pytest.fixture
def env_isole(tmp_path):
    """Donne env_isole() -> dict : environnement sans HOME réel ni motifs privés."""

    def _env():
        home = tmp_path / "home-vide"
        home.mkdir(exist_ok=True)
        env = dict(os.environ)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env.pop("MOTIFS_INTERDITS", None)
        env.pop("DEPOT_PRIVE", None)  # en CI, la visibilité réelle ; ici, celle des réglages
        env.update(
            GIT_AUTHOR_NAME="Essai",
            GIT_AUTHOR_EMAIL="essai@example.com",
            GIT_COMMITTER_NAME="Essai",
            GIT_COMMITTER_EMAIL="essai@example.com",
        )
        return env

    return _env


def git(cwd, env, *args):
    r = subprocess.run(
        ["git", *args],
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def depot(tmp_path, env):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, env, "init", "-q", "-b", "main")
    git(d, env, "config", "core.autocrlf", "false")
    return d


def manque(dependance, raison):
    """Une dépendance du système manque : saut, ou échec si MODELE_TESTS_SANS_SAUT la nomme.

    MODELE_TESTS_SANS_SAUT est une liste séparée par des virgules ; « 1 » les vaut toutes.
    Une dépendance nommée qui manque fait échouer le test au lieu de le sauter (LE-16).
    """
    liste = {d.strip() for d in os.environ.get("MODELE_TESTS_SANS_SAUT", "").split(",") if d.strip()}
    if "1" in liste or dependance in liste:
        pytest.fail(f"{raison}, et MODELE_TESTS_SANS_SAUT exige {dependance}")
    pytest.skip(raison)


def exiger(*dependances):
    """Saute le test si une commande du système manque, sauf si MODELE_TESTS_SANS_SAUT la nomme."""
    for dependance in dependances:
        if not shutil.which(dependance):
            manque(dependance, f"{dependance} absent")


def trouver_bash():
    """bash de Git sous Windows (celui du PATH peut être celui de WSL), celui du PATH ailleurs."""
    if sys.platform == "win32":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            return str(git_bash)
    elif shutil.which("bash"):
        return shutil.which("bash")
    manque("bash", "bash absent")


def faux_gh(dossier, sorties):
    """Un faux « gh » dans `dossier`. `sorties` : {"pr checks": (code, texte), "api": (code, texte)}.

    Il choisit sa réponse d'après ses deux premiers arguments (`run list`, `pr list`,
    `workflow list`, `pr checks`), ou d'après le seul mot `api`, et note chaque appel dans `appels` et, pour les appels simultanés, dans un fichier `appel-…`.
    Une chaîne vaut (0, chaîne) pour « pr checks »."""
    if isinstance(sorties, str):
        sorties = {"pr checks": (0, sorties)}
    for cle, (code, texte) in sorties.items():
        k = cle.replace(" ", "-")
        (dossier / f"sortie-{k}").write_text(texte, encoding="utf-8", newline="")
        (dossier / f"code-{k}").write_text(str(code), encoding="utf-8")
    if sys.platform == "win32":
        f = dossier / "gh.cmd"
        f.write_text(
            "@echo off\r\n"
            'echo %* >> "%~dp0appels"\r\n'
            'echo %* > "%~dp0appel-%1-%2"\r\n'
            "set K=%1-%2\r\n"
            'if "%1"=="api" set K=api\r\n'
            'if not exist "%~dp0sortie-%K%" exit /b 1\r\n'
            'type "%~dp0sortie-%K%"\r\n'
            'set /p C=<"%~dp0code-%K%"\r\n'
            "exit /b %C%\r\n",
            encoding="utf-8",
            newline="",
        )
    else:
        f = dossier / "gh"
        f.write_text(
            "#!/bin/sh\n"
            'd=$(dirname "$0")\n'
            'echo "$*" >> "$d/appels"\n'
            'echo "$*" > "$d/appel-$1-$2"\n'
            'if [ "$1" = api ]; then k=api; else k="$1-$2"; fi\n'
            '[ -f "$d/sortie-$k" ] || exit 1\n'
            'cat "$d/sortie-$k"\n'
            'exit "$(cat "$d/code-$k")"\n',
            encoding="utf-8",
        )
        f.chmod(0o755)
    return f


def faux_gh_lent(dossier, texte="[]"):
    """Un « gh » qui attend cinq secondes avant d'imprimer `texte`."""
    if sys.platform == "win32":
        f = dossier / "gh.cmd"
        f.write_text(f"@echo off\r\nping -n 6 127.0.0.1 >nul\r\necho {texte}\r\n", encoding="utf-8")
    else:
        f = dossier / "gh"
        f.write_text(f"#!/bin/sh\nsleep 5\necho '{texte}'\n", encoding="utf-8")
        f.chmod(0o755)



def appels_de(dossier):
    """Les appels notés par `faux_gh`, même simultanés : un fichier `appel-<arg1>-<arg2>` par type d'appel."""
    return "".join(f.read_text(encoding="utf-8") for f in sorted(dossier.glob("appel-*")))
