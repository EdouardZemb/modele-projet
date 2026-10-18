"""Garde de Claude Code (hook PreToolUse) : refuse ce qu'un agent ne doit pas faire seul.

Cinq choses sont refusées : un envoi vers la branche principale, tout contournement des hooks
git, la fusion d'une PR avant que tous ses contrôles soient verts, toute fusion quand le projet est
en mode `fusion : edouard`, et dans les deux modes l'envoi d'une étiquette et l'écriture d'une
publication. La vraie serrure est la protection de branche de GitHub ; ce garde évite seulement à
l'agent de s'y heurter, et de la chercher.

Le mode de fusion se lit sur GitHub (`.copier-answers.yml` de la branche principale), jamais dans la
copie locale ni dans `origin/<branche>`, qu'une session peut réécrire. Tout ce qui est illisible
vaut `edouard`.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : garde_claude.py [--branche NOM] [--fusion session|edouard]  (lit sur l'entrée standard le JSON du hook :
    {"tool_name": ..., "tool_input": {"command": ...}, "cwd": ...})

Outils surveillés : `Bash` et `Monitor` (lecture Bash), `PowerShell` (lecture PowerShell), et
tout autre outil qui porte une commande, un outil MCP par exemple (toutes les lectures). La
commande est le premier champ utilisable de `tool_input` parmi `command`, `cmd`, `input`,
`script` : un texte, ou une liste de textes (argv) jointe par des espaces. Pour `Bash`,
`PowerShell` et `Monitor`, un champ d'un autre type est refusé ; pour tout autre outil, il est
ignoré. Un outil sans champ utilisable passe sans que rien soit lancé.

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
# La lecture de chaque outil connu ; tout autre outil est lu de toutes les façons (None).
LECTURES = {"Bash": "Bash", "PowerShell": "PowerShell", "Monitor": "Bash"}
CHAMPS_COMMANDE = ("command", "cmd", "input", "script")
PROFONDEUR_MAX = 4
BUDGET = 20.0  # secondes, pour tous les sous-processus d'une invocation (délai du hook : 30)
_echeance: float | None = None

ASSIGNATION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECTIONS = set("<>")
PONCTUATION = ";|&()<>\n"
# Marque le texte d'une here-string (`<<<`) parmi les jetons : un octet nul ne vient jamais d'une
# commande. Pour un interprète, ce texte est une commande ; pour tout autre, c'est une donnée.
ICI = chr(0) + "<<<"
# Configuration git passée par l'environnement : elle prime sur le core.hooksPath du dépôt.
CONFIG_PAR_ENVIRONNEMENT = re.compile(r"git_config_(?:count|key_|parameters)", re.IGNORECASE)
REFUS_CONFIG_ENVIRONNEMENT = (
    "configuration git par l'environnement (GIT_CONFIG_…), qui peut détourner les hooks"
)
REFUS_HOOKS = "hooks git détournés (core.hooksPath)"
REFUS_AUTRE_DEPOT = "fusion dans un autre dépôt : contrôles invérifiables ici"
REFUS_MODE = "fusion réservée à Edouard (mode fusion : edouard)"
REFUS_ETIQUETTE = (
    "envoi d'une étiquette ou écriture de publication : à Edouard (étiquette ou publication)"
)
MODES_FUSION = ("session", "edouard")
REPONSE_SESSION = re.compile(r"^fusion:[ \t]*session[ \t]*\r?$", re.MULTILINE)
DESTINATION_ETIQUETTE = re.compile(r"^v[0-9]")
RELEASE_LECTURE = {"view", "list", "download"}

# Mots qui précèdent la vraie commande sans la changer.
PREFIXES = {
    "env", "command", "exec", "sudo", "time", "nohup", "builtin", "nice", "timeout", "!", "{", "}",
    "if", "then", "do", "else", "elif", "while", "until",
}  # fmt: skip
# Options de ces enveloppes qui prennent une valeur (`env -u NOM`, `timeout -s KILL`).
ENVELOPPES_AVEC_VALEUR = {
    "env": {"-u", "--unset"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
}
# Enveloppes dont le premier argument est une durée, pas la commande (`timeout 60 git …`).
ENVELOPPES_A_DUREE = {"timeout"}
# Interpréteurs dont un argument est lui-même une commande.
INTERPRETES = {
    "bash", "sh", "zsh", "dash", "ksh", "pwsh", "powershell", "cmd", "eval", "xargs", "wsl", "start",
    "start-process", "saps", "invoke-expression", "iex",
}  # fmt: skip
CHANGE_DOSSIER = {"cd", "pushd", "chdir", "set-location", "sl", "push-location"}
# Commandes qui effacent, déplacent ou renomment : Bash, cmd, PowerShell et ses alias.
EFFACE_OU_DEPLACE = {
    "rm", "rmdir", "del", "erase", "rd", "remove-item", "ri",
    "mv", "move", "move-item", "mi", "ren", "rename", "rename-item", "rni",
}  # fmt: skip
REFUS_GARDE_FOUS = "effacement ou déplacement des garde-fous (.githooks, scripts/modele)"
REFUS_IDENTIFIANTS = (
    "identifiants affichés (git credential, gh auth git-credential), "
    "qui permettraient de contourner le garde"
)


def _affiche_identifiants(commande: str, args: list[str]) -> bool:
    """`git credential fill`, ou `get` d'un assistant (`git credential-manager get`,
    `git-credential-store get`) : ils impriment l'identifiant enregistré."""
    if commande == "credential":
        return "fill" in args
    return commande.startswith(("credential-", "git-credential-")) and "get" in args


