"""Installe le Compose de la cible : le binaire amont de `docker compose`, son empreinte vérifiée.

La cible a Compose 2.26.1, dans une construction de sa distribution, et le runner de la CI une
version plus récente. Comme le job `menage-cible` pour le moteur (LE-41), le job `fausse-app` fait
tourner ses épreuves sous la version de la cible, celle de la publication amont, que déclare
`tests/modele/docker-cible.env` avec l'empreinte de son binaire. Il lance ce script sous `sudo`,
avant les épreuves :

    sudo python3 -I tests/modele/installer_compose.py --source <adresse ou fichier> \\
      --empreinte <sha256> --destination /usr/local/lib/docker/cli-plugins/docker-compose

La source est une adresse `https://` ou `http://`, lue par `urllib`, ou un fichier. Son empreinte
SHA-256 doit valoir `--empreinte` : sinon, le script rend 1 et n'écrit rien, pas même le dossier.
Le binaire s'écrit en 755 par un fichier temporaire du même dossier, renommé ; le dossier, et ceux
qui lui manquent au-dessus, se créent au besoin, en 755, quel que soit le umask :
`/usr/local/lib/docker/cli-plugins` peut manquer sur le runner. Une source absente ou illisible, ou
une écriture impossible, rend 1 ; un usage faux, 64. Bibliothèque standard seule.
"""

import argparse
import hashlib
import http.client
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

USAGE = (
    "usage : python3 -I tests/modele/installer_compose.py --source <adresse ou fichier> "
    "--empreinte <sha256> --destination <chemin>"
)
DELAI = 60
_EMPREINTE = re.compile(r"[0-9a-f]{64}\Z")


class _Usage(Exception):
    """Un usage faux : le message dit lequel."""


class _Analyseur(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(message)


def lire(source):
    """Les octets de la source : une adresse `http(s)://`, lue par urllib, ou un fichier."""
    if source.startswith(("https://", "http://")):
        with urllib.request.urlopen(source, timeout=DELAI) as reponse:
            return reponse.read()
    return Path(source).read_bytes()


def creer_dossier(dossier):
    """Le dossier, et ceux qui lui manquent au-dessus, créés chacun en 755, quel que soit le umask."""
    manquants = []
    while not dossier.exists():
        manquants.append(dossier)
        dossier = dossier.parent
    for chemin in reversed(manquants):
        chemin.mkdir()
        os.chmod(chemin, 0o755)


def ecrire(destination, octets):
    """Les octets à la destination, en 755, par un fichier temporaire du même dossier, renommé."""
    creer_dossier(destination.parent)
    descripteur, temporaire = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}."
    )
    try:
        with os.fdopen(descripteur, "wb") as fichier:
            fichier.write(octets)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.chmod(temporaire, 0o755)
        os.replace(temporaire, destination)
    except BaseException:
        try:
            os.unlink(temporaire)
        except OSError:
            pass
        raise


def main(arguments):
    analyseur = _Analyseur(prog="installer_compose.py", add_help=False)
    analyseur.add_argument("--source", required=True)
    analyseur.add_argument("--empreinte", required=True)
    analyseur.add_argument("--destination", required=True)
    try:
        options = analyseur.parse_args(arguments)
        if not _EMPREINTE.match(options.empreinte):
            raise _Usage("--empreinte : 64 caractères hexadécimaux, en minuscules")
    except _Usage as erreur:
        print(f"installer_compose : {erreur}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 64
    try:
        octets = lire(options.source)
    except (OSError, ValueError, http.client.HTTPException) as erreur:
        print(
            f"installer_compose : source illisible ({options.source}) : {erreur} ; rien n'est écrit",
            file=sys.stderr,
        )
        return 1
    calculee = hashlib.sha256(octets).hexdigest()
    if calculee != options.empreinte:
        print(
            f"installer_compose : empreinte de {options.source} : {calculee}, attendue "
            f"{options.empreinte} ; rien n'est écrit",
            file=sys.stderr,
        )
        return 1
    destination = Path(options.destination)
    try:
        ecrire(destination, octets)
    except OSError as erreur:
        print(f"installer_compose : {destination} non écrit : {erreur}", file=sys.stderr)
        return 1
    print(f"installer_compose : {destination} écrit, en 755 (sha256 {calculee})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
