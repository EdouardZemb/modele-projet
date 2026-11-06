"""La documentation de la racine : la licence et la carte, deux contrôles qui refusent en CI.

La licence. En nature `code`, `LICENSE` doit être présent à la racine, sous ce nom exact, et non
vide ; en nature `donnees`, il n'est pas exigé. La nature se lit comme la lit la porte de
confidentialité, par `nature()` de `confidentialite.py` : en CI, un dépôt public est de code, et un
dépôt privé prend la nature de sa branche par défaut, jamais celle de la PR ; hors CI, c'est le
`reglages.py` voisin, et `code` sans lui.

La carte. Chaque fichier `.md` de la racine, sauf `README.md`, doit être lié par un lien Markdown :
`CLAUDE.md` depuis `README.md`, un autre depuis `README.md` ou depuis la section « Ce qui fait foi »
de `CLAUDE.md` (jusqu'au titre suivant de même niveau). Un nom entre accents graves ne suffit pas :
on ne peut pas le suivre. `README.md` et `CLAUDE.md` doivent exister. La sortie dit le nombre de
fichiers vus, puis nomme chaque fichier non lié.

Ce qui est un lien : un lien en ligne, `[…](cible)` ou `![…](cible)`, avec un titre ou des
chevrons, son texte sur plusieurs lignes ou entre crochets au besoin, une image cliquable donnant
ses deux cibles ; une définition de référence, `[x]: cible`, sa cible au besoin sur la ligne
suivante, hors d'une note (`[^1]:`). Les blocs de code clôturés, le code en ligne et les
commentaires HTML sont retirés avant : GitHub n'y rend aucun lien. La cible perd son ancre et sa
requête, puis elle est décodée (`%20`) ; un `/` en tête part de la racine ; une cible avec un
schéma (`https:`, `mailto:`), une ancre seule, ou une cible qui sort de la racine n'est pas locale.
Les chemins se comparent à la casse près, comme sur GitHub ; un document est un fichier dont le
suffixe est `.md`, sans égard à la casse. Un texte en CRLF se lit comme en LF, et un octet qui
n'est pas de l'UTF-8 est remplacé, sans erreur.

La sortie ne cite jamais le contenu d'un fichier, seulement des chemins, chaque caractère de
contrôle remplacé par `?`.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : documentation.py [--racine DOSSIER]  (défaut : le dossier courant ; la CI le lance depuis
        la racine du dépôt)

Retour : 0 rien à signaler, 1 refus, 64 erreur d'usage.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

EXIT_USAGE = 64
PREFIXE = "documentation : "
CE_QUI_FAIT_FOI = "ce qui fait foi"
NON_LIE = "n'est lié ni par README.md ni par « Ce qui fait foi » de CLAUDE.md"

# --- ce qui est un lien ----------------------------------------------------------------------

_OUVERTURE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)$")
_FERMETURE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*$")
# Un commentaire HTML, ou un code en ligne : une suite d'accents graves, refermée par une suite de
# même longueur, sans franchir une ligne vide. Le plus à gauche l'emporte, comme sur GitHub.
_CODE_OU_COMMENTAIRE = re.compile(
    r"<!--.*?-->|(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n).)*?(?<!`)\1(?!`)", re.DOTALL
)
_ECHAPPEMENT = re.compile(r"\\(.)", re.DOTALL)
# Un caractère du texte d'un lien : ni crochet, ni barre oblique inverse nue, ni ligne vide.
_CAR = r"(?:[^\[\]\\\n]|\\.|\n(?![ \t]*\n))"


def _crochets(profondeur: int) -> str:
    """Un texte entre crochets, où d'autres crochets s'emboîtent sur `profondeur` niveaux."""
    if profondeur == 0:
        return rf"\[{_CAR}*\]"
    return rf"\[(?:{_CAR}|{_crochets(profondeur - 1)})*\]"


_DESTINATION = (
    r"\(\s*(?:<(?P<chevrons>[^<>\n]*)>"
    r"|(?P<brute>(?!<)(?:[^\s()\\]|\\.|\((?:[^\s()\\]|\\.)*\))+))"
    r"(?:\s+(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\)))?\s*\)"
)
_EN_LIGNE = re.compile(
    r"(?P<image>!?)(?P<texte>" + _crochets(3) + r")" + _DESTINATION
)
_REFERENCE = re.compile(
    r"^ {0,3}\[(?!\^)(?:[^\[\]\\\n]|\\.)+\]:[ \t]*(?:\n[ \t]*)?"
    r"(?:<(?P<chevrons>[^<>\n]*)>|(?P<brute>(?!<)\S+))",
    re.MULTILINE,
)
_SCHEMA = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_PONCTUATION_ECHAPPEE = re.compile(r"\\([!-/:-@\[-`{-~])")
_TITRE = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_FERMANTE = re.compile(r"(?:^|[ \t]+)#+$")


def _en_lf(texte: str) -> str:
    return texte.replace("\r\n", "\n").replace("\r", "\n")


def _hors_des_blocs(texte: str) -> str:
    """Le texte, chaque ligne d'un bloc de code clôturé vidée : le nombre de lignes ne change pas.
    Un bloc se ferme par une clôture du même caractère, au moins aussi longue ; sans elle, il court
    jusqu'à la fin. Une suite d'accents graves suivie d'un autre accent grave n'ouvre rien."""
    lignes = texte.split("\n")
    cloture: tuple[str, int] | None = None
    for i, ligne in enumerate(lignes):
        if cloture is None:
            ouverture = _OUVERTURE.match(ligne)
            if ouverture is None:
                continue
            suite = ouverture.group(1)
            if suite[0] == "`" and "`" in ouverture.group(2):
                continue
            cloture = (suite[0], len(suite))
        else:
            fermeture = _FERMETURE.match(ligne)
            suite = fermeture.group(1) if fermeture else ""
            if suite[:1] == cloture[0] and len(suite) >= cloture[1]:
                cloture = None
        lignes[i] = ""
    return "\n".join(lignes)


def _sans_code_ni_commentaire(texte: str) -> str:
    """Chaque code en ligne et chaque commentaire HTML remplacés par des `x`, ses fins de ligne
    gardées ; chaque crochet échappé (`\\[`) remplacé de même, une barre oblique inverse échappée
    comprise."""
    texte = _CODE_OU_COMMENTAIRE.sub(lambda m: re.sub(r"[^\n]", "x", m.group(0)), texte)
    return _ECHAPPEMENT.sub(lambda m: "xx" if m.group(1) in "[]" else m.group(0), texte)


def _en_ligne(texte: str, decalage: int = 0) -> list[tuple[int, str, bool]]:
    """Les liens en ligne d'un texte : (position de la cible, cible, image ?). Une image dans le
    texte d'un lien compte, et le lien aussi ; un lien dans le texte d'un lien l'emporte, et le
    lien qui le contient n'en est pas un."""
    trouves: list[tuple[int, str, bool]] = []
    for m in _EN_LIGNE.finditer(texte):
        image = m.group("image") == "!"
        interieurs = [] if image else _en_ligne(m.group("texte")[1:-1], m.start("texte") + 1)
        trouves.extend((decalage + p, c, i) for p, c, i in interieurs)
        if any(not est_image for _, _, est_image in interieurs):
            continue
        nom = "chevrons" if m.group("chevrons") is not None else "brute"
        if m.group(nom):
            trouves.append((decalage + m.start(nom), m.group(nom), image))
    return trouves