# Les commandes de `gh help` (gh 2.93) : de base, d'actions, d'alias et additionnelles. Tout autre
# premier mot est un alias ou une extension, qui pourrait masquer `gh pr merge`.
COMMANDES_GH = {
    "auth", "browse", "codespace", "gist", "issue", "org", "pr", "project", "release", "repo",
    "skill", "cache", "run", "workflow", "co", "agent-task", "alias", "api", "attestation",
    "completion", "config", "copilot", "extension", "gpg-key", "label", "licenses", "preview",
    "ruleset", "search", "secret", "ssh-key", "status", "variable", "help", "--version", "--help",
}  # fmt: skip

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
    r"|/releases"
)
API_FUSION = re.compile(r"/merge")
GRAPHQL_FUSION = re.compile(r"mergepullrequest|enablepullrequestautomerge|mergebranch")
GRAPHQL_ECRITURE = re.compile(
    r"mergepullrequest|enablepullrequestautomerge|updateref|createref|deleteref"
    r"|createcommitonbranch|branchprotectionrule|ruleset|mergebranch"
)


class Contexte:
    """Les rappels (branche courante, contrôles) et le dossier courant suivi au fil des `cd`."""

    def __init__(self, branche, branche_courante, checks_verts, outil=None, fusion=None):
        self.branche = branche
        self.outil = outil
        self._courante = branche_courante
        self._verts = checks_verts
        self._fusion = fusion if fusion is not None else (lambda dossier: "edouard")
        self.dossier: str | None = None
        self.depot_par_environnement = False  # la commande entière mentionne GH_REPO
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

    def fusion(self) -> str:
        """Le mode de fusion du dépôt visé (le dossier suivi par les `cd`), lu une fois par dossier.

        Tout ce qui n'est pas `session` vaut `edouard`."""
        cle = ("fusion", self.dossier)
        if cle not in self._memo:
            try:
                mode = self._fusion(self.dossier)
            except Exception:  # noqa: BLE001 - fail-closed
                mode = "edouard"
            self._memo[cle] = "session" if mode == "session" else "edouard"
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


def _segments_shlex(commande: str, echappement: bool, virgules: bool) -> list[list[str]]:
    lex = shlex.shlex(commande, posix=True, punctuation_chars=PONCTUATION)
    # PowerShell : `a,b` hors guillemets est une liste, chaque élément devient un argument.
    lex.whitespace = " \t\r" + ("," if virgules else "")
    lex.whitespace_split = True
    lex.commenters = ""
    if not echappement:
        lex.escape = ""
    segments: list[list[str]] = [[]]
    sauter = False
    chaine = False
    for jeton in lex:
        if _est_operateur(jeton):
            if any(c in jeton for c in ";|()\n") or not (set(jeton) & REDIRECTIONS):
                segments.append([])
            else:  # redirection : l'opérateur et sa cible ne sont pas des arguments
                sauter = True
                chaine = jeton == "<<<"
                if segments[-1] and segments[-1][-1].isdigit():
                    segments[-1].pop()
            continue
        if sauter:
            sauter = False
            if chaine:  # here-string : son texte est gardé, marqué, pour _motif_segment
                segments[-1].append(ICI + jeton)
            continue
        segments[-1].append(jeton)
    return [s for s in segments if s]


