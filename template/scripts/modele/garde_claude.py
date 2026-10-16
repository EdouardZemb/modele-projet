"""Garde de Claude Code (hook PreToolUse) : refuse ce qu'un agent ne doit pas faire seul.

Trois choses sont refusées : un envoi vers la branche principale, tout contournement des hooks
git, et la fusion d'une PR avant que tous ses contrôles soient verts. La vraie serrure est la
protection de branche de GitHub ; ce garde évite seulement à l'agent de s'y heurter, et de la
chercher.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : garde_claude.py [--branche NOM]  (lit sur l'entrée standard le JSON du hook :
    {"tool_name": ..., "tool_input": {"command": ...}, "cwd": ...})

Retour : 0 rien refusé, 2 commande refusée (Claude Code affiche l'erreur à l'agent),
1 entrée illisible (erreur non bloquante), 64 erreur d'usage (branche inconnue).

Principe : dans le doute, refuser. Une commande qu'on ne sait pas lire à fond est analysée
quand même, par un découpage plus grossier, jamais ignorée.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

EXIT_USAGE = 64
OUTILS = ("Bash", "PowerShell")
PROFONDEUR_MAX = 4
BUDGET = 20.0  # secondes, pour tous les sous-processus d'une invocation (délai du hook : 30)
_echeance: float | None = None

ASSIGNATION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECTIONS = set("<>")
PONCTUATION = ";|&()<>\n"

# Mots qui précèdent la vraie commande sans la changer.
PREFIXES = {
    "env", "command", "exec", "sudo", "time", "nohup", "builtin", "nice", "!", "{", "}",
    "if", "then", "do", "else", "elif", "while", "until",
}  # fmt: skip
# Interpréteurs dont un argument est lui-même une commande.
INTERPRETES = {
    "bash", "sh", "zsh", "dash", "ksh", "pwsh", "powershell", "cmd", "eval", "xargs", "wsl", "start",
}  # fmt: skip
CHANGE_DOSSIER = {"cd", "pushd", "chdir", "set-location", "sl", "push-location"}

SOUS_COMMANDES_HOOKS = {"commit", "merge", "push", "am", "rebase", "cherry-pick", "revert"}
LONGUES_AVEC_VALEUR = {
    "--message", "--file", "--author", "--date", "--template", "--reuse-message",
    "--reedit-message", "--fixup", "--squash", "--cleanup", "--trailer",
}  # fmt: skip
COURTES_AVEC_VALEUR = "mFCct"
PUSH_AVEC_VALEUR = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
GH_MERGE_AVEC_VALEUR = {
    "-b", "--body", "-t", "--subject", "-F", "--body-file", "-A", "--author-email",
    "--match-head-commit",
}  # fmt: skip
GH_API_AVEC_VALEUR = {
    "-H", "--header", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview",
}  # fmt: skip
GH_API_CHAMPS = {"-f", "-F", "--field", "--raw-field", "--input"}
API_ECRITURE = re.compile(
    r"/merge|git/refs|/contents/|/rulesets|/protection|git/(commits|trees|tags)|/update-branch"
)
GRAPHQL_ECRITURE = re.compile(
    r"mergepullrequest|enablepullrequestautomerge|updateref|createref|deleteref"
    r"|createcommitonbranch|branchprotectionrule|ruleset|mergebranch"
)


class Contexte:
    """Les rappels (branche courante, contrôles) et le dossier courant suivi au fil des `cd`."""

    def __init__(self, branche, branche_courante, checks_verts, outil=None):
        self.branche = branche
        self.outil = outil
        self._courante = branche_courante
        self._verts = checks_verts
        self.dossier: str | None = None
        self._memo: dict[tuple[str, str | None], Any] = {}

    def courante(self, chemin: str | None) -> str | None:
        cle = ("courante", chemin)
        if cle not in self._memo:
            self._memo[cle] = self._courante(chemin)
        return self._memo[cle]

    def verts(self, pr: str | None) -> bool:
        cle = ("verts", pr)
        if cle not in self._memo:
            self._memo[cle] = bool(self._verts(pr))
        return self._memo[cle]

    def chemin(self, option_c: str | None) -> str | None:
        if self.dossier is None:
            return option_c
        if option_c is None:
            return self.dossier
        return os.path.join(self.dossier, option_c)


def _nom(mot: str) -> str:
    """Nom de commande réduit : `/usr/bin/git`, `C:\\...\\git.exe` donnent `git`."""
    base = re.split(r"[\\/]", mot)[-1].lower()
    for suffixe in (".exe", ".cmd", ".bat"):
        if base.endswith(suffixe):
            return base[: -len(suffixe)]
    return base


def _est_operateur(jeton: str) -> bool:
    return bool(jeton) and all(c in PONCTUATION for c in jeton)


def _segments_shlex(commande: str, echappement: bool) -> list[list[str]]:
    lex = shlex.shlex(commande, posix=True, punctuation_chars=PONCTUATION)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    if not echappement:
        lex.escape = ""
    segments: list[list[str]] = [[]]
    sauter = False
    for jeton in lex:
        if _est_operateur(jeton):
            if any(c in jeton for c in ";|()\n") or not (set(jeton) & REDIRECTIONS):
                segments.append([])
            else:  # redirection : l'opérateur et sa cible ne sont pas des arguments
                sauter = True
                if segments[-1] and segments[-1][-1].isdigit():
                    segments[-1].pop()
            continue
        if sauter:
            sauter = False
            continue
        segments[-1].append(jeton)
    return [s for s in segments if s]


def _segments_grossiers(commande: str) -> list[list[str]]:
    """Repli quand `shlex` échoue (guillemets mal fermés, syntaxe PowerShell) : espaces seuls."""
    morceaux = re.split(r"[;|&\n()<>]+", commande)
    segments = []
    for morceau in morceaux:
        jetons = morceau.replace("'", "").replace('"', "").split()
        if jetons:
            segments.append(jetons)
    return segments


def _segments(commande: str, echappement: bool) -> list[list[str]]:
    try:
        return _segments_shlex(commande, echappement)
    except ValueError:
        return _segments_grossiers(commande)


def _variantes(commande: str, outil: str | None = None) -> list[tuple[str, bool]]:
    """Les lectures d'une commande selon l'outil.

    Bash : l'antislash échappe, l'apostrophe inversée est une substitution (donc un séparateur).
    PowerShell : l'antislash est un caractère ordinaire (chemins Windows), l'apostrophe inversée
    est l'échappement, supprimé avant l'analyse. Outil inconnu : toutes les lectures, et on
    refuse si une seule refuse."""
    powershell = [(re.sub(r"`\r?\n", " ", commande).replace("`", ""), False)]
    if outil == "PowerShell":
        return powershell
    continue_sh = re.sub(r"\\\r?\n", "", commande)  # continuation : antislash puis saut
    textes = (continue_sh.replace("`", " "), continue_sh.replace("`", ";"))
    if outil == "Bash":
        return [(t, True) for t in textes]
    return [(t, e) for t in textes for e in (True, False)] + powershell


def _valeur_suivante(args: list[str], i: int) -> str:
    return args[i + 1] if i + 1 < len(args) else ""


def _motif_hooks_git(jeton: str) -> bool:
    return "hookspath" in jeton.lower()


def _options_git(args: list[str]) -> tuple[str | None, int, str | None]:
    """Lit les options globales de git. Rend (chemin de -C, indice de la sous-commande, refus)."""
    chemin = None
    i = 0
    while i < len(args) and args[i].startswith("-"):
        a = args[i]
        if _motif_hooks_git(a):
            return chemin, i, "hooks git détournés (core.hooksPath)"
        if a == "-C":
            chemin = _valeur_suivante(args, i) or chemin
            i += 2
        elif a == "-c":
            valeur = _valeur_suivante(args, i)
            if _motif_hooks_git(valeur):
                return chemin, i, "hooks git détournés (core.hooksPath)"
            if valeur.lower().startswith("alias."):
                return chemin, i, "alias git pouvant masquer un push vers la branche principale"
            i += 2
        elif a in ("--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"):
            if _motif_hooks_git(_valeur_suivante(args, i)):
                return chemin, i, "hooks git détournés (core.hooksPath)"
            i += 2
        else:
            i += 1
    return chemin, i, None


def _sans_hooks(sous: str, args: list[str]) -> bool:
    """Vrai si les options de `args` demandent d'ignorer les hooks (--no-verify, -n de commit)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            return False
        if a.startswith("--"):
            nom = a.split("=")[0]
            if len(nom) >= len("--no-ve") and "--no-verify".startswith(nom):
                return True
            if "=" not in a and nom in LONGUES_AVEC_VALEUR:
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for k, c in enumerate(a[1:], start=1):
                if c in COURTES_AVEC_VALEUR:
                    if k == len(a) - 1:
                        i += 1
                    break
                if c == "n" and sous == "commit":
                    return True
        i += 1
    return False


