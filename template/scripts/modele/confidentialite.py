"""Porte de confidentialité : refuse les secrets et les identifiants privés.

Bibliothèque standard seule, Python 3.10 ou plus.

Règle d'or : la sortie ne contient JAMAIS la valeur trouvée ni le texte d'un motif privé,
seulement « emplacement — nom du motif ». Les journaux d'Actions d'un dépôt public sont publics.
Pour la même raison, un chemin de fichier qui correspond lui-même à un motif est masqué.

Un fichier UTF-16 (avec BOM) est examiné comme du texte ; un autre binaire est signalé par une
ligne « fichier binaire non examiné », sans refus.

Dans un dépôt privé (`VISIBILITE = "prive"` dans reglages.py), un constat de la famille
« identification » (adresse, cible, nom de machine, motif privé) s'affiche de la même façon, sans
refuser ; un constat de la famille « secret » (clé, jeton) refuse toujours. En CI, DEPOT_PRIVE
(la visibilité réelle) l'emporte sur reglages.py ; --public force le mode public. Sans
reglages.py (le dépôt modèle lui-même) ou en `public`, tout constat refuse. Les erreurs d'usage et
l'absence d'une liste privée exigée refusent toujours (64).

Usage (un seul mode) :
    confidentialite.py --index | --message FICHIER | --diff BASE | --texte FICHIER
                       | --fichiers CHEMIN...
    options : --motifs FICHIER, --exiger-prives, --public

Retour : 0 rien trouvé (ou dépôt privé sans secret), 1 au moins un constat qui refuse, 64 erreur
d'usage ou liste privée exigée absente.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

ARBRE_VIDE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
LISTE_PAR_DEFAUT = ".config/modele-projet/motifs-interdits.txt"
EXIT_USAGE = 64


# Deux familles. Un secret (clé, jeton) refuse toujours, même dans un dépôt privé. Ce qui identifie
# (adresse, cible, nom de machine, motif privé) avertit seulement dans un dépôt privé.
SECRET = "secret"
IDENTIFICATION = "identification"


@dataclass(frozen=True)
class Motif:
    nom: str
    expression: re.Pattern[str]
    famille: str = IDENTIFICATION


@dataclass(frozen=True)
class Constat:
    emplacement: str
    motif: str
    famille: str = IDENTIFICATION


def _g(nom: str, expression: str, famille: str = IDENTIFICATION) -> Motif:
    return Motif(nom, re.compile(expression), famille)


MOTIFS_GENERIQUES: tuple[Motif, ...] = (
    _g(
        "adresse IP privée",
        r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b",
    ),
    _g("adresse Tailscale", r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}\b"),
    _g(
        "cible SSH",
        r"\bssh(?:\.exe)?\s+(?:-\S+\s+(?:[^\s@-][^\s@]*\s+)?)*(?!git@)[A-Za-z_][\w.-]*@[\w.-]+",
    ),
    _g("cible scp", r"\b[a-z_][\w.-]*@[a-z0-9][\w-]*:[~/]"),
    _g("cible scp à hôte pointé", r"\b[a-z_][\w.-]*@[a-z0-9][\w-]*(?:\.[\w-]+)+:[~/]"),
    _g("adresse IPv6 Tailscale", r"(?i)\bfd7a:115c:a1e0:"),
    _g("nom MagicDNS Tailscale", r"(?i)\b[a-z0-9-]+\.[a-z0-9-]+\.ts\.net\b"),
    _g("clé privée age", r"AGE-SECRET-KEY-1[0-9A-Z]{58}", SECRET),
    _g("clé privée PEM", r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----", SECRET),
    _g(
        "jeton GitHub",
        r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b",
        SECRET,
    ),
    _g("JWT", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", SECRET),
    _g("jeton de tunnel Cloudflare", r"\beyJ[A-Za-z0-9+/=]{100,}", SECRET),
    # l'adresse de ping porte la clé du contrôle : qui la connaît peut le faire mentir
    _g("adresse de ping Healthchecks", r"hc-ping\.com/[A-Za-z0-9_-]{20,}", SECRET),
)


def charger_motifs_prives(texte: str) -> tuple[Motif, ...]:
    """Lit la liste privée. Le message d'erreur ne cite jamais le texte d'un motif."""
    motifs: list[Motif] = []
    for brut in texte.replace("\r", "").split("\n"):
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        rang = len(motifs) + 1
        source = ligne[3:] if ligne.startswith("re:") else re.escape(ligne)
        try:
            expression = re.compile(source, re.IGNORECASE)
        except re.error:
            raise ValueError(f"motif privé n°{rang} invalide") from None
        motifs.append(Motif(f"motif privé n°{rang}", expression))
    return tuple(motifs)


def _lire_liste(chemin: Path) -> str:
    # utf-8-sig : le Bloc-notes de Windows peut écrire un BOM qui corromprait le premier motif.
    return chemin.read_text(encoding="utf-8-sig").replace("\r", "")


def source_motifs_prives(chemin: str | None) -> str | None:
    """Fichier --motifs, sinon variable MOTIFS_INTERDITS, sinon liste du poste, sinon None."""
    if chemin:
        return _lire_liste(Path(chemin))
    # Un secret posé depuis un fichier enregistré avec un BOM le garde en tête de la variable.
    env = (os.environ.get("MOTIFS_INTERDITS") or "").removeprefix("\ufeff")
    if env.strip():
        return env.replace("\r", "")
    defaut = Path.home() / LISTE_PAR_DEFAUT
    if defaut.is_file():
        return _lire_liste(defaut)
    return None


def examiner(lignes: Iterable[tuple[str, str]], motifs: Sequence[Motif]) -> list[Constat]:
    """Un constat par couple (ligne, motif) qui correspond. La valeur trouvée n'est pas gardée."""
    constats: list[Constat] = []
    for emplacement, texte in lignes:
        for motif in motifs:
            if motif.expression.search(texte):
                constats.append(Constat(emplacement, motif.nom, motif.famille))
    return constats