def _segments_grossiers(commande: str, virgules: bool) -> list[list[str]]:
    """Repli quand `shlex` échoue (guillemets mal fermés, syntaxe PowerShell) : espaces seuls."""
    morceaux = re.split(r"[;|&\n()<>]+", commande)
    segments = []
    for morceau in morceaux:
        jetons = morceau.replace("'", "").replace('"', "")
        if virgules:
            jetons = jetons.replace(",", " ")
        if jetons.split():
            segments.append(jetons.split())
    return segments


def _segments(commande: str, echappement: bool, virgules: bool = False) -> list[list[str]]:
    try:
        return _segments_shlex(commande, echappement, virgules)
    except ValueError:
        return _segments_grossiers(commande, virgules)


def _variantes(commande: str, outil: str | None = None) -> list[tuple[str, bool, bool]]:
    """Les lectures d'une commande selon l'outil : (texte, échappement, virgules).

    Bash : l'antislash échappe, l'apostrophe inversée est une substitution (donc un séparateur) ;
    une troisième lecture la garde, pour que le contenu d'un jeton entre guillemets qui en porte
    une soit réanalysé. PowerShell : l'antislash est un caractère ordinaire (chemins Windows),
    l'apostrophe inversée est l'échappement, supprimé avant l'analyse, et la virgule sépare les
    éléments d'une liste d'arguments. Outil inconnu : toutes les lectures, et on refuse si une
    seule refuse."""
    powershell = [(re.sub(r"`\r?\n", " ", commande).replace("`", ""), False, True)]
    if outil == "PowerShell":
        return powershell
    continue_sh = re.sub(r"\\\r?\n", "", commande)  # continuation : antislash puis saut
    textes = (continue_sh.replace("`", " "), continue_sh.replace("`", ";"), continue_sh)
    if outil == "Bash":
        return [(t, True, False) for t in textes]
    return [(t, e, False) for t in textes for e in (True, False)] + powershell


def _valeur_suivante(args: list[str], i: int) -> str:
    return args[i + 1] if i + 1 < len(args) else ""


def _motif_hooks_git(jeton: str) -> bool:
    return "hookspath" in jeton.lower()


def _vise_garde_fous(arg: str) -> bool:
    """Vrai si `arg` désigne `.githooks` ou `scripts/modele`, ou un chemin en dessous : séparateur
    `/` ou `\\`, préfixe quelconque (`./`, `C:\\x\\`), sans égard à la casse. `scripts` lui-même,
    qui contient `scripts/modele`, n'est visé qu'à la racine (`scripts`, `./scripts`), pas
    `apps/web/scripts`. Une option porteuse d'un chemin (`-Path:x`, `--x=y`) est lue par sa
    valeur."""
    valeur = re.sub(r"^-+[\w-]+[:=]", "", arg) if arg.startswith("-") else arg
    parties = [p for p in re.split(r"[\\/]", valeur.lower()) if p not in ("", ".")]
    for i, partie in enumerate(parties):
        if partie == ".githooks":
            return True
        if partie == "scripts" and parties[i + 1 : i + 2] == ["modele"]:
            return True
    absolu = bool(re.match(r"[\\/~]|[A-Za-z]:", valeur))
    return parties == ["scripts"] and not absolu


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
            if _abrege(nom, "--tags") or _abrege(nom, "--follow-tags"):
                return REFUS_ETIQUETTE
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
        if refspec == "tag":  # `git push origin tag <nom>` : syntaxe de refs/tags/<nom>
            return REFUS_ETIQUETTE
        dest = _destination(refspec)
        if dest.startswith(("refs/tags/", "tags/")) or DESTINATION_ETIQUETTE.match(dest):
            return REFUS_ETIQUETTE
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
    elif _motif_hooks_git(sous) or any(_motif_hooks_git(a) for a in reste):
        return REFUS_HOOKS
    if sous in ("rm", "mv") and any(_vise_garde_fous(a) for a in reste):
        return REFUS_GARDE_FOUS
    if _affiche_identifiants(sous.lower(), reste):
        return REFUS_IDENTIFIANTS
    if sous == "push":
        return _push(reste, chemin, ctx)
    return None


