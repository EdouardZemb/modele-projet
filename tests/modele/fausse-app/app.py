"""La fausse app du modèle : le contrat de la cible `serveur` (spec §6.1), en quelques lignes.

Elle écoute sur $PORT (défaut 3000), sur $HOST (défaut 0.0.0.0). Sa route de santé, /api/sante,
rend {statut, environnement, version, revision} : statut `ok` tant que ses données
(/donnees/MARQUE) sont là, sinon un 503 avec {statut: "ko"}. L'environnement, la version et la
révision viennent de FAUSSE_APP_ENV, FAUSSE_APP_VERSION et FAUSSE_APP_REVISION ; le Dockerfile
pose la révision, depuis l'argument de construction REVISION.

FAUSSE_APP_DONNEES remplace /donnees (pour les tests). Bibliothèque standard seule.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHEMIN_SANTE = "/api/sante"


def sante():
    """Le code HTTP et le document de la route de santé."""
    donnees = Path(os.environ.get("FAUSSE_APP_DONNEES", "/donnees"))
    if not (donnees / "MARQUE").is_file():
        return 503, {"statut": "ko"}
    return 200, {
        "statut": "ok",
        "environnement": os.environ.get("FAUSSE_APP_ENV", "dev"),
        "version": os.environ.get("FAUSSE_APP_VERSION", "dev"),
        "revision": os.environ.get("FAUSSE_APP_REVISION", "local"),
    }


class Gestionnaire(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != CHEMIN_SANTE:
            self.send_error(404)
            return
        code, document = sante()
        corps = json.dumps(document).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


def main():
    hote = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "3000"))
    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    print(f"fausse app : http://{hote}:{port}{CHEMIN_SANTE}", file=sys.stderr, flush=True)
    serveur.serve_forever()


if __name__ == "__main__":
    main()
