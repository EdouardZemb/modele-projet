"""Porte de confidentialité : refuse les secrets et les identifiants privés.

Bibliothèque standard seule, Python 3.10 ou plus.

Règle d'or : la sortie ne contient JAMAIS la valeur trouvée ni le texte d'un motif privé,
seulement « emplacement — nom du motif ». Les journaux d'Actions d'un dépôt public sont publics.
Pour la même raison, un chemin de fichier qui correspond lui-même à un motif est masqué.

Usage (un seul mode) :
    confidentialite.py --index | --message FICHIER | --diff BASE | --texte FICHIER
                       | --fichiers CHEMIN...
    options : --motifs FICHIER, --exiger-prives

Retour : 0 rien trouvé, 1 au moins un constat, 64 erreur d'usage ou liste privée exigée absente.
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


@dataclass(frozen=True)
class Motif:
    nom: str
    expression: re.Pattern[str]


@dataclass(frozen=True)
class Constat:
    emplacement: str
    motif: str


def _g(nom: str, expression: str) -> Motif:
    return Motif(nom, re.compile(expression))


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
    _g("clé privée age", r"AGE-SECRET-KEY-1[0-9A-Z]{58}"),
    _g("clé privée PEM", r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    _g("jeton GitHub", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    _g("JWT", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    _g("jeton de tunnel Cloudflare", r"\beyJ[A-Za-z0-9+/=]{100,}"),
    _g("adresse de ping Healthchecks", r"hc-ping\.com/[A-Za-z0-9_-]{20,}"),
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
    env = os.environ.get("MOTIFS_INTERDITS")
    if env and env.strip():
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
                constats.append(Constat(emplacement, motif.nom))
    return constats


# --- sources de lignes -----------------------------------------------------------------------


class ErreurUsage(Exception):
    pass


def _git(*args: str) -> str:
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
    # Octets bruts, décodés ici : le mode texte de subprocess transformerait un retour chariot
    # isolé en saut de ligne et ferait disparaître du contenu ajouté.
    return r.stdout.decode("utf-8", errors="replace")


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


def _lignes_de_texte(emplacement: str, octets: bytes) -> Iterator[tuple[str, str]]:
    if b"\0" in octets[:8192]:
        return
    texte = octets.decode("utf-8", errors="replace")
    for i, ligne in enumerate(texte.split("\n"), start=1):
        yield f"{emplacement}:{i}", ligne.rstrip("\r")


def _lire_octets(chemin: str) -> bytes:
    try:
        return Path(chemin).read_bytes()
    except OSError:
        raise ErreurUsage("fichier illisible") from None


def _lignes_du_mode(args: argparse.Namespace) -> list[tuple[str, str]]:
    sortie: list[tuple[str, str]] = []
    if args.index:
        diff = _git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff", "--no-renames")
        sortie.extend(lignes_ajoutees(diff))
        noms = _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR", "--no-renames")
        sortie.extend((f"{c}:0", c) for c in _chemins(noms))
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
            base = ["diff", ARBRE_VIDE, "HEAD"]
            noms_base = [ARBRE_VIDE, "HEAD"]
        else:
            base = ["diff", f"{args.diff}...HEAD"]
            noms_base = [f"{args.diff}...HEAD"]
        diff = _git(*base, "-U0", "--no-color", "--no-ext-diff", "--no-renames")
        sortie.extend(lignes_ajoutees(diff))
        noms = _git("diff", *noms_base, "--name-only", "-z", "--diff-filter=ACMR", "--no-renames")
        sortie.extend((f"{c}:0", c) for c in _chemins(noms))
    elif args.message is not None:
        sortie.extend(_lignes_de_texte(args.message, _lire_octets(args.message)))
    elif args.texte is not None:
        sortie.extend(_lignes_de_texte(args.texte, _lire_octets(args.texte)))
    else:
        for rang, chemin in enumerate(args.fichiers, start=1):
            if not Path(chemin).is_file():
                raise ErreurUsage(f"chemin introuvable ou dossier (argument n°{rang})")
            sortie.append((f"{chemin}:0", chemin))
            sortie.extend(_lignes_de_texte(chemin, _lire_octets(chemin)))
    return sortie


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
    return p


def _masquer(emplacement: str, motifs: Sequence[Motif]) -> str:
    """Remplace le chemin par un texte neutre s'il correspond lui-même à un motif."""
    chemin, _, reste = emplacement.rpartition(":")
    if not chemin:
        chemin, reste = emplacement, ""
    if any(m.expression.search(chemin) for m in motifs):
        chemin = "<chemin masqué>"
    return f"{chemin}:{reste}" if reste else chemin


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
        lignes = _lignes_du_mode(args)
    except ErreurUsage as e:
        print(f"confidentialité : {e}", file=sys.stderr)
        return EXIT_USAGE
    constats = examiner(lignes, motifs)
    for constat in constats:
        print(
            f"confidentialité : {_masquer(constat.emplacement, motifs)} — {constat.motif}",
            file=sys.stderr,
        )
    if constats:
        print(f"confidentialité : {len(constats)} constat(s), refus.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
