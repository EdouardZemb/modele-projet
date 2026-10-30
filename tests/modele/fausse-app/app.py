"""La fausse app du modèle : le contrat de la cible `serveur` (spec §6.1, M-0006 § 5), en quelques
lignes.

Elle écoute sur $PORT (défaut 3000), sur $HOST (défaut 0.0.0.0). Sa route de santé, /api/sante,
rend {statut, environnement, version, revision, configuration} : statut `ok` tant que ses données
(/donnees/MARQUE) sont là, sinon un 503 avec {statut: "ko"}. L'environnement, la version et la
révision viennent de FAUSSE_APP_ENV, FAUSSE_APP_VERSION et FAUSSE_APP_REVISION ; le Dockerfile
pose la révision, depuis l'argument de construction REVISION.

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
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHEMIN_SANTE = "/api/sante"
# Les versions de schéma de la configuration et du contenu que cette image sait lire.
VERSIONS_CONNUES = {"1"}
ICI = Path(__file__).resolve().parent
EXEMPLE = ICI / "exemple"
EXEMPLE_CONTENU = ICI / "exemple-contenu"


class RefusDeDemarrer(Exception):
    """L'app ne démarre pas : son message dit pourquoi."""


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
        if self.path != CHEMIN_SANTE:
            self.send_error(404)
            return
        code, document = sante(self.configuration)
        corps = json.dumps(document).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


def main():
    try:
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
