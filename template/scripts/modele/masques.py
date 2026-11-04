"""Porte « fichiers masqués » : refuse un commit qui aligne ou met à jour le projet quand son
.gitignore masque un fichier que le modèle écrit, ou un secret chiffré que la chaîne lit.

Un fichier géré masqué par le .gitignore n'est pas indexé : la mise à jour du modèle l'écrit sur
le disque, mais il n'entre jamais dans un commit (LE-23). La porte ne s'applique qu'à un commit qui
touche `.copier-answers.yml` (indexé, ou présent sans être suivi). Elle examine les chemins gérés
communs, et ceux de la cible `serveur` sauf si la cible déclarée est une autre ; une cible
illisible vaut `serveur`. En cible `donnees`, elle examine aussi `config/README.md` et
`contenu/README.md`, semés, puis, sauf si `cible_code` vaut `aucune`, l'instance du dépôt de
données : `.sops.yaml`, `env/prod.env`, `env/staging.env`, `cles/*.pub` et les secrets chiffrés
`secrets/*.env.enc`. Ce qu'un dépôt de données peut ignorer (un secret en clair, une clé privée,
un fichier local de `config/` ou de `contenu/`) n'est pas examiné. Un cache Python
(`__pycache__`, `.pyc`) est ignoré.

Le remède est une exception nommée au .gitignore : `!<fichier>`, ou `!<dossier>/` quand un dossier
parent est exclu, car git ne regarde pas ce que contient un dossier exclu. Un dossier de secrets
exclu (`secrets/`, `deploiement/secrets/`) ne se lève jamais seul, ce qui laisserait entrer les
secrets en clair : le remède le lève, en exclut le contenu, puis n'admet que ce que la chaîne y
lit, `!/secrets/`, `/secrets/*` et `!/secrets/*.env.enc`. Ces lignes sont ancrées à la racine :
`!secrets/` vaudrait à toute profondeur, et ferait paraître les dossiers `secrets/` imbriqués.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : masques.py [--racine DOSSIER]  (--racine sert aux tests ; sinon la racine du dépôt courant)

Retour : 0 rien à signaler, 1 refus (fichier masqué, ou git en échec), 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import fnmatch
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
    ".github/ISSUE_TEMPLATE/lot.yml",
    ".github/pull_request_template.md",
    ".claude/skills/consigner/",
    ".claude/settings.json",
    ".copier-answers.yml",
)
CHEMINS_SERVEUR: tuple[str, ...] = (
    "deploiement/",
    "tests/deploiement/",
    ".sops.yaml",
    ".github/actions/modele-image-construire/",
    ".github/actions/modele-image-publier/",
)
# Un dépôt de données (cible `donnees`) : ses deux README.md, semés. Le reste de `config/` et de
# `contenu/` est au projet, qui peut en ignorer une partie.
CHEMINS_DONNEES: tuple[str, ...] = (
    "config/README.md",
    "contenu/README.md",
)
# L'instance d'un projet `serveur` dans son dépôt de données (`cible_code: serveur`) : ce que le
# modèle y sème, et les secrets chiffrés que la chaîne y lit. Rien d'autre : un secret en clair
# sous `secrets/`, ou une clé privée sous `cles/`, reste masqué sans refus.
CHEMINS_INSTANCE: tuple[str, ...] = (
    ".sops.yaml",
    "env/prod.env",
    "env/staging.env",
    "cles/*.pub",
    "secrets/*.env.enc",
)
# Les secrets chiffrés que la chaîne lit : ils ne sont pas du modèle, mais doivent entrer. Un motif
# ne vaut qu'au premier niveau de son dossier, comme dans `.sops.yaml`.
SECRETS_CHIFFRES: tuple[str, ...] = ("secrets/*.env.enc", "deploiement/secrets/*.env.enc")
# Les dossiers de secrets, et ce que la chaîne y lit : le seul contenu à y admettre.
DOSSIERS_DE_SECRETS: dict[str, tuple[str, ...]] = {
    "secrets/": ("*.env.enc",),
    "deploiement/secrets/": ("*.cles", "*.env.enc"),
}
LIGNE_CIBLE = re.compile(r"^cible:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
LIGNE_CIBLE_CODE = re.compile(r"^cible_code:[ \t]*(\S+)[ \t]*$", re.MULTILINE)
AUTRE_REMEDE = (
    "Si ce fichier n'est ni du modèle ni un secret chiffré que la chaîne lit (un fichier local), "
    "le sortir de ce dossier ; ne jamais lever le masque d'un secret en clair."
)
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


def _reponse(texte: str, ligne: re.Pattern[str]) -> str | None:
    """La valeur d'une réponse de premier niveau, sans ses guillemets ; None si elle est absente."""
    m = ligne.search(texte)
    return None if m is None else m.group(1).strip("'\"")


def chemins_examines(racine: Path) -> tuple[str, ...]:
    """Les chemins à examiner, selon la cible que déclarent les réponses.

    Toujours les chemins communs. En cible `serveur`, ou si la cible est illisible, ceux de la
    cible `serveur`. En cible `donnees`, les deux README.md, et l'instance sauf si `cible_code`
    vaut `aucune` : une `cible_code` illisible vaut `serveur`."""
    try:
        texte = (racine / REPONSES).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return CHEMINS_COMMUNS + CHEMINS_SERVEUR
    cible = _reponse(texte, LIGNE_CIBLE)
    if cible is None or cible == "serveur":
        return CHEMINS_COMMUNS + CHEMINS_SERVEUR
    if cible == "donnees":
        instance = () if _reponse(texte, LIGNE_CIBLE_CODE) == "aucune" else CHEMINS_INSTANCE
        return CHEMINS_COMMUNS + CHEMINS_DONNEES + instance
    return CHEMINS_COMMUNS