# --- sources de lignes -----------------------------------------------------------------------


class ErreurUsage(Exception):
    pass


def _git_octets(*args: str) -> bytes:
    try:
        r = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            check=False,
            capture_output=True,
        )
    except OSError:
        raise ErreurUsage("git est introuvable") from None
    if r.returncode != 0:
        raise ErreurUsage("échec de git (dépôt, base ou référence invalide)")
    return r.stdout


def _git(*args: str) -> str:
    # Octets bruts, décodés ici : le mode texte de subprocess transformerait un retour chariot
    # isolé en saut de ligne et ferait disparaître du contenu ajouté.
    return _git_octets(*args).decode("utf-8", errors="replace")


_ENTETE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def lignes_ajoutees(diff: str) -> Iterator[tuple[str, str]]:
    """Lit un diff -U0 : produit (chemin:n, texte) pour chaque ligne ajoutée."""
    chemin: str | None = None
    restant_ancien = restant_nouveau = 0
    numero = 0
    for ligne in diff.split("\n"):
        if restant_ancien > 0 or restant_nouveau > 0:
            if ligne.startswith("+"):
                if chemin is not None:
                    yield f"{chemin}:{numero}", ligne[1:].rstrip("\r")
                numero += 1
                restant_nouveau -= 1
            elif ligne.startswith("-"):
                restant_ancien -= 1
            # « \ No newline at end of file » : ni ancien ni nouveau
            continue
        if ligne.startswith("+++ "):
            cible = ligne[4:].split("\t")[0]
            if cible == "/dev/null":
                chemin = None
            else:
                if len(cible) > 1 and cible.startswith('"') and cible.endswith('"'):
                    cible = cible[1:-1]
                chemin = cible[2:] if cible[:2] in ("a/", "b/") else cible
            continue
        m = _ENTETE.match(ligne)
        if m:
            restant_ancien = int(m.group(1)) if m.group(1) is not None else 1
            numero = int(m.group(2))
            restant_nouveau = int(m.group(3)) if m.group(3) is not None else 1


def _chemins(sortie: str) -> list[str]:
    return [c for c in sortie.split("\0") if c]


# Options de chaque `git diff` : ni pager, ni outil externe, ni textconv (un textconv peut vider
# le contenu que la porte doit lire), ni détection de renommage.
DIFF = ("--no-color", "--no-ext-diff", "--no-textconv", "--no-renames")
BOM_UTF16 = (b"\xff\xfe", b"\xfe\xff")


def _texte(octets: bytes) -> str | None:
    """Le texte d'un contenu, ou None s'il est binaire (un octet nul dans les 8 premiers Kio).

    Un contenu qui commence par un BOM UTF-16 est décodé comme tel : c'est ce qu'écrivent par
    défaut `>` et `Out-File` dans Windows PowerShell 5.1."""
    if octets[:2] in BOM_UTF16:
        return octets.decode("utf-16", errors="replace")
    if b"\0" in octets[:8192]:
        return None
    return octets.decode("utf-8", errors="replace")