def _gh_merge(args: list[str], ctx: Contexte, depot: bool = False) -> str | None:
    pr = None
    if ctx.depot_par_environnement:
        return REFUS_AUTRE_DEPOT
    if ctx.fusion() != "session":
        return REFUS_MODE
    if any(a.split("=")[0] == "--admin" for a in args):
        return "fusion en contournant les règles de protection (--admin)"
    i = 0
    while i < len(args):
        a = args[i]
        nom = a.split("=")[0]
        if nom in ("-R", "--repo"):
            return REFUS_AUTRE_DEPOT
        if a.startswith("-"):
            if "=" not in a and nom in GH_MERGE_AVEC_VALEUR:
                i += 1
        elif pr is None:
            pr = a
        i += 1
    if depot or (pr is not None and re.match(r"(?i)[a-z][a-z0-9+.-]*://", pr)):
        return REFUS_AUTRE_DEPOT
    if pr is None and ctx.dossier is not None:
        return "fusion : préciser le numéro de PR après un changement de dossier"
    if not ctx.verts(pr):
        return "fusion avant que tous les contrôles soient verts"
    return None


def _graphql_opaque(args: list[str], texte: str) -> bool:
    return (
        "$" in texte
        or any(a.startswith("@") or "=@" in a for a in args)
        or any(a == "--input" or a.startswith("--input=") for a in args)
    )


def _gh_api(args: list[str], ctx: Contexte) -> str | None:
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
    # Les deux contrôles valent pour tout appel, quel que soit le point d'accès.
    texte = " ".join(args).lower()
    effective = (methode or ("POST" if champs else "GET")).upper()
    ecrit = effective != "GET" and point is not None
    fusion_graphql = "mutation" in texte and bool(GRAPHQL_FUSION.search(texte))
    # Corps qu'on ne lit pas ici (@fichier, --input, variables) : fusion possible.
    opaque = point is not None and "graphql" in point.lower() and _graphql_opaque(args, texte)
    fusion_rest = ecrit and bool(API_FUSION.search(point.lower()))
    if (fusion_graphql or opaque or fusion_rest) and ctx.depot_par_environnement:
        return REFUS_AUTRE_DEPOT  # GH_REPO quelque part dans la commande : cible invérifiable
    if (fusion_graphql or opaque) and ctx.fusion() != "session":
        return REFUS_MODE
    if ecrit and API_FUSION.search(point.lower()) and ctx.fusion() != "session":
        return REFUS_MODE
    if ecrit and "/releases" in point.lower():
        return REFUS_ETIQUETTE
    if "mutation" in texte and GRAPHQL_ECRITURE.search(texte):
        return refus
    if ecrit and API_ECRITURE.search(point.lower()):
        return refus
    return None


def _montre_le_jeton(arg: str) -> bool:
    """`--show-token`, `-t`, ou `-t` dans un groupe d'options courtes (`-at`)."""
    if arg.split("=")[0] == "--show-token":
        return True
    return bool(re.fullmatch(r"-[a-z]*t[a-z]*", arg))


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
    if mots and mots[0] not in COMMANDES_GH:
        return "commande gh inconnue (alias ou extension), qui pourrait masquer une fusion"
    if mots[:1] == ["alias"] and mots[1:2] in (["set"], ["import"]):
        return "alias gh pouvant masquer une fusion"
    if mots == ["auth", "token"]:
        return "jeton gh exposé (gh auth token), qui permettrait de contourner le garde"
    if mots == ["auth", "git-credential"]:
        return REFUS_IDENTIFIANTS
    if mots == ["auth", "status"] and any(_montre_le_jeton(a) for a in args):
        return (
            "jeton gh exposé (gh auth status --show-token), qui permettrait de contourner le garde"
        )
    if mots == ["pr", "merge"]:
        reste = args[positions[1] + 1 :]
        return _gh_merge(reste, ctx, depot)
    if mots[:1] == ["release"] and len(mots) > 1 and mots[1] not in RELEASE_LECTURE:
        return REFUS_ETIQUETTE
    if mots[:1] == ["api"]:
        return _gh_api(args[positions[0] + 1 :], ctx)
    return None


