"""La fausse app du modèle : le contrat de la cible `serveur` (spec §6.1, M-0006 § 5), en quelques
lignes.

À copier dans un projet <nom> : remplacer FAUSSE_APP_ par son préfixe (<NOM>_, tirets en _).
FAUSSE_APP_ est celui du projet que rend la CI du modèle (nom=fausse-app) ; compose ne passe à l'app
que les variables du préfixe de son projet.

Elle écoute sur $PORT (défaut 3000), sur $HOST (défaut 0.0.0.0). Sa route de santé, /api/sante,
rend {statut, environnement, version, revision, configuration} : statut `ok` tant que ses données
(/donnees/MARQUE) sont là, sinon un 503 avec {statut: "ko"}. L'environnement, la version et la
révision viennent de FAUSSE_APP_ENV, FAUSSE_APP_VERSION et FAUSSE_APP_REVISION ; le Dockerfile
pose la révision, depuis l'argument de construction REVISION.

Elle sert aussi ce que le relais du staging marque (lot 19) : une page, `/` (son titre, le lien de
son manifeste et celui de son icône), son manifeste, `/manifest.webmanifest`, et son icône,
`/icone.png`, un PNG de 16 x 16 tout #0b7f8f, écrit par zlib. Tout autre chemin rend 404.

Ses données, au premier démarrage : sur un /donnees absent ou vide, l'app sème ce que le Dockerfile
sème dans l'image (SEMIS), comme une vraie app crée son stockage. Sur le serveur, /donnees est un
dossier de l'hôte, vide au premier déploiement, monté par-dessus celui de l'image. Un /donnees qui
n'est pas vide n'est jamais touché : sans MARQUE, il reste non conforme. Un semis impossible refuse
de démarrer.

L'instance (M-0006, § 5) : sa configuration dans /config, son contenu dans /contenu, deux montages
en lecture seule. Chacun porte sa version de schéma, dans son fichier `version`. Au démarrage, l'app
lit les deux versions et refuse une version qu'elle ne connaît pas. Un /config ou un /contenu
absent ou vide la fait servir son exemple, celui que l'image embarque (exemple/ et
exemple-contenu/, à côté de ce fichier), sauf en prod, où elle refuse de démarrer : pas de repli
sur l'exemple. Le champ `configuration` de la santé dit `montee` quand /config est monté et non
vide, `exemple` sinon. Un refus de démarrer sort en code 1, le message sur stderr.

FAUSSE_APP_DONNEES, FAUSSE_APP_CONFIG et FAUSSE_APP_CONTENU remplacent /donnees, /config et
/contenu (pour les tests). Bibliothèque standard seule.
"""

import json
import os
import struct
import sys
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHEMIN_SANTE = "/api/sante"
# Les versions de schéma de la configuration et du contenu que cette image sait lire.
VERSIONS_CONNUES = {"1"}
ICI = Path(__file__).resolve().parent
EXEMPLE = ICI / "exemple"
EXEMPLE_CONTENU = ICI / "exemple-contenu"
# Ce que l'app sème dans un dossier de données vide : ce que le Dockerfile sème dans l'image.
SEMIS = {
    "MARQUE": "fausse-app\n",
    "notes/premiere.txt": "une note\n",
    ".cachee": "un fichier caché\n",
}


def bloc_png(nom, donnees):
    """Un bloc PNG : sa longueur, son nom, ses données et son CRC, calculé sur le nom et les
    données."""
    crc = zlib.crc32(nom + donnees) & 0xFFFFFFFF
    return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", crc)


def icone(cote=16, couleur=(0x0B, 0x7F, 0x8F)):
    """Un PNG de `cote` x `cote`, profondeur 8, en RVBA (type 6), tout `couleur`, opaque : chaque
    ligne, son octet de filtre (0), puis ses pixels."""
    ligne = b"\x00" + bytes((*couleur, 0xFF)) * cote
    entete = struct.pack(">IIBBBBB", cote, cote, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloc_png(b"IHDR", entete)
        + bloc_png(b"IDAT", zlib.compress(ligne * cote, 9))
        + bloc_png(b"IEND", b"")
    )