def _destination(refspec: str) -> str:
    r = refspec.lstrip("+")
    dest = r.rsplit(":", 1)[1] if ":" in r else r
    if not dest:
        dest = r.rsplit(":", 1)[0]
    for prefixe in ("refs/heads/", "heads/"):
        if dest.startswith(prefixe):
            return dest[len(prefixe) :]
    return dest


def _abrege(nom: str, long: str) -> bool:
    """git accepte une abréviation non ambiguë d'une option longue : `--al` pour `--all`."""
    return len(nom) >= 4 and nom.startswith("--") and long.startswith(nom)


def _push(args: list[str], chemin: str | None, ctx: Contexte) -> str | None:
    refspecs: list[str] = []
    remote = None
    i = 0
    fin_options = False
    while i < len(args):
        a = args[i]
        if not fin_options and a == "--":
            fin_options = True
        elif not fin_options and a.startswith("-") and a != "-":
            nom = a.split("=")[0]
            if _abrege(nom, "--all") or _abrege(nom, "--mirror"):
                return "push de toutes les branches (--all, --mirror), main comprise"
            if _abrege(nom, "--repo"):
                remote = a  # --repo donne le remote : tout argument positionnel est un refspec
            if "=" not in a and (
                nom in PUSH_AVEC_VALEUR or any(_abrege(nom, longue) for longue in PUSH_AVEC_VALEUR)
            ):
                i += 1
                if _abrege(nom, "--repo"):
                    remote = a
        elif remote is None:
            remote = a
        else:
            refspecs.append(a)
        i += 1
    refus = f"push vers {ctx.branche}"
    for refspec in refspecs:
        dest = _destination(refspec)
        if dest == ctx.branche:
            return refus
        if dest in ("HEAD", "@"):
            courante = ctx.courante(chemin)
            if courante is None or courante == ctx.branche:
                return refus
        elif re.search(r"[*?\[]", dest) and not dest.startswith("refs/tags/"):
            return refus
    if not refspecs:
        courante = ctx.courante(chemin)
        if courante is None or courante == ctx.branche:
            return refus
    return None