def _motif_segment(segment: list[str], ctx: Contexte, profondeur: int) -> str | None:
    ici = [jeton[len(ICI) :] for jeton in segment if jeton.startswith(ICI)]
    segment = [jeton for jeton in segment if not jeton.startswith(ICI)]
    # Une substitution `$(…)` ou `…` s'exécute même entre guillemets doubles (Bash), et "$(…)"
    # aussi en PowerShell : le contenu d'un tel jeton est réanalysé comme une commande.
    if profondeur < PROFONDEUR_MAX:
        for jeton in [*segment, *ici]:
            if "$(" in jeton or "`" in jeton:
                motif = _motif_commande(jeton.replace("`", ";"), ctx, profondeur + 1)
                if motif:
                    return motif
    if any(CONFIG_PAR_ENVIRONNEMENT.search(jeton) for jeton in segment):
        return REFUS_CONFIG_ENVIRONNEMENT
    i = 0
    enveloppe: str | None = None
    duree = False
    while i < len(segment):
        jeton = segment[i]
        if ASSIGNATION.match(jeton):
            pass
        elif _nom(jeton) in PREFIXES:
            enveloppe = _nom(jeton)
            duree = enveloppe in ENVELOPPES_A_DUREE
        elif enveloppe is not None and jeton.startswith("-"):
            if jeton in ENVELOPPES_AVEC_VALEUR.get(enveloppe, ()):
                i += 1
        elif duree:
            duree = False
        else:
            break
        i += 1
    if any(_motif_hooks_git(jeton) for jeton in segment[:i]):
        return REFUS_HOOKS
    if i >= len(segment):
        return None
    commande, reste = _nom(segment[i]), segment[i + 1 :]
    # core.hooksPath dans n'importe quel jeton : seul git (lectures, réparation exacte) en décide.
    if commande != "git" and any(_motif_hooks_git(jeton) for jeton in segment[i:]):
        return REFUS_HOOKS
    if commande in EFFACE_OU_DEPLACE and any(_vise_garde_fous(a) for a in reste):
        return REFUS_GARDE_FOUS
    if commande.startswith("git-credential-") and _affiche_identifiants(commande, reste):
        return REFUS_IDENTIFIANTS
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
        candidats = [*reste, " ".join(utiles)]
        if ici:  # `bash <<< 'cmd'` exécute le texte ; `xargs git commit <<< x` l'ajoute à la fin
            candidats += [*ici, " ".join([*utiles, *ici])]
        for candidat in candidats:
            if candidat.strip():
                motif = _motif_commande(candidat, ctx, profondeur + 1)
                if motif:
                    return motif
    return None


def _motif_commande(commande: str, ctx: Contexte, profondeur: int = 0) -> str | None:
    if CONFIG_PAR_ENVIRONNEMENT.search(commande):
        return REFUS_CONFIG_ENVIRONNEMENT
    lecture = ctx.outil if profondeur == 0 else None
    for texte, echappement, virgules in _variantes(commande, lecture):
        if CONFIG_PAR_ENVIRONNEMENT.search(texte):
            return REFUS_CONFIG_ENVIRONNEMENT
        for segment in _segments(texte, echappement, virgules):
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
    fusion: Callable[[str | None], str] = lambda dossier: "edouard",
) -> str | None:
    """La raison du refus de `commande`, ou None si elle est admise.

    `branche_courante` reçoit le chemin d'un `git -C <chemin>` (ou d'un `cd`), ou None.
    `checks_verts` reçoit l'argument de PR de `gh pr merge`, ou None.
    `outil` (« Bash » ou « PowerShell ») choisit la lecture ; None les essaie toutes.
    `fusion` reçoit le dossier suivi par les `cd` (None : celui du hook) et rend le mode
    (« session » ou « edouard »), appelé au plus une fois par dossier et seulement pour une fusion ; sans autre valeur que « session », toute fusion est refusée.
    Aucune exception ne sort d'ici : une commande qu'on ne sait pas analyser est refusée.
    """
    try:
        if CONFIG_PAR_ENVIRONNEMENT.search(commande):
            return REFUS_CONFIG_ENVIRONNEMENT
        # Le dossier suivi (`cd`) ne doit pas passer d'une lecture à l'autre.
        ctx = Contexte(branche, branche_courante, checks_verts, outil, fusion)
        ctx.depot_par_environnement = "gh_repo" in commande.lower()
        for texte, echappement, virgules in _variantes(commande, outil):
            if CONFIG_PAR_ENVIRONNEMENT.search(texte):
                return REFUS_CONFIG_ENVIRONNEMENT
            ctx.dossier = None
            for segment in _segments(texte, echappement, virgules):
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