def fichiers_masques(racine: Path, chemins: tuple[str, ...]) -> list[str]:
    """Les fichiers du modèle présents sur le disque que le .gitignore masque, triés.

    `--glob-pathspecs` : un `*` ne franchit pas un `/`, comme dans un .gitignore. Sans lui,
    `secrets/*.env.enc` prendrait aussi `secrets/sous/x.env.enc`. Un chemin sans motif vaut
    toujours pour ce qu'il contient."""
    sortie = _git_ok(
        racine,
        "--glob-pathspecs",
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
        *chemins,
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


def _parents(chemin: str) -> list[str]:
    """Les dossiers qui contiennent `chemin`, de la racine vers lui : `a/`, `a/b/`."""
    parties = chemin.split("/")[:-1]
    return ["/".join(parties[: i + 1]) + "/" for i in range(len(parties))]


def dossiers_exclus(racine: Path, chemins: list[str]) -> dict[str, str]:
    """Pour chaque chemin sous un dossier que git exclut, le plus haut de ces dossiers (`a/b/`).

    Une exception `!<chemin>` ne lève pas un tel masque : git ne regarde pas dans un dossier exclu.
    Un seul appel à `git check-ignore`, pour tous les dossiers. Il passe `--no-index` : sans lui,
    un dossier qui contient déjà un fichier suivi compte comme suivi, et git ne le dit pas exclu.
    Les dossiers lui passent sans leur `/` final : git compare `env/*` à `env/` et l'y trouve, alors
    que ce motif n'exclut que le contenu. Ils existent, puisqu'ils contiennent un fichier listé, et
    git y reconnaît encore un motif de dossier (`env/`)."""
    dossiers = list(dict.fromkeys(d for chemin in chemins for d in _parents(chemin)))
    if not dossiers:
        return {}
    entree = b"".join(d.rstrip("/").encode("utf-8") + b"\0" for d in dossiers)
    r = _git(racine, "check-ignore", "--no-index", "-z", "--stdin", entree=entree)
    if r.returncode not in (0, 1):  # 1 : aucun dossier exclu
        erreur = r.stderr.decode("utf-8", errors="replace").strip()
        raise ErreurGit(f"git check-ignore --no-index -z --stdin : {erreur}")
    sortie = r.stdout.decode("utf-8", errors="replace").split("\0")
    exclus = {d + "/" for d in sortie if d}
    resultat = {}
    for chemin in chemins:
        haut = next((d for d in _parents(chemin) if d in exclus), None)
        if haut is not None:
            resultat[chemin] = haut
    return resultat


def remede(chemin: str, dossier: str | None) -> str:
    """L'exception à poser : sur le dossier exclu s'il y en a un, sinon sur le fichier. Un dossier
    de secrets se lève sans laisser entrer ce que la chaîne n'y lit pas."""
    if dossier is None:
        return f"Ajouter `!{chemin}` à ce fichier, puis l'indexer."
    admis = DOSSIERS_DE_SECRETS.get(dossier)
    if admis is None:
        return f"Ajouter `!{dossier}` à ce fichier, puis indexer le fichier."
    # Ancrées à la racine : `!secrets/`, sans `/` en tête, vaudrait à toute profondeur.
    exceptions = [
        f"`!/{dossier}`",
        f"`/{dossier}*`",
        *(f"`!/{dossier}{motif}`" for motif in admis),
    ]
    return (
        f"Ajouter à la fin de ce fichier {', '.join(exceptions[:-1])} et {exceptions[-1]}, dans cet "
        f"ordre, puis indexer le fichier : jamais `!/{dossier}` seul, qui laisserait entrer les "
        "secrets en clair."
    )


def secret_chiffre(chemin: str) -> bool:
    """Vrai si `chemin` est un secret chiffré que la chaîne lit (`SECRETS_CHIFFRES`)."""
    return any(
        chemin.count("/") == motif.count("/") and fnmatch.fnmatchcase(chemin, motif)
        for motif in SECRETS_CHIFFRES
    )


def constat(chemin: str) -> str:
    """Ce qu'est le fichier masqué, pour le message de refus."""
    if secret_chiffre(chemin):
        return "secret chiffré que la chaîne lit, masqué par le .gitignore"
    return "fichier du modèle masqué par le .gitignore"


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
        prog="masques.py",
        description="Refuse un fichier du modèle, ou un secret chiffré, masqué par le .gitignore.",
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
        masques = fichiers_masques(racine, chemins_examines(racine))
        dossiers = dossiers_exclus(racine, masques)
        lignes = [
            f"modele-projet : refusé — {constat(chemin)} : {chemin} "
            f"(règle {regle(racine, chemin)}). {remede(chemin, dossiers.get(chemin))}"
            for chemin in masques
        ]
    except ErreurGit as e:
        print(
            f"modele-projet : refusé — fichiers masqués invérifiables ({e}). {RENVOI}",
            file=sys.stderr,
        )
        return 1
    if lignes:
        print("\n".join(lignes), AUTRE_REMEDE, RENVOI, sep="\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