def _git(args: list[str], ctx: Contexte) -> str | None:
    option_c, i, refus = _options_git(args)
    if refus:
        return refus
    if i >= len(args):
        return None
    sous, reste = args[i], args[i + 1 :]
    chemin = ctx.chemin(option_c)
    if sous in SOUS_COMMANDES_HOOKS and _sans_hooks(sous, reste):
        return "commande git sans hooks (--no-verify)"
    if sous == "config":
        lecture = any(a in ("--get", "--get-all", "--list", "-l") for a in reste)
        options = [a for a in reste if a.startswith("-")]
        positions = [a for a in reste if not a.startswith("-")]
        repare = (  # la réparation prescrite par la méthode : exactement cette valeur
            set(options) <= {"--local", "--worktree"}
            and len(positions) == 2
            and positions[0].lower() == "core.hookspath"
            and positions[1] == ".githooks"
        )
        if any(_motif_hooks_git(a) for a in reste) and not lecture and not repare:
            return "hooks git détournés (core.hooksPath)"
        if any(a.lower().startswith("alias.") for a in reste) and not lecture:
            return "alias git pouvant masquer un push vers la branche principale"
    if sous == "push":
        return _push(reste, chemin, ctx)
    return None


def _gh_merge(args: list[str], ctx: Contexte, depot: bool = False) -> str | None:
    pr = None
    if any(a.split("=")[0] == "--admin" for a in args):
        return "fusion en contournant les règles de protection (--admin)"
    i = 0
    while i < len(args):
        a = args[i]
        nom = a.split("=")[0]
        if nom in ("-R", "--repo"):
            return "fusion dans un autre dépôt : contrôles invérifiables ici"
        if a.startswith("-"):
            if "=" not in a and nom in GH_MERGE_AVEC_VALEUR:
                i += 1
        elif pr is None:
            pr = a
        i += 1
    if depot:
        return "fusion dans un autre dépôt : contrôles invérifiables ici"
    if pr is None and ctx.dossier is not None:
        return "fusion : préciser le numéro de PR après un changement de dossier"
    if not ctx.verts(pr):
        return "fusion avant que tous les contrôles soient verts"
    return None