def fusion_du_depot(branche: str, cwd: str | None) -> str:
    """Le mode de fusion du projet, lu sur GitHub : `.copier-answers.yml` à `ref=<branche>`.

    « session » seulement si une ligne vaut `fusion: session` ; « edouard » dans tous les autres
    cas (gh absent, code non nul, budget épuisé, ligne absente ou autre valeur)."""
    gh = shutil.which("gh")
    if gh is None:
        return "edouard"
    point = "repos/{owner}/{repo}/contents/.copier-answers.yml?ref=" + branche
    cmd = [gh, "api", "-H", "Accept: application/vnd.github.raw+json", point]
    r = _executer(cmd, cwd or ".")
    if r is None or r.returncode != 0:
        return "edouard"
    texte = r.stdout.decode("utf-8", errors="replace")
    return "session" if REPONSE_SESSION.search(texte) else "edouard"


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
    p.add_argument(
        "--fusion",
        choices=MODES_FUSION,
        help="mode de fusion, qui l'emporte sur la lecture de .copier-answers.yml sur GitHub",
    )
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


class CommandeIllisible(Exception):
    """Un champ de commande d'un type que le garde ne sait pas lire."""


def commande_de(entree: dict, stricte: bool = True) -> str | None:
    """La commande du premier champ utilisable de `tool_input` parmi CHAMPS_COMMANDE, ou None.

    Un texte est pris tel quel ; une liste de textes (un argv) est jointe par des espaces. Un
    champ d'un autre type lève CommandeIllisible en lecture stricte (Bash, PowerShell, Monitor,
    dont la commande doit être un texte) ; pour tout autre outil, il est ignoré, et le champ
    suivant est essayé : un outil MCP peut avoir un `input` structuré qui n'est pas une
    commande."""
    for champ in CHAMPS_COMMANDE:
        if champ not in entree:
            continue
        valeur = entree[champ]
        if isinstance(valeur, str):
            return valeur
        if isinstance(valeur, list) and all(isinstance(v, str) for v in valeur):
            return " ".join(valeur)
        if stricte:
            raise CommandeIllisible(champ)
    return None


def _executer_garde(args) -> int:
    global _echeance
    _echeance = time.monotonic() + BUDGET
    try:
        donnees = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
        outil = donnees["tool_name"]
        entree = donnees.get("tool_input") or {}
        cwd = donnees.get("cwd") or "."
        if not isinstance(outil, str) or not isinstance(entree, dict) or not isinstance(cwd, str):
            raise TypeError
    except (ValueError, KeyError, TypeError, AttributeError):
        print("garde-claude : entrée du hook illisible, rien vérifié.", file=sys.stderr)
        return 1
    try:
        commande = commande_de(entree, stricte=outil in LECTURES)
    except CommandeIllisible:
        _refuser("champ de commande d'un type inattendu, impossible à analyser")
        return 2
    if commande is None:  # un outil sans commande (lecture, recherche, MCP) : rien à lancer
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
        LECTURES.get(outil),
        (lambda dossier: args.fusion)
        if args.fusion
        else (lambda dossier: fusion_du_depot(branche, os.path.join(cwd, dossier) if dossier else cwd)),
    )
    if motif is None:
        return 0
    _refuser(motif)
    return 2


if __name__ == "__main__":
    sys.exit(main())
