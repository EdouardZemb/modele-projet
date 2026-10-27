"""Porte « fichiers masqués » : refuse un commit qui aligne ou met à jour le projet quand son
.gitignore masque un fichier que le modèle écrit.

Un fichier géré masqué par le .gitignore n'est pas indexé : la mise à jour du modèle l'écrit sur
le disque, mais il n'entre jamais dans un commit (LE-23). La porte ne s'applique qu'à un commit qui
touche `.copier-answers.yml` (indexé, ou présent sans être suivi). Elle examine les chemins gérés
communs, et ceux de la cible `serveur` sauf si la cible déclarée est une autre ; une cible
illisible vaut `serveur`. Un cache Python (`__pycache__`, `.pyc`) est ignoré.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : masques.py [--racine DOSSIER]  (--racine sert aux tests ; sinon la racine du dépôt courant)

Retour : 0 rien à signaler, 1 refus (fichier masqué, ou git en échec), 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

EXIT_USAGE = 64
REPONSES = ".copier-answers.yml"
CHEMINS_COMMUNS: tuple[str, ...] = (
    ".githooks/",
    "scripts/modele/",
    "docs/modele/",
    ".github/modele/",
    ".github/workflows/modele-*.yml",
    ".claude/skills/consigner/",
    ".claude/settings.json",
    ".copier-answers.yml",
)
CHEMINS_SERVEUR: tuple[str, ...] = ("deploiement/", "tests/deploiement/", ".sops.yaml")
LIGNE_CIBLE = re.compile(r"^cible:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
RENVOI = "Voir docs/modele/methode.md, « Les garde-fous »."


class ErreurGit(Exception):
    """Une commande git a échoué ou n'a pas pu être lancée."""


def _git(racine: Path, *args: str, entree: bytes | None = None) -> subprocess.CompletedProcess:
    """Lance git dans `racine` ; la sortie est lue en octets. Un échec de lancement lève ErreurGit."""
    try:
        return subprocess.run(
            ["git", *args],
            check=False,
            cwd=racine,
            capture_output=True,
            stdin=subprocess.DEVNULL if entree is None else None,
            input=entree,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ErreurGit(f"git {' '.join(args)} : {e}") from e


def _git_ok(racine: Path, *args: str, entree: bytes | None = None) -> str:
    """La sortie (UTF-8) d'une commande git qui doit réussir ; sinon ErreurGit."""
    r = _git(racine, *args, entree=entree)
    if r.returncode != 0:
        erreur = r.stderr.decode("utf-8", errors="replace").strip()
        raise ErreurGit(f"git {' '.join(args)} : {erreur}")
    return r.stdout.decode("utf-8", errors="replace")


def racine_du_depot(cwd: Path) -> Path:
    return Path(_git_ok(cwd, "rev-parse", "--show-toplevel").strip())


def declenche(racine: Path) -> bool:
    """Vrai si le commit touche les réponses du modèle : indexées, ou présentes sans être suivies."""
    if _git_ok(racine, "diff", "--cached", "--name-only", "--", REPONSES).strip():
        return True
    if not (racine / REPONSES).exists():
        return False
    return _git(racine, "ls-files", "--error-unmatch", "--", REPONSES).returncode != 0


def cible_serveur(racine: Path) -> bool:
    """Faux seulement si les réponses déclarent une cible autre que `serveur`."""
    try:
        texte = (racine / REPONSES).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True
    m = LIGNE_CIBLE.search(texte)
    return m is None or m.group(1).strip("'\"") == "serveur"


def fichiers_masques(racine: Path, serveur: bool) -> list[str]:
    """Les fichiers gérés présents sur le disque que le .gitignore masque, triés."""
    chemins = CHEMINS_COMMUNS + (CHEMINS_SERVEUR if serveur else ())
    sortie = _git_ok(
        racine, "ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", *chemins
    )
    noms = [n for n in sortie.split("\0") if n]
    return sorted(n for n in noms if "__pycache__" not in n.split("/") and not n.endswith(".pyc"))


def regle(racine: Path, chemin: str) -> str:
    """La règle qui masque `chemin`, sous la forme `<source>:<ligne>:<motif>`."""
    # -z n'existe qu'avec --stdin : le chemin passe par l'entrée, terminé par un octet nul.
    entree = chemin.encode("utf-8") + b"\0"
    champs = _git_ok(racine, "check-ignore", "-v", "-z", "--stdin", entree=entree).split("\0")
    if len(champs) < 3:
        return "règle inconnue"
    return ":".join(champs[:3])


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):
        self.exit(EXIT_USAGE, "masques : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(
        prog="masques.py", description="Refuse un fichier du modèle masqué par le .gitignore."
    )
    p.add_argument("--racine", type=Path, default=None, help="racine du dépôt (pour les tests)")
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0)
    try:
        racine = args.racine if args.racine is not None else racine_du_depot(Path.cwd())
        if not declenche(racine):
            return 0
        masques = fichiers_masques(racine, cible_serveur(racine))
        lignes = [
            f"modele-projet : refusé — fichier du modèle masqué par le .gitignore : {chemin} "
            f"(règle {regle(racine, chemin)}). Ajouter `!{chemin}` à ce fichier, puis l'indexer."
            for chemin in masques
        ]
    except ErreurGit as e:
        print(
            f"modele-projet : refusé — fichiers masqués invérifiables ({e}). {RENVOI}",
            file=sys.stderr,
        )
        return 1
    if lignes:
        print("\n".join(lignes), RENVOI, sep="\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