def _gh_api(args: list[str]) -> str | None:
    refus = "fusion ou écriture de branche par l'API GitHub, qui contourne la PR"
    methode = None
    champs = False
    point = None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-X", "--method"):
            methode = _valeur_suivante(args, i)
            i += 1
        elif a.startswith("--method="):
            methode = a.split("=", 1)[1]
        elif a.startswith("-X") and len(a) > 2:
            methode = a[2:]
        elif a in GH_API_CHAMPS:
            champs = True
            i += 1
        elif a.startswith(("-f", "-F", "--field=", "--raw-field=", "--input=")):
            champs = True
        elif a in GH_API_AVEC_VALEUR:
            i += 1
        elif not a.startswith("-") and point is None:
            point = a
        i += 1
    texte = " ".join(args).lower()  # les deux contrôles valent pour tout appel, quel que soit le point
    if "mutation" in texte and GRAPHQL_ECRITURE.search(texte):
        return refus
    effective = (methode or ("POST" if champs else "GET")).upper()
    if effective != "GET" and point is not None and API_ECRITURE.search(point.lower()):
        return refus
    return None


def _gh(args: list[str], ctx: Contexte) -> str | None:
    positions = []
    depot = False
    i = 0
    while i < len(args) and len(positions) < 2:
        a = args[i]
        if a.split("=")[0] in ("-R", "--repo"):
            depot = True
            i += 1 if "=" in a else 2
            continue
        if not a.startswith("-"):
            positions.append(i)
        i += 1
    mots = [args[k] for k in positions]
    if mots == ["pr", "merge"]:
        reste = args[positions[1] + 1 :]
        return _gh_merge(reste, ctx, depot)
    if mots[:1] == ["api"]:
        return _gh_api(args[positions[0] + 1 :])
    return None


def _motif_segment(segment: list[str], ctx: Contexte, profondeur: int) -> str | None:
    i = 0
    enveloppe = False
    while i < len(segment):
        jeton = segment[i]
        if ASSIGNATION.match(jeton):
            if _motif_hooks_git(jeton):
                return "hooks git détournés (core.hooksPath)"
        elif _nom(jeton) in PREFIXES:
            enveloppe = True
        elif not (enveloppe and jeton.startswith("-")):
            break
        i += 1
    if i >= len(segment):
        return None
    commande, reste = _nom(segment[i]), segment[i + 1 :]
    if commande in CHANGE_DOSSIER:
        cible = next((a for a in reste if not a.startswith("-") or a == "-"), None)
        if cible is not None and cible != "-":
            ctx.dossier = ctx.chemin(cible) if ctx.dossier else cible
        return None
    if commande == "git":
        return _git(reste, ctx)
    if commande == "gh":
        return _gh(reste, ctx)
    if commande in INTERPRETES and profondeur < PROFONDEUR_MAX:
        utiles = list(reste)
        while utiles and (utiles[0].startswith("-") or utiles[0].startswith("/")):
            utiles.pop(0)
        for candidat in [*reste, " ".join(utiles)]:
            if candidat.strip():
                motif = _motif_commande(candidat, ctx, profondeur + 1)
                if motif:
                    return motif
    return None


def _motif_commande(commande: str, ctx: Contexte, profondeur: int = 0) -> str | None:
    for texte, echappement in _variantes(commande, ctx.outil if profondeur == 0 else None):
        for segment in _segments(texte, echappement):
            motif = _motif_segment(segment, ctx, profondeur)
            if motif:
                return motif
    return None