def liens(texte: str) -> list[str]:
    """Les cibles brutes des liens d'un texte, dans l'ordre où elles paraissent, sans leurs
    chevrons, hors des blocs de code clôturés, du code en ligne et des commentaires HTML."""
    texte = _sans_code_ni_commentaire(_hors_des_blocs(_en_lf(texte)))
    trouves = [(p, c) for p, c, _ in _en_ligne(texte)]
    for m in _REFERENCE.finditer(texte):
        nom = "chevrons" if m.group("chevrons") is not None else "brute"
        if m.group(nom):
            trouves.append((m.start(nom), m.group(nom)))
    return [cible for _, cible in sorted(trouves)]


def cible_locale(cible: str, racine: Path) -> str | None:
    """Le chemin, relatif à la racine et en `/`, sans `/` final (`.` pour la racine), que vise une
    cible ; `None` si elle n'est pas locale : un schéma, une ancre seule, ou une sortie de la
    racine, par `..` ou par un lien symbolique."""
    if _SCHEMA.match(cible) or cible.startswith("//"):
        return None
    chemin = cible.split("#", 1)[0].split("?", 1)[0]
    chemin = unquote(_PONCTUATION_ECHAPPEE.sub(r"\1", chemin), errors="replace")
    if not chemin:
        return None
    segments: list[str] = []
    for segment in chemin.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not segments:
                return None
            segments.pop()
        else:
            segments.append(segment)
    relatif = "/".join(segments) or "."
    try:
        base = racine.resolve()
        if not (base / relatif).resolve().is_relative_to(base):
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return relatif


def _affichable(texte: str) -> str:
    """Le texte, chaque caractère de contrôle (catégorie Unicode `Cc`) remplacé par `?`."""
    return "".join("?" if unicodedata.category(c) == "Cc" else c for c in texte)