def _lignes_de_texte(
    emplacement: str, octets: bytes, non_examines: list[str]
) -> Iterator[tuple[str, str]]:
    """Chaque ligne d'un contenu ; un binaire n'en donne aucune et rejoint `non_examines`."""
    texte = _texte(octets)
    if texte is None:
        non_examines.append(emplacement)
        return
    for i, ligne in enumerate(texte.split("\n"), start=1):
        yield f"{emplacement}:{i}", ligne.rstrip("\r")


def _binaires(*plage: str) -> list[str]:
    """Les chemins ajoutés ou modifiés que git juge binaires (`-` `-` dans --numstat)."""
    sortie = _git("diff", *plage, "--numstat", "-z", "--diff-filter=ACMR", *DIFF)
    chemins = []
    for entree in sortie.split("\0"):
        champs = entree.split("\t", 2)
        if len(champs) == 3 and champs[0] == "-" and champs[1] == "-":
            chemins.append(champs[2])
    return chemins


def _lignes_des_binaires(
    plage: Sequence[str], revision: str, non_examines: list[str]
) -> Iterator[tuple[str, str]]:
    """Un fichier que git juge binaire n'a aucune ligne dans le diff : on lit l'objet lui-même
    (`:<chemin>` pour l'index, `HEAD:<chemin>` sinon). UTF-16 et texte marqué binaire par un
    attribut sont examinés en entier ; un vrai binaire est signalé, sans refus."""
    for chemin in _binaires(*plage):
        octets = _git_octets("show", "--no-textconv", f"{revision}:{chemin}")
        yield from _lignes_de_texte(chemin, octets, non_examines)


def _lire_octets(chemin: str) -> bytes:
    try:
        return Path(chemin).read_bytes()
    except OSError:
        raise ErreurUsage("fichier illisible") from None


def _lignes_du_mode(args: argparse.Namespace) -> tuple[list[tuple[str, str]], list[str]]:
    """Les lignes à examiner, et les fichiers binaires qui ne l'ont pas été."""
    sortie: list[tuple[str, str]] = []
    non_examines: list[str] = []
    if args.index:
        diff = _git("diff", "--cached", "-U0", *DIFF)
        sortie.extend(lignes_ajoutees(diff))
        noms = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", *DIFF)
        sortie.extend((f"{c}:0", c) for c in _chemins(noms))
        sortie.extend(_lignes_des_binaires(["--cached"], "", non_examines))
    elif args.diff is not None:
        if not args.diff.strip() or args.diff.startswith("-"):
            raise ErreurUsage("base de comparaison vide ou invalide")
        if set(args.diff) != {"0"}:
            _git(
                "rev-parse",
                "--verify",
                "--quiet",
                "--end-of-options",
                args.diff + "^" + "{" + "commit" + "}",
            )
        if set(args.diff) == {"0"}:
            plage = [ARBRE_VIDE, "HEAD"]
        else:
            plage = [f"{args.diff}...HEAD"]
        diff = _git("diff", *plage, "-U0", *DIFF)
        sortie.extend(lignes_ajoutees(diff))
        noms = _git("diff", *plage, "--name-only", "-z", "--diff-filter=ACMR", *DIFF)
        sortie.extend((f"{c}:0", c) for c in _chemins(noms))
        sortie.extend(_lignes_des_binaires(plage, "HEAD", non_examines))
    elif args.message is not None:
        sortie.extend(_lignes_de_texte(args.message, _lire_octets(args.message), non_examines))
    elif args.texte is not None:
        sortie.extend(_lignes_de_texte(args.texte, _lire_octets(args.texte), non_examines))
    else:
        for rang, chemin in enumerate(args.fichiers, start=1):
            if not Path(chemin).is_file():
                raise ErreurUsage(f"chemin introuvable ou dossier (argument n°{rang})")
            sortie.append((f"{chemin}:0", chemin))
            sortie.extend(_lignes_de_texte(chemin, _lire_octets(chemin), non_examines))
    return sortie, non_examines


# --- ligne de commande -----------------------------------------------------------------------


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):  # le message reçu pourrait citer l'entrée : on ne l'affiche pas
        self.exit(EXIT_USAGE, "confidentialité : usage invalide (voir --help)\n")