def motif_de_refus(
    commande: str,
    branche: str,
    branche_courante: Callable[[str | None], str | None],
    checks_verts: Callable[[str | None], bool],
    outil: str | None = None,
) -> str | None:
    """La raison du refus de `commande`, ou None si elle est admise.

    `branche_courante` reçoit le chemin d'un `git -C <chemin>` (ou d'un `cd`), ou None.
    `checks_verts` reçoit l'argument de PR de `gh pr merge`, ou None.
    `outil` (« Bash » ou « PowerShell ») choisit la lecture ; None les essaie toutes.
    Aucune exception ne sort d'ici : une commande qu'on ne sait pas analyser est refusée.
    """
    try:
        # Le dossier suivi (`cd`) ne doit pas passer d'une lecture à l'autre.
        ctx = Contexte(branche, branche_courante, checks_verts, outil)
        for texte, echappement in _variantes(commande, outil):
            ctx.dossier = None
            for segment in _segments(texte, echappement):
                motif = _motif_segment(segment, ctx, 0)
                if motif:
                    return motif
    except Exception:  # noqa: BLE001 - fail-closed : jamais d'exception vers l'appelant
        return "commande impossible à analyser"
    return None


def _executer(cmd: list[str], cwd: str) -> subprocess.CompletedProcess | None:
    """Lance `cmd` dans le budget de temps restant ; budget épuisé ou erreur : None."""
    delai = BUDGET if _echeance is None else _echeance - time.monotonic()
    if delai <= 0:
        return None
    try:
        return subprocess.run(
            cmd,
            check=False,
            cwd=cwd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=delai,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def checks_verts_gh(pr: str | None, cwd: str) -> bool:
    """Vrai si et seulement si la PR a des contrôles et qu'ils sont tous `pass` ou `skipping`."""
    gh = shutil.which("gh")
    if gh is None or (pr is not None and pr.startswith("-")):
        return False
    cmd = [gh, "pr", "checks", *([pr] if pr else []), "--json", "bucket"]
    r = _executer(cmd, cwd)
    if r is None or r.returncode != 0:
        return False
    try:
        controles = json.loads(r.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return False
    if not isinstance(controles, list) or not controles:
        return False
    return all(isinstance(c, dict) and c.get("bucket") in ("pass", "skipping") for c in controles)


def branche_courante_git(chemin: str | None, cwd: str) -> str | None:
    """La branche courante (`git rev-parse --abbrev-ref HEAD`), ou None si illisible."""
    cmd = ["git", *(["-C", chemin] if chemin else []), "rev-parse", "--abbrev-ref", "HEAD"]
    r = _executer(cmd, cwd)
    if r is None or r.returncode != 0:
        return None
    nom = r.stdout.decode("utf-8", errors="replace").strip()
    return nom or None


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):
        self.exit(EXIT_USAGE, "garde-claude : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(prog="garde_claude.py", description="Garde PreToolUse de Claude Code.")
    p.add_argument("--branche", help="branche principale (défaut : reglages.BRANCHE_PRINCIPALE)")
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    try:
        return _executer_garde(args)
    except Exception:  # noqa: BLE001 - fail-closed : pas de trace, un refus lisible
        _refuser("commande impossible à analyser")
        return 2
    finally:
        global _echeance
        _echeance = None


def _refuser(motif: str) -> None:
    print(
        f"modele-projet : refusé — {motif}. Voir docs/modele/methode.md, « Les garde-fous ».",
        file=sys.stderr,
    )


def _executer_garde(args) -> int:
    global _echeance
    _echeance = time.monotonic() + BUDGET
    try:
        donnees = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
        outil = donnees["tool_name"]
        entree = donnees.get("tool_input") or {}
        commande = entree.get("command", "") if outil in OUTILS else ""
        cwd = donnees.get("cwd") or "."
        if not isinstance(outil, str) or not isinstance(commande, str) or not isinstance(cwd, str):
            raise TypeError
    except (ValueError, KeyError, TypeError, AttributeError):
        print("garde-claude : entrée du hook illisible, rien vérifié.", file=sys.stderr)
        return 1
    if outil not in OUTILS:
        return 0
    branche = args.branche
    if branche is None:
        try:
            from reglages import BRANCHE_PRINCIPALE as branche
        except ImportError:
            print("garde-claude : réglages introuvables et aucun --branche donné.", file=sys.stderr)
            return EXIT_USAGE
    motif = motif_de_refus(
        commande,
        branche,
        lambda chemin: branche_courante_git(chemin, cwd),
        lambda pr: checks_verts_gh(pr, cwd),
        outil,
    )
    if motif is None:
        return 0
    _refuser(motif)
    return 2


if __name__ == "__main__":
    sys.exit(main())
