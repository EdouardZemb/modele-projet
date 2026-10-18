"""Contrôle des secrets chiffrés par sops, sans les déchiffrer.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage :
    verifier_secrets.py [--racine DIR]

Pour chaque `*.env.enc` (hors `.git/`), on compare :
  - ses clés à celles de son `.cles` (même nom, suffixe `.env.enc` remplacé par `.cles`) ;
  - ses destinataires age à ceux de `.sops.yaml`.
Un `.cles` sans `.enc` avertit seulement : un projet neuf n'a pas encore ses secrets.
`reglages.SECRETS_EXIGES` (chemin du `.cles` -> clés exigées) ajoute les clés dont la mécanique a besoin.

Les messages nomment des chemins, des numéros de ligne et des noms de clé, jamais une valeur.

Retour : 0 conforme (avertissements compris), 1 refus, 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_REFUS = 1
EXIT_USAGE = 64

REGEX_CLE = re.compile(r"[A-Z][A-Z0-9_]*")
REGEX_NOM = re.compile(r"([^=\s]+)=")
REGEX_DESTINATAIRE = re.compile(r"sops_age__list_\d+__map_recipient")
REGEX_AGE = re.compile(r"age1[0-9a-z]{58}")

SUFFIXE_ENC = ".env.enc"
SUFFIXE_CLES = ".cles"


class Illisible(Exception):
    """Un fichier qu'on ne peut pas lire : porte le numéro de ligne, jamais son contenu."""

    def __init__(self, ligne: int, raison: str):
        super().__init__(raison)
        self.ligne = ligne
        self.raison = raison


@dataclass(frozen=True)
class Constat:
    niveau: str  # « refus » ou « avertissement »
    chemin: str
    message: str


def lire_cles(chemin: Path) -> list[str]:
    """Une clé par ligne ; lignes vides et « # » ignorées ; un doublon est une erreur."""
    cles: list[str] = []
    for numero, brut in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if not REGEX_CLE.fullmatch(ligne):
            raise Illisible(numero, "clé invalide (attendu : MAJUSCULES, chiffres et _)")
        if ligne in cles:
            raise Illisible(numero, f"clé en double : {ligne}")
        cles.append(ligne)
    return cles


def lire_chiffre(chemin: Path) -> tuple[set[str], set[str]]:
    """(clés, destinataires) d'un dotenv chiffré par sops. Aucune valeur n'est conservée."""
    cles: set[str] = set()
    destinataires: set[str] = set()
    for numero, brut in enumerate(chemin.read_text(encoding="utf-8").splitlines(), start=1):
        if not brut.strip():
            continue
        correspondance = REGEX_NOM.match(brut)
        if not correspondance:
            raise Illisible(numero, "ligne sans « = » : ce n'est pas un dotenv chiffré")
        nom = correspondance.group(1)
        if nom.startswith("sops_"):
            if REGEX_DESTINATAIRE.fullmatch(nom):
                destinataires.add(brut[correspondance.end() :].strip())
        else:
            cles.add(nom)
    return cles, destinataires


def destinataires_sops_yaml(racine: Path) -> set[str]:
    texte = (racine / ".sops.yaml").read_text(encoding="utf-8")
    return set(REGEX_AGE.findall(texte))


def _fichiers(racine: Path, motif: str) -> list[Path]:
    return sorted(p for p in racine.rglob(motif) if ".git" not in p.relative_to(racine).parts and p.is_file())


def _relatif(racine: Path, chemin: Path) -> str:
    return chemin.relative_to(racine).as_posix()


def _court(destinataire: str) -> str:
    return destinataire[:8] + "…"


def _noms(cles) -> str:
    return ", ".join(sorted(cles))