def _analyseur() -> argparse.ArgumentParser:
    p = _Analyseur(prog="confidentialite.py", description="Porte de confidentialité.")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--index", action="store_true", help="lignes ajoutées de l'index git")
    mode.add_argument("--message", metavar="FICHIER", help="message de commit")
    mode.add_argument("--diff", metavar="BASE", help="lignes ajoutées depuis BASE")
    mode.add_argument("--texte", metavar="FICHIER", help="un fichier de texte (ex. corps de PR)")
    mode.add_argument("--fichiers", metavar="CHEMIN", nargs="+", help="fichiers à examiner")
    p.add_argument("--motifs", metavar="FICHIER", help="liste de motifs privés")
    p.add_argument("--exiger-prives", action="store_true", help="échoue sans liste privée")
    p.add_argument(
        "--public",
        action="store_true",
        help="mode public quelle que soit la visibilité : tout constat refuse (avant un passage "
        "en public)",
    )
    return p


def _masquer_chemin(chemin: str, motifs: Sequence[Motif]) -> str:
    """Un texte neutre à la place du chemin, s'il correspond lui-même à un motif."""
    return "<chemin masqué>" if any(m.expression.search(chemin) for m in motifs) else chemin


def _masquer(emplacement: str, motifs: Sequence[Motif]) -> str:
    """Comme _masquer_chemin, pour un emplacement « chemin:ligne »."""
    chemin, _, reste = emplacement.rpartition(":")
    if not chemin:
        chemin, reste = emplacement, ""
    chemin = _masquer_chemin(chemin, motifs)
    return f"{chemin}:{reste}" if reste else chemin


def visibilite() -> str:
    """La visibilité qui s'applique : `prive` ou `public`.

    En CI, la variable DEPOT_PRIVE porte la visibilité réelle du dépôt
    (`github.event.repository.private`) et l'emporte : toute autre valeur que `true` donne
    `public`, quoi que dise reglages.py. Un dépôt passé public sans `copier update`, ou une PR qui
    réécrit VISIBILITE, ne s'ouvre donc pas. Sans la variable (le poste, les hooks), c'est la
    visibilité posée au rendu (`reglages.VISIBILITE`) qui décide. Sans réglages (le dépôt modèle
    lui-même), ou pour toute autre valeur que `prive` : `public`, où un constat refuse."""
    depot_prive = os.environ.get("DEPOT_PRIVE")
    if depot_prive is not None and depot_prive.strip().lower() != "true":
        return "public"
    try:
        from reglages import VISIBILITE
    except ImportError:
        return "public"
    return "prive" if VISIBILITE == "prive" else "public"


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        args = _analyseur().parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    try:
        liste = source_motifs_prives(args.motifs)
        prives = charger_motifs_prives(liste) if liste is not None else ()
    except ValueError as e:  # message déjà neutre : « motif privé n°k invalide »
        print(f"confidentialité : {e}", file=sys.stderr)
        return EXIT_USAGE
    except (OSError, UnicodeDecodeError):
        print("confidentialité : liste de motifs privés illisible", file=sys.stderr)
        return EXIT_USAGE
    if args.exiger_prives and not prives:
        print("confidentialité : liste de motifs privés exigée mais absente", file=sys.stderr)
        return EXIT_USAGE
    if liste is None:
        print("confidentialité : aucune liste privée, motifs génériques seuls", file=sys.stderr)
    motifs = (*MOTIFS_GENERIQUES, *prives)
    try:
        lignes, non_examines = _lignes_du_mode(args)
    except ErreurUsage as e:
        print(f"confidentialité : {e}", file=sys.stderr)
        return EXIT_USAGE
    for chemin in non_examines:  # la fin du silence, pas un refus
        print(
            f"confidentialité : fichier binaire non examiné : {_masquer_chemin(chemin, motifs)}",
            file=sys.stderr,
        )
    constats = examiner(lignes, motifs)
    for constat in constats:
        print(
            f"confidentialité : {_masquer(constat.emplacement, motifs)} — {constat.motif}",
            file=sys.stderr,
        )
    if not constats:
        return 0
    if not args.public and visibilite() == "prive":
        secrets = sum(1 for c in constats if c.famille == SECRET)
        if not secrets:  # un dépôt privé peut nommer son serveur : il est averti
            print(
                f"confidentialité : {len(constats)} constat(s), "
                "dépôt privé : avertissement, pas de refus",
                file=sys.stderr,
            )
            return 0
        print(
            f"confidentialité : {len(constats)} constat(s), refus : "
            f"{secrets} secret(s), qui refusent même dans un dépôt privé.",
            file=sys.stderr,
        )
        return 1
    print(f"confidentialité : {len(constats)} constat(s), refus.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