# --- les contrôles ---------------------------------------------------------------------------


def _lire(racine: Path, nom: str, noms: list[str]) -> str | None:
    """Le texte d'un fichier de la racine, nommé à la casse près ; `None` s'il n'y est pas."""
    chemin = racine / nom
    if nom not in noms or not chemin.is_file():
        return None
    try:
        return _en_lf(chemin.read_text("utf-8", errors="replace"))
    except OSError:
        return None


def _section(texte: str, titre: str) -> str:
    """Les lignes des sections d'un titre donné (sans égard à la casse), jusqu'au titre suivant de
    même niveau ou d'un niveau supérieur ; hors des blocs de code clôturés."""
    lignes = texte.split("\n")
    niveaux: list[tuple[int, int, str]] = []
    for i, ligne in enumerate(_hors_des_blocs(texte).split("\n")):
        m = _TITRE.match(ligne)
        if m:
            contenu = _FERMANTE.sub("", m.group(2) or "").strip()
            niveaux.append((i, len(m.group(1)), contenu.casefold()))
    morceaux = []
    for k, (i, niveau, contenu) in enumerate(niveaux):
        if contenu != titre:
            continue
        fin = next((j for j, n, _ in niveaux[k + 1 :] if n <= niveau), len(lignes))
        morceaux.append("\n".join(lignes[i + 1 : fin]))
    return "\n".join(morceaux)


def _cibles(texte: str, racine: Path) -> set[str]:
    return {c for c in (cible_locale(lien, racine) for lien in liens(texte)) if c is not None}


def licence(racine: Path, nature: str) -> tuple[list[str], bool]:
    """La licence : (lignes, refus)."""
    if nature == "donnees":
        return ["licence : non exigée (nature donnees)"], False
    texte = _lire(racine, "LICENSE", os.listdir(racine))
    if texte is None or not texte.strip():
        return ["licence : LICENSE absent ou vide, exigé en nature code"], True
    return ["licence : LICENSE présent (nature code)"], False


def carte(racine: Path) -> tuple[list[str], bool]:
    """La carte de la racine : (lignes, refus). La première ligne dit le nombre de fichiers vus."""
    noms = os.listdir(racine)
    vus = sorted(
        nom
        for nom in noms
        if Path(nom).suffix.lower() == ".md" and nom != "README.md" and (racine / nom).is_file()
    )
    readme = _lire(racine, "README.md", noms)
    claude = _lire(racine, "CLAUDE.md", noms)
    absents = [
        f"carte : {nom} absent"
        for nom, texte in (("README.md", readme), ("CLAUDE.md", claude))
        if texte is None
    ]
    par_le_readme = _cibles(readme or "", racine)
    par_ce_qui_fait_foi = _cibles(_section(claude or "", CE_QUI_FAIT_FOI), racine)
    non_lies = []
    for nom in vus:
        if nom == "CLAUDE.md":
            if nom not in par_le_readme:
                non_lies.append("carte : CLAUDE.md n'est pas lié par README.md")
        elif nom not in par_le_readme and nom not in par_ce_qui_fait_foi:
            non_lies.append(f"carte : {_affichable(nom)} {NON_LIE}")
    tete = f"carte : {len(vus)} fichier{'s' if len(vus) > 1 else ''} .md à la racine"
    if non_lies:
        tete += f", {len(non_lies)} non lié{'s' if len(non_lies) > 1 else ''}"
    elif len(vus) == 1:
        tete += ", lié"
    elif len(vus) > 1:
        tete += ", tous liés"
    return [tete, *absents, *non_lies], bool(absents or non_lies)


# --- ligne de commande -----------------------------------------------------------------------


def _nature() -> str:
    """La nature, lue par la porte de confidentialité : importée ici seulement, à l'appel."""
    from confidentialite import nature

    return nature()


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):  # le message reçu pourrait citer l'entrée : on ne l'affiche pas
        self.exit(EXIT_USAGE, "documentation : usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(prog="documentation.py", description="La licence et la carte de la racine.")
    p.add_argument(
        "--racine", type=Path, default=Path("."), help="racine du dépôt (défaut : le dossier courant)"
    )
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    if not args.racine.is_dir():
        print("documentation : racine introuvable (voir --help)", file=sys.stderr)
        return EXIT_USAGE
    lignes_licence, refus_licence = licence(args.racine, _nature())
    lignes_carte, refus_carte = carte(args.racine)
    for ligne in (*lignes_licence, *lignes_carte):
        print(PREFIXE + ligne)
    if refus_licence or refus_carte:
        print(PREFIXE + "refus")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