# Ce que le relais du staging marque : la page, le manifeste et l'icône, chacun avec son type.
PAGE = (
    b"<!doctype html>\n"
    b'<html lang="fr">\n'
    b"<head>\n"
    b'<meta charset="utf-8">\n'
    b"<title>fausse app</title>\n"
    b'<link rel="manifest" href="/manifest.webmanifest">\n'
    b'<link rel="icon" href="/icone.png">\n'
    b"</head>\n"
    b"<body>\n"
    b"<p>fausse app</p>\n"
    b"</body>\n"
    b"</html>\n"
)
MANIFESTE = json.dumps(
    {
        "name": "fausse app",
        "short_name": "fausse",
        "icons": [{"src": "/icone.png", "sizes": "16x16", "type": "image/png"}],
    }
).encode("utf-8")
RESSOURCES = {
    "/": ("text/html; charset=utf-8", PAGE),
    "/manifest.webmanifest": ("application/manifest+json", MANIFESTE),
    "/icone.png": ("image/png", icone()),
}


class RefusDeDemarrer(Exception):
    """L'app ne démarre pas : son message dit pourquoi."""


def semer(donnees):
    """Sur un dossier de données absent ou vide, pose SEMIS ; un dossier non vide n'est pas touché."""
    try:
        if donnees.exists() and any(donnees.iterdir()):
            return
        for chemin, texte in SEMIS.items():
            fichier = donnees / chemin
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_bytes(texte.encode("utf-8"))
    except OSError as erreur:
        raise RefusDeDemarrer(f"données {donnees} : {erreur.strerror or erreur}") from None


def monte(dossier):
    """Vrai si le dossier est là, et non vide."""
    try:
        return dossier.is_dir() and any(dossier.iterdir())
    except OSError:
        return False


def version_de(dossier):
    """La version de schéma que porte le dossier (son fichier `version`), ou None."""
    try:
        return (dossier / "version").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def demarrer(environ):
    """Ce que sert l'app, `montee` ou `exemple` ; RefusDeDemarrer si elle ne peut pas servir."""
    config = Path(environ.get("FAUSSE_APP_CONFIG", "/config"))
    contenu = Path(environ.get("FAUSSE_APP_CONTENU", "/contenu"))
    config_montee = monte(config)
    contenu_monte = monte(contenu)
    if environ.get("FAUSSE_APP_ENV", "dev") == "prod":
        manquants = [
            point
            for point, present in (("/config", config_montee), ("/contenu", contenu_monte))
            if not present
        ]
        if manquants:
            raise RefusDeDemarrer(
                f"en prod, {' et '.join(manquants)} absent ou vide : pas de repli sur l'exemple"
            )
    for quoi, dossier in (
        ("configuration", config if config_montee else EXEMPLE),
        ("contenu", contenu if contenu_monte else EXEMPLE_CONTENU),
    ):
        version = version_de(dossier)
        if version not in VERSIONS_CONNUES:
            raise RefusDeDemarrer(f"version de {quoi} inconnue : {version!r} ({dossier})")
    return "montee" if config_montee else "exemple"


def sante(configuration):
    """Le code HTTP et le document de la route de santé."""
    donnees = Path(os.environ.get("FAUSSE_APP_DONNEES", "/donnees"))
    if not (donnees / "MARQUE").is_file():
        return 503, {"statut": "ko"}
    return 200, {
        "statut": "ok",
        "environnement": os.environ.get("FAUSSE_APP_ENV", "dev"),
        "version": os.environ.get("FAUSSE_APP_VERSION", "dev"),
        "revision": os.environ.get("FAUSSE_APP_REVISION", "local"),
        "configuration": configuration,
    }


class Gestionnaire(BaseHTTPRequestHandler):
    # Ce que sert l'app, fixé au démarrage (demarrer).
    configuration = "exemple"

    def do_GET(self):
        if self.path == CHEMIN_SANTE:
            code, document = sante(self.configuration)
            self.repondre(code, "application/json", json.dumps(document).encode("utf-8"))
        elif self.path in RESSOURCES:
            self.repondre(200, *RESSOURCES[self.path])
        else:
            self.send_error(404)

    def repondre(self, code, type_contenu, corps):
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


def main():
    try:
        semer(Path(os.environ.get("FAUSSE_APP_DONNEES", "/donnees")))
        Gestionnaire.configuration = demarrer(os.environ)
    except RefusDeDemarrer as refus:
        print(f"fausse app : refus de démarrer : {refus}", file=sys.stderr, flush=True)
        return 1
    hote = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "3000"))
    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    print(
        f"fausse app : http://{hote}:{port}{CHEMIN_SANTE}, configuration "
        f"{Gestionnaire.configuration}",
        file=sys.stderr,
        flush=True,
    )
    serveur.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
