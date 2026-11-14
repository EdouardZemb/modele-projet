"""Le faux `gh` du relevé (`poste/releve.py`) : il ne connaît que `gh api`.

Il lit d'abord son entrée jusqu'à la fin, comme un `gh` qui attendrait une requête : un appelant
qui laisserait son entrée ouverte l'attendrait. Puis il note ses arguments dans le journal que
nomme `FAUX_GH_JOURNAL`, une ligne JSON par appel, avec la valeur de `GH_PAGER`.

Il refuse, par le code 2 :
- un premier argument autre que `api`, une option qu'il ne connaît pas, et `--jq` ;
- un argument qui porte `&`, `|`, `<`, `>`, `^`, `%`, `"` ou une fin de ligne : sous Windows, le
  `.cmd` qui l'enveloppe couperait ou réécrirait cet argument ;
- un appel REST, tout point d'API sauf `graphql`, sans `-X GET` : `gh api -f` l'enverrait en POST.

Il répond d'après le fichier JSON que nomme `FAUX_GH_REPONSES`. La clé est le point d'API suivi de
ses paramètres `-f` et `-F` triés, `chemin?clé=valeur&…` ; la valeur, `{"code": 0 ou 1,
"sortie": …}`, la sortie écrite telle quelle si c'est une chaîne, en JSON sinon, et au besoin
`"erreur"`, écrite sur la sortie d'erreur. Une clé inconnue rend 3.
"""

import json
import os
import sys

INTERDITS = set('&|<>^%"\n\r')
AVEC_VALEUR = {"-X", "--method", "-f", "--raw-field", "-F", "--field"}
DRAPEAUX = {"--paginate", "--slurp"}


def _refus(message: str) -> int:
    sys.stderr.write(f"faux gh : {message}\n")
    return 2


def main(argv: list[str]) -> int:
    sys.stdin.read()
    with open(os.environ["FAUX_GH_JOURNAL"], "a", encoding="utf-8") as journal:
        journal.write(json.dumps({"args": argv, "GH_PAGER": os.environ.get("GH_PAGER")}) + "\n")
    if any(INTERDITS & set(argument) for argument in argv):
        return _refus("argument interdit")
    if not argv or argv[0] != "api":
        return _refus("seul gh api est connu")
    methode = None
    point = None
    parametres: list[str] = []
    drapeaux: set[str] = set()
    i = 1
    while i < len(argv):
        argument = argv[i]
        if argument in AVEC_VALEUR:
            if i + 1 >= len(argv):
                return _refus(f"{argument} sans valeur")
            valeur = argv[i + 1]
            if argument in ("-X", "--method"):
                methode = valeur
            else:
                parametres.append(valeur)
            i += 2
            continue
        if argument in DRAPEAUX:
            drapeaux.add(argument)
        elif argument.startswith("-"):
            return _refus("option inconnue")
        elif point is None:
            point = argument
        else:
            return _refus("deux points d'API")
        i += 1
    if point is None:
        return _refus("point d'API absent")
    if "--slurp" in drapeaux and "--paginate" not in drapeaux:
        return _refus("--slurp sans --paginate")
    if point != "graphql" and methode != "GET":
        return _refus("appel REST sans -X GET")
    cle = point + ("?" + "&".join(sorted(parametres)) if parametres else "")
    with open(os.environ["FAUX_GH_REPONSES"], encoding="utf-8") as f:
        reponses = json.load(f)
    if cle not in reponses:
        sys.stderr.write("faux gh : clé inconnue\n")
        return 3
    reponse = reponses[cle]
    sortie = reponse.get("sortie", "")
    if not isinstance(sortie, str):
        sortie = json.dumps(sortie)
    sys.stdout.buffer.write(sortie.encode("utf-8"))
    if reponse.get("erreur"):
        sys.stderr.buffer.write(reponse["erreur"].encode("utf-8"))
    return int(reponse.get("code", 0))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
