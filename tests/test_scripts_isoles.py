"""Les scripts du modèle sous `python -I` : `-I` implique `-P`, qui retire le dossier du script du
chemin d'import, et `-E`, qui ignore `PYTHONDONTWRITEBYTECODE`, sur lequel compte `lancer.sh`.
Chaque script qui importe un voisin pose lui-même `sys.dont_write_bytecode`, puis ajoute son
dossier en fin de chemin d'import, sans doublon."""

import importlib
import json
import os
import subprocess
import sys

import pre_push
import pytest
import verifier_secrets
from conftest import REPONSES_DONNEES_SERVEUR, SCRIPTS, appels_de, faux_gh, git
from test_texte_pr import FERME_RIEN

BRANCHE = "principal"
# Les scripts qui importent un voisin : chacun porte sa propre copie de `_voisins`, puisque
# l'importer d'un autre serait importer un voisin.
VOISINS = (
    "documentation",
    "garde_claude",
    "pre_push",
    "signaux",
    "texte_pr",
    "verifier_donnees",
    "verifier_secrets",
)


def isole(rendu, env, script, *args, entree=None, **variables):
    """Lance `scripts/modele/<script>` du rendu sous `python -I`, depuis la racine du rendu."""
    return subprocess.run(
        [sys.executable, "-I", f"scripts/modele/{script}", *args],
        cwd=rendu,
        env={**env, **variables},
        input=entree,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_scripts_sous_python_isole(rendre, env_isole, tmp_path):
    """Dans un projet rendu, chaque script trouve ses voisins sous `-I`, sans écrire de
    `__pycache__`. Un code de sortie ne prouve rien ici : sans ses voisins, `signaux.py` rend 0,
    `verifier_secrets.py` rend 0 sans un mot, et `verifier_donnees.py` rend 64 dans les deux cas.
    Six lancements exigent un texte que seul le `reglages.py` du projet permet d'écrire : la
    branche, qu'aucun script n'a par défaut, pour `garde_claude.py`, `pre_push.py` et `signaux.py`
    sans argument ; la nature pour `documentation.py` ; le dépôt de code d'un dépôt de données pour
    `verifier_secrets.py` et `verifier_donnees.py`. Les deux autres ne lisent pas les réglages, et
    prouvent l'import de leur voisin `documentation` : `texte_pr.py` par un texte qu'il n'écrit pas
    sans lui, `signaux.py --branche` par l'absence de « non lue (erreur) », qu'il écrit quand cet
    import échoue."""
    # Les réponses par défaut portent déjà la branche : elle se change en fusionnant les deux.
    rendu = rendre(**{**REPONSES_DONNEES_SERVEUR, "branche_principale": BRANCHE})
    env = env_isole()
    for nom in ("GITHUB_REPOSITORY_OWNER", "DEPOT_PRIVE", "PYTHONDONTWRITEBYTECODE"):
        env.pop(nom, None)
    git(rendu, env, "init", "-q", "-b", BRANCHE)
    git(rendu, env, "commit", "-q", "--allow-empty", "-m", "chore: essai")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    faux_gh(bin_, {"run list": (0, "[]"), "pr list": (0, "[]"), "workflow list": (0, "[]")})
    env["PATH"] = str(bin_) + os.pathsep + env["PATH"]
    fermetures = tmp_path / "fermetures.json"
    fermetures.write_text(FERME_RIEN, encoding="utf-8")

    echecs = []

    def exiger(nom, r, code, presents=(), absents=()):
        sortie = r.stdout + r.stderr
        if r.returncode != code:
            echecs.append(f"{nom} : code {r.returncode}, attendu {code}\n{sortie}")
        for texte in presents:
            if texte not in sortie:
                echecs.append(f"{nom} : « {texte} » absent\n{sortie}")
        for texte in absents:
            if texte in sortie:
                echecs.append(f"{nom} : « {texte} » présent\n{sortie}")

    commande = {"tool_name": "Bash", "tool_input": {"command": f"git push origin {BRANCHE}"}}
    r = isole(rendu, env, "garde_claude.py", entree=json.dumps({**commande, "cwd": str(rendu)}))
    exiger("garde_claude.py", r, 2, [f"push vers {BRANCHE}"])

    entree = f"refs/heads/x 1111 refs/heads/{BRANCHE} 0000\n"
    r = isole(rendu, env, "pre_push.py", entree=entree)
    exiger("pre_push.py", r, 1, [f"refs/heads/{BRANCHE}"])

    # Sans `--branche`, la branche vient des réglages du projet, puis va à `gh`. Lu ici : le
    # lancement suivant passe la même branche à `gh`.
    r = isole(rendu, env, "signaux.py")
    exiger("signaux.py", r, 0, ["rien de rouge"], ["erreur interne", "non lue (erreur)"])
    if f"--branch {BRANCHE}" not in appels_de(bin_):
        echecs.append(f"signaux.py : « --branch {BRANCHE} » absent des appels\n{appels_de(bin_)}")

    # Avec `--branche`, `signaux.py` n'importe que `documentation` : l'erreur de cet import serait
    # rattrapée, et se lirait « non lue (erreur) », sous un texte par ailleurs complet.
    r = isole(rendu, env, "signaux.py", "--branche", BRANCHE)
    exiger("signaux.py --branche", r, 0, ["rien de rouge"], ["erreur interne", "non lue (erreur)"])

    r = isole(rendu, env, "documentation.py")
    exiger("documentation.py", r, 0, ["licence : non exigée (nature donnees)"], ["Traceback"])

    r = isole(rendu, env, "verifier_secrets.py")
    exiger("verifier_secrets.py", r, 0)
    if r.stdout.strip() != verifier_secrets.MESSAGE_DONNEES:
        echecs.append(f"verifier_secrets.py : sortie inattendue\n{r.stdout + r.stderr}")

    r = isole(rendu, env, "verifier_donnees.py", "--code", ".")
    exiger("verifier_donnees.py", r, 64, ["le compte des images manque"])

    r = isole(
        rendu,
        env,
        "texte_pr.py",
        "--fermetures",
        str(fermetures),
        CORPS="## Écarts à la spec\n\nAucun.\n",
        AUTEUR="x",
        TETE="a" * 40,
    )
    exiger("texte_pr.py", r, 0, ["écarts à la spec : aucun"])

    assert not echecs, "\n\n".join(echecs)
    # Avant tout lancement sans `-I` dans ce rendu : les imports ont eu lieu, puisque les textes
    # exigés en dépendent, et aucun n'a laissé de cache.
    assert list(rendu.rglob("__pycache__")) == []


def test_voisins_sans_doublon(monkeypatch):
    """Le dossier du script s'ajoute en fin de chemin d'import, une seule fois, même quand `main`
    est appelé plusieurs fois dans le même processus, comme le font les tests. En tête, il
    masquerait la bibliothèque standard, que `-I` protège exprès."""
    dossier = os.path.dirname(os.path.abspath(pre_push.__file__))
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != dossier])
    monkeypatch.delitem(sys.modules, "reglages", raising=False)
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    assert dossier not in sys.path
    # `template/` n'a pas de `reglages.py`, seulement son gabarit : 64, sans lire l'entrée.
    assert pre_push.main([]) == 64
    assert pre_push.main([]) == 64
    assert sys.path.count(dossier) == 1, sys.path
    assert sys.path[-1] == dossier, sys.path


def test_voisins_partout():
    """Chaque script qui porte `_voisins` est éprouvé ci-dessous : une copie neuve s'y ajoute."""
    porteurs = {p.stem for p in SCRIPTS.glob("*.py") if "def _voisins(" in p.read_text("utf-8")}
    assert porteurs == set(VOISINS)


@pytest.mark.parametrize("nom", VOISINS)
def test_chaque_voisins_sans_doublon(nom, monkeypatch):
    """Chaque copie, appelée deux fois, pose `sys.dont_write_bytecode` et laisse le dossier du
    script une seule fois dans le chemin d'import, en dernier."""
    module = importlib.import_module(nom)
    assert module._voisins.__module__ == nom
    dossier = os.path.dirname(os.path.abspath(module.__file__))
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != dossier])
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    module._voisins()
    module._voisins()
    assert sys.dont_write_bytecode is True
    assert sys.path.count(dossier) == 1, sys.path
    assert sys.path[-1] == dossier, sys.path