def verifier(racine: Path, exiges: dict[str, list[str]]) -> list[Constat]:
    racine = Path(racine)
    constats: list[Constat] = []
    enc = _fichiers(racine, "*" + SUFFIXE_ENC)
    cles_fichiers = _fichiers(racine, "*" + SUFFIXE_CLES)

    sops_yaml = racine / ".sops.yaml"
    attendus: set[str] | None = None
    if enc:
        if not sops_yaml.is_file():
            constats.append(Constat("refus", ".sops.yaml", "absent : les destinataires ne peuvent pas être contrôlés"))
        else:
            attendus = destinataires_sops_yaml(racine)
            if not attendus:
                constats.append(Constat("refus", ".sops.yaml", "aucun destinataire age"))
                attendus = None

    for chemin in enc:
        rel = _relatif(racine, chemin)
        voisin = chemin.with_name(chemin.name[: -len(SUFFIXE_ENC)] + SUFFIXE_CLES)
        try:
            cles_chiffrees, destinataires = lire_chiffre(chemin)
        except Illisible as e:
            constats.append(Constat("refus", f"{rel}:{e.ligne}", e.raison))
            continue
        if not voisin.is_file():
            constats.append(Constat("refus", rel, f"pas de {_relatif(racine, voisin)} : la liste des clés attendues manque"))
        else:
            try:
                declarees = set(lire_cles(voisin))
            except Illisible as e:
                constats.append(Constat("refus", f"{_relatif(racine, voisin)}:{e.ligne}", e.raison))
            else:
                if declarees - cles_chiffrees:
                    constats.append(Constat("refus", rel, f"clés manquantes : {_noms(declarees - cles_chiffrees)}"))
                if cles_chiffrees - declarees:
                    constats.append(Constat("refus", rel, f"clés en trop : {_noms(cles_chiffrees - declarees)}"))
        if attendus is not None:
            if attendus - destinataires:
                manquants = ", ".join(sorted(_court(d) for d in attendus - destinataires))
                constats.append(Constat("refus", rel, f"destinataires manquants : {manquants}"))
            if destinataires - attendus:
                en_trop = ", ".join(sorted(_court(d) for d in destinataires - attendus))
                constats.append(Constat("refus", rel, f"destinataires hors .sops.yaml : {en_trop}"))
        elif not destinataires:
            constats.append(Constat("refus", rel, "aucun destinataire age"))

    for chemin in cles_fichiers:
        voisin = chemin.with_name(chemin.name[: -len(SUFFIXE_CLES)] + SUFFIXE_ENC)
        if not voisin.is_file():
            constats.append(
                Constat("avertissement", _relatif(racine, chemin), f"pas de {voisin.name} : secrets pas encore posés")
            )

    for rel_cles, requises in sorted(exiges.items()):
        chemin = racine / rel_cles
        if not chemin.is_file():
            constats.append(Constat("refus", rel_cles, "absent, mais la mécanique du modèle en exige des clés"))
            continue
        try:
            presentes = set(lire_cles(chemin))
        except Illisible as e:
            constats.append(Constat("refus", f"{rel_cles}:{e.ligne}", e.raison))
            continue
        absentes = set(requises) - presentes
        if absentes:
            constats.append(Constat("refus", rel_cles, f"clés exigées par la mécanique du modèle : {_noms(absentes)}"))

    return constats


def _exiges_des_reglages() -> dict[str, list[str]]:
    try:
        import reglages  # type: ignore[import-not-found]
    except ImportError:
        return {}
    return dict(getattr(reglages, "SECRETS_EXIGES", {}))


def main(argv: list[str] | None = None, exiges: dict[str, list[str]] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Contrôle des secrets chiffrés par sops, sans déchiffrer.")
    analyseur.add_argument("--racine", default=".", help="racine du dépôt (défaut : le dossier courant)")
    try:
        args = analyseur.parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else 0
    racine = Path(args.racine)
    if not racine.is_dir():
        print(f"racine introuvable : {racine}", file=sys.stderr)
        return EXIT_USAGE
    if exiges is None:
        exiges = _exiges_des_reglages()
    constats = verifier(racine, exiges)
    for c in constats:
        print(f"{c.niveau} : {c.chemin} : {c.message}")
    return EXIT_REFUS if any(c.niveau == "refus" for c in constats) else 0


if __name__ == "__main__":
    # Les messages sont en UTF-8 quelle que soit la page de code de la console ou du tube.
    for flux in (sys.stdout, sys.stderr):
        flux.reconfigure(encoding="utf-8")
    sys.exit(main())
