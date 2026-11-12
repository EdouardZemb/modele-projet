"""Coupe le magasin containerd dans le `daemon.json` de Docker, sans en perdre les autres réglages.

LE-41 : depuis le passage d'`ubuntu-latest` à Ubuntu 26.04, le Docker du runner est un 29 en magasin
containerd, alors que la cible garde le magasin classique ; l'épreuve du ménage s'arrête sur
l'autre. Le job `fausse-app` lance ce script sous `sudo`, avant tout usage de Docker, puis redémarre
le démon : `python3 -I tests/modele/daemon_classique.py /etc/docker/daemon.json`. Le `daemon.json`
de l'image du runner porte déjà ses réglages : le script les garde, et ne pose que
`features.containerd-snapshotter: false`.

Un fichier absent ou vide vaut `{}`. Un JSON illisible, qui n'est pas un objet, ou dont `features`
n'est pas un objet, refuse (code 1) sans toucher au fichier. Sans chemin : code 64.
"""

import json
import sys
from pathlib import Path


def couper(texte):
    """Le `daemon.json` donné, le magasin containerd coupé ; `ValueError` s'il est illisible,
    `TypeError` s'il n'a pas la forme attendue."""
    try:
        reglages = json.loads(texte) if texte.strip() else {}
    except json.JSONDecodeError as erreur:
        raise ValueError(f"daemon.json illisible : {erreur}") from None
    if not isinstance(reglages, dict):
        raise TypeError("le daemon.json n'est pas un objet JSON")
    features = reglages.setdefault("features", {})
    if not isinstance(features, dict):
        raise TypeError("« features » n'est pas un objet JSON")
    features["containerd-snapshotter"] = False
    return json.dumps(reglages, indent=2, ensure_ascii=False) + "\n"


def main(arguments):
    if len(arguments) != 1:
        print("usage : python3 -I tests/modele/daemon_classique.py <daemon.json>", file=sys.stderr)
        return 64
    chemin = Path(arguments[0])
    try:
        texte = chemin.read_text(encoding="utf-8") if chemin.exists() else ""
        neuf = couper(texte)
    except (OSError, UnicodeDecodeError, ValueError, TypeError) as erreur:
        print(f"daemon_classique : {erreur}", file=sys.stderr)
        return 1
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(neuf, encoding="utf-8")
    except OSError as erreur:
        print(f"daemon_classique : {erreur}", file=sys.stderr)
        return 1
    print(f"daemon_classique : magasin containerd coupé dans {chemin}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
