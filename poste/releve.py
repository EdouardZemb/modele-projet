"""Le relevé des projets nés du modèle. Il lit GitHub par `gh api`, en lecture seule, et lance sur
ce qu'il lit les scripts du modèle de deux versions : celle de chaque projet, et la tête du clone.

Ses deux rôles : l'inventaire, avant une spec ou un plan, quand la tête ne porte pas encore le
changement (les règles des projets, leurs plans en cours, leurs fichiers gérés modifiés) ; la
mesure de l'effet de ce que la tête change, à la revue finale et à la clôture d'un lot. Il n'écrit
nulle part, sauf dans un dossier temporaire qu'il retire.

Les projets. Les dépôts du compte (`--compte`), lus par `user/repos` page par page (l'API publique
d'un compte ne liste aucun dépôt privé), et filtrés sur leur propriétaire. Un dépôt non archivé
est un projet quand le `.copier-answers.yml` de sa branche par défaut porte un `_src_path` qui
nomme `EdouardZemb/modele-projet`. Un 404 sur ce fichier dit « pas un projet » ; toute autre
erreur, et un 404 ailleurs, rend le projet « non relevé », jamais « pas un projet », et le relevé
passe au suivant. Une cible `donnees` a la nature `donnees`, que sa réponse ne porte pas.

Les relevés de chaque projet, après une en-tête (sa version, sa cible, sa nature, son mode de
fusion). « La tête » est le commit `HEAD` du clone, extrait comme une autre version.
- Les plans : chaque `*.md` sous `.claude/plans/` de la branche par défaut, sous-dossiers compris,
  lu par son blob. Il passe par le `plan.py` de la version du projet, puis par celui de la tête,
  chacun par `--sans-lieux` : « même verdict (passe) » ou « même verdict (refuse) » (même code,
  mêmes lignes hors du résumé), ou « verdict changé », à lire ; puis par celui de la tête par
  `--sans-lieux --neuf` : « refuserait s'il était neuf », une information, avec ses refus.
  `plan.py` se lance depuis le dossier temporaire, sur `.claude/plans/<nom>` : ses lignes ne
  portent aucun chemin du poste.
- Les PR ouvertes qui ajoutent un plan (`added`, ou `renamed`) : elles seront vérifiées sur leur
  commit de fusion, donc comme des plans neufs. Elles sont à lire.
- Les textes des N dernières PR (`--prs`), tous états, lus par REST, qui donne l'auteur tel que le
  workflow `texte-pr` le passe (`dependabot[bot]`) ; leurs fermetures par une requête GraphQL par
  dépôt. Chacune passe par le `texte_pr.py` des deux versions ; seules s'affichent celles dont le
  verdict change (« passait, refuse », « refusait, passe », « message changé »), à lire, puis un
  compte. Une PR absente de la réponse GraphQL a ses textes « non relevés ».
- La règle : les contrôles requis de la branche par défaut (`rules/branches/<branche>`), contre
  ceux du fichier géré `ruleset-main.json` de la tête. Un contrôle géré absent est à lire ; un
  contrôle propre au projet, une information ; un dépôt privé sans règle dit « aucune règle ».
- Les fichiers gérés : ceux des dossiers exclus des formateurs (`methode.md`), que le modèle change
  entre la version du projet (ou `--depuis`, pour tous) et la tête. Les semés (`_skip_if_exists`
  du `copier.yml` de la tête) et `.claude/settings.json` sont écartés. Un segment de chemin
  `{% if <réponse> == '<valeur>' %}<nom>{% endif %}`, `!=`, ou `{% if <réponse> %}`, s'évalue avec
  les réponses du projet ; tout autre Jinja, et tout fichier `.jinja`, donne « non comparé
  (rendu) ». Sinon, le blob du projet se compare, par son SHA, à celui du modèle à la version du
  projet : « identique », « modifié dans le projet » (à lire), « absent du projet », ou « nouveau
  dans le modèle ». Les autres fichiers gérés, comme le gabarit de PR, ne sont pas comparés.

Les scripts d'une version s'extraient une fois, fichier par fichier (`git ls-tree`, puis
`git show <version>:<chemin>`) : les seuls `*.py` de `template/scripts/modele/`, jamais un
`.jinja`. Une version absente du clone rend le projet « non relevé ». Un script qui ne se lance
pas, qui plante ou qui sort en erreur d'usage ne donne pas de verdict : un vrai refus rend 1 et
finit par la ligne `refus` du script, un code 1 sans elle est un plantage, tout autre code qu'un 0
ou un 1 une erreur ; le plan ou la PR est alors « non relevé », et le projet avec lui.

Le relevé n'écrit que dans un dossier temporaire, qui porte les plans de dépôts privés : s'il ne
se retire pas à la fin, une ligne fixe le dit, sans son chemin, et le code passe à 1.

Les appels à `gh` : tous par `gh api`, sans `--jq`, chaque appel REST par `-X GET`, ses paramètres
par `-f clé=valeur`. Aucun argument ne porte `&`, `|`, `<`, `>`, `^`, `%`, `"` ni une fin de ligne,
qu'un `.cmd` couperait ou réécrirait sous Windows. Chaque lancement : `GH_PAGER` vide, l'entrée
fermée, sans terminal.

La sortie ne cite jamais une ligne lue : des noms, des numéros, des verdicts, des textes fixes, et
les lignes des scripts du modèle, qui ne citent rien non plus. Chaque nom passe par `_affichable`.
Chaque ligne commence par `relevé : `.

Bibliothèque standard seule, Python 3.10 ou plus.

Usage : releve.py [--compte COMPTE] [--prs N] [--depuis ÉTIQUETTE] [--clone DOSSIER] [--gh GH]
        Depuis la racine du clone du modèle, `gh` connecté. --prs : de 1 à 100 (défaut : 50).
        --clone : défaut, le dépôt git du dossier courant. --gh : défaut, `gh`.

Retour : 0 tous les projets lus et rien à lire ; 1 quelque chose à lire, un projet non relevé,
         aucun projet relevé (un `--compte` qui n'est pas celui de `gh` n'en trouve aucun), une
         erreur passagère sur la liste des dépôts ou le dossier temporaire non retiré ;
         64 erreur d'usage (`gh` absent, ou sans accès : un 401 sur la liste des dépôts, ou `gh`
         qui y sort par 4, authentification requise, même sans rien écrire ; un dossier qui n'est
         pas un clone du modèle, ou dont la tête ne dit pas ses contrôles gérés ; une option
         invalide).
"""

from __future__ import annotations

import argparse
import base64
import binascii
import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_RIEN = 0
EXIT_A_LIRE = 1
EXIT_USAGE = 64
PREFIXE = "relevé : "
MODELE = "EdouardZemb/modele-projet"
COMPTE = "EdouardZemb"
PRS = 50
PRS_MAX = 100
PLANS = ".claude/plans/"
SCRIPTS = "template/scripts/modele/"
REGLE = "template/.github/{% if cible != 'donnees' %}modele{% endif %}/ruleset-main.json"
# Les dossiers gérés exclus des formateurs (`methode.md`, « Les fichiers gérés par le modèle »).
GERES = (".githooks/", "scripts/modele/", "docs/modele/", ".github/modele/")
GERES += (".claude/skills/consigner/",)
MIXTE = ".claude/settings.json"
LIMITES = (
    "fichiers gérés : seuls les dossiers exclus des formateurs (methode.md) sont comparés, pas le "
    "gabarit de PR ni les autres fichiers gérés hors d'eux"
)
VERSION_ABSENTE = "version absente du clone, lancer git fetch --tags"
NEUF = "refuserait s'il était neuf"
REFUS_DU_PLAN = "plan : refus"
REFUS_DU_TEXTE = "texte de la PR : refus"
TEMPORAIRE_NON_RETIRE = "dossier temporaire non retiré"
AUCUN_PROJET = "aucun projet né du modèle relevé"
# Le code de sortie de `gh` quand il n'est pas connecté : « authentification requise ».
GH_SANS_AUTHENTIFICATION = 4
GERES_ILLISIBLES = "contrôles gérés illisibles dans la tête du clone (ruleset-main.json)"
# Ce qu'aucun argument de `gh` ne porte : sous Windows, un `.cmd` le couperait ou le réécrirait.
INTERDITS = frozenset('&|<>^%"\n\r')
# Les fermetures des N dernières PR, en une requête par dépôt, sur une ligne et sans guillemets.
REQUETE = (
    "query($owner: String!, $name: String!, $n: Int!) { repository(owner: $owner, name: $name) "
    "{ pullRequests(last: $n) { nodes { number closingIssuesReferences(first: 100) "
    "{ totalCount nodes { number } } } } } }"
)
DELAI = 300

_COMPTE = re.compile(r"[A-Za-z0-9](?:-?[A-Za-z0-9])*")
_NOM = re.compile(r"[A-Za-z0-9._-]+")
_BRANCHE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]*")
_VALEUR = re.compile(r"[A-Za-z0-9._/+-]{1,100}")
_DU_MODELE = re.compile(r"(?<![\w.-])" + re.escape(MODELE) + r"(?:\.git)?/?$", re.IGNORECASE)
_STATUT = re.compile(r"[0-9]{3}")
_HTTP = re.compile(r"HTTP ([0-9]{3})")
_RESUME = re.compile(r"[0-9]+ mécanismes(?: vérifiés|, lieux non ouverts)")
_CLE = re.compile(r"([A-Za-z_][\w-]*)[ \t]*:(?:[ \t]+(.*))?$")
_SI = re.compile(
    r"\{%-?\s*if\s+([A-Za-z_]\w*)\s*(?:(==|!=)\s*'([^'{}%]*)'\s*)?-?%\}([^{}]*)"
    r"\{%-?\s*endif\s*-?%\}"
)
_JINJA = re.compile(r"\{[{%#].*?[}%#]\}")
_WORKFLOW_GERE = re.compile(r"\.github/workflows/modele-[^/]*\.yml")
_ILLISIBLE = re.compile(r'[<>:"|?*\\\x00-\x1f]')
_FAUX = frozenset({"", "false", "no", "off", "0", "null", "~"})


def _documentation():
    """`documentation.py` du clone de ce script, chargé sous un nom à lui, sans écrire de cache."""
    chemin = Path(__file__).resolve().parent.parent / SCRIPTS / "documentation.py"
    spec = importlib.util.spec_from_file_location("releve_documentation", chemin)
    module = importlib.util.module_from_spec(spec)
    avant = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = avant
    return module


def _sans_guillemets(valeur: str) -> str:
    """Une valeur YAML d'une ligne : entre apostrophes, `''` rend `'` ; entre guillemets, `\\"` et
    `\\\\` rendent `"` et `\\` ; sinon telle quelle."""
    if len(valeur) >= 2 and valeur[0] == valeur[-1] == "'":
        return valeur[1:-1].replace("''", "'")
    if len(valeur) >= 2 and valeur[0] == valeur[-1] == '"':
        return re.sub(r'\\(["\\])', r"\1", valeur[1:-1])
    return valeur


def _lire_reponses(texte: str) -> dict[str, str]:
    """Les clés de premier niveau d'un `.copier-answers.yml`, chaque valeur en texte. Une ligne
    indentée continue la valeur précédente, jointe par une espace ; une ligne qui commence par `#`,
    après ses blancs, est ignorée."""
    brutes: dict[str, str] = {}
    cle = None
    for ligne in texte.replace("\r\n", "\n").split("\n"):
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        if ligne[0] in " \t":
            if cle is not None:
                brutes[cle] = f"{brutes[cle]} {ligne.strip()}".strip()
            continue
        m = _CLE.match(ligne)
        cle = None if m is None else m.group(1)
        if cle is not None:
            brutes[cle] = (m.group(2) or "").strip()
    return {cle: _sans_guillemets(valeur) for cle, valeur in brutes.items()}


def _semes(texte: str) -> list[str]:
    """Les éléments `- <motif>` sous `_skip_if_exists:` d'un `copier.yml`, sans leurs
    guillemets."""
    semes: list[str] = []
    dedans = False
    for ligne in texte.replace("\r\n", "\n").split("\n"):
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        if ligne[0] not in " \t-":
            dedans = ligne.rstrip() == "_skip_if_exists:"
            continue
        m = re.match(r"[ \t]*-[ \t]+(.*?)[ \t]*$", ligne)
        if dedans and m is not None:
            semes.append(_sans_guillemets(m.group(1)))
    return semes


def _vrai(valeur: str | None) -> bool:
    return valeur is not None and valeur.strip().lower() not in _FAUX


def _rendre(chemin: str, reponses: dict[str, str]) -> tuple[str | None, bool]:
    """Le chemin d'un fichier du gabarit, rendu pour un projet : (chemin, ou `None` s'il n'est pas
    rendu ; vrai s'il n'est pas comparable, `.jinja` ou d'un autre Jinja que les conditions
    simples). Une condition simple s'évalue ; un autre Jinja se retire du nom."""
    rendu = chemin.endswith(".jinja")
    if rendu:
        chemin = chemin.removesuffix(".jinja")
    segments = []
    for segment in chemin.split("/"):
        m = _SI.fullmatch(segment)
        if m is not None:
            nom, operateur, attendu, texte = m.groups()
            valeur = reponses.get(nom)
            if operateur is None:
                vrai = _vrai(valeur)
            else:
                vrai = (valeur == attendu) == (operateur == "==")
            if not vrai or not texte:
                return None, rendu
            segments.append(texte)
        elif _JINJA.search(segment):
            rendu = True
            segment = _JINJA.sub("", segment)
            if not segment:
                return None, rendu
            segments.append(segment)
        else:
            segments.append(segment)
    return "/".join(segments), rendu


def _gere(chemin: str) -> bool:
    return chemin.startswith(GERES) or _WORKFLOW_GERE.fullmatch(chemin) is not None


def _git(clone: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(clone), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )


def _ls_tree(clone: Path, *args: str) -> list[tuple[str, str, str]] | None:
    """Les entrées de `git ls-tree -z --full-tree` : (type, SHA, chemin) ; `None` en erreur."""
    r = _git(clone, "ls-tree", "-z", "--full-tree", *args)
    if r.returncode != 0:
        return None
    entrees = []
    for entree in filter(None, r.stdout.decode("utf-8", errors="replace").split("\0")):
        meta, _, chemin = entree.partition("\t")
        morceaux = meta.split()
        if len(morceaux) == 3:
            entrees.append((morceaux[1], morceaux[2], chemin))
    return entrees


def _extraire(clone: Path, version: str, dossier: Path) -> list[str] | None:
    """Les `*.py` de `template/scripts/modele/` à `version`, écrits dans `dossier` tels que
    `git show` les rend, sans conversion : leurs noms, triés ; `None` si la version manque."""
    entrees = _ls_tree(clone, version, SCRIPTS)
    if entrees is None:
        return None
    noms = []
    for sorte, _, chemin in entrees:
        nom = chemin.removeprefix(SCRIPTS)
        if sorte != "blob" or "/" in nom or not nom.endswith(".py"):
            continue
        r = _git(clone, "show", f"{version}:{chemin}")
        if r.returncode != 0:
            return None
        (dossier / nom).write_bytes(r.stdout)
        noms.append(nom)
    return sorted(noms)


def _clone(chemin: str | None) -> Path | None:
    """La racine du clone du modèle : le dépôt git de `chemin` (défaut : le dossier courant), dont
    la tête porte `copier.yml` et `plan.py` ; `None` sinon."""
    base = Path(chemin) if chemin else Path.cwd()
    if not base.is_dir():
        return None
    r = _git(base, "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        return None
    racine = Path(r.stdout.decode("utf-8", errors="replace").strip())
    for fichier in ("copier.yml", SCRIPTS + "plan.py"):
        if _git(racine, "cat-file", "-e", f"HEAD:{fichier}").returncode != 0:
            return None
    return racine


class _NonReleve(Exception):
    """Un projet que le relevé n'a pas pu lire en entier : la raison, en morceaux."""


class _Releve:
    def __init__(
        self,
        gh: str,
        clone: Path,
        tmp: Path,
        compte: str,
        prs: int,
        depuis: str | None,
        geres: set[str],
    ):
        self.gh = gh
        self.clone = clone
        self.tmp = tmp
        self.compte = compte
        self.prs = prs
        self.doc = _documentation()
        self.env = dict(os.environ, GH_PAGER="")
        self.shas: dict[str, str | None] = {}
        self.scripts: dict[str, Path | None] = {}
        self.blobs: dict[str, dict[str, str]] = {}
        self.dossiers = 0
        self.tete = self._sha("HEAD")
        self.depuis = None if depuis is None else self._sha(depuis)
        self.depuis_nom = depuis
        copier = _git(clone, "show", "HEAD:copier.yml").stdout.decode("utf-8", errors="replace")
        self.semes = _semes(copier)
        self.geres = geres

    # --- les sorties ---

    def _dire(self, *morceaux: str) -> None:
        print(PREFIXE + " : ".join(morceaux), flush=True)

    def _nom(self, texte: str) -> str:
        return self.doc._affichable(texte)

    # --- le clone ---

    def _sha(self, version: str) -> str | None:
        if version not in self.shas:
            r = _git(self.clone, "rev-parse", "--verify", "--quiet", f"{version}^{{commit}}")
            sha = r.stdout.decode("ascii", errors="replace").strip()
            self.shas[version] = sha if r.returncode == 0 and sha else None
        return self.shas[version]

    def _dossier(self, prefixe: str) -> Path:
        self.dossiers += 1
        dossier = self.tmp / f"{prefixe}{self.dossiers}"
        dossier.mkdir()
        return dossier

    def _scripts(self, sha: str) -> Path | None:
        if sha not in self.scripts:
            dossier = self._dossier("version-")
            self.scripts[sha] = None if _extraire(self.clone, sha, dossier) is None else dossier
        return self.scripts[sha]

    def _blobs(self, sha: str) -> dict[str, str]:
        """Les SHA des blobs du gabarit à une version, par chemin sous `template/`."""
        if sha not in self.blobs:
            entrees = _ls_tree(self.clone, "-r", sha, "template/") or []
            self.blobs[sha] = {
                chemin.removeprefix("template/"): blob
                for sorte, blob, chemin in entrees
                if sorte == "blob"
            }
        return self.blobs[sha]

    # --- les lancements ---

    def _api(self, rubrique: str, nom: str, point: str, *parametres: str, pages=False):
        """Un appel REST, `-X GET`, ses paramètres par `-f`, chacun `clé=valeur` : le JSON lu.
        Une erreur lève `_NonReleve`, avec son statut."""
        args = ["api", point, "-X", "GET"]
        for parametre in parametres:
            args += ["-f", parametre]
        if pages:
            args += ["--paginate", "--slurp"]
        return self._gh(rubrique, nom, args)

    def _gh(self, rubrique: str, nom: str, args: list[str]):
        if any(INTERDITS & set(arg) for arg in args):
            raise _NonReleve(rubrique, "argument refusé")
        try:
            r = subprocess.run(
                [self.gh, *args],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                env=self.env,
                timeout=DELAI,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise _NonReleve(rubrique, "délai dépassé") from None
        except OSError:
            raise _GhAbsent(rubrique, "gh ne se lance pas") from None
        if r.returncode == GH_SANS_AUTHENTIFICATION:
            # `gh` jamais connecté : ni JSON ni `HTTP NNN`, seulement ce code
            raise _SansAcces(rubrique, "authentification requise")
        if r.returncode != 0:
            raise _Erreur(rubrique, _statut(r.stdout, r.stderr))
        try:
            return json.loads(r.stdout.decode("utf-8", errors="replace") or "null")
        except ValueError:
            raise _NonReleve(rubrique, "réponse illisible") from None

    def _lancer(self, script: Path, args: list[str], cwd: Path, env=None):
        """Un script du modèle : (code, lignes de sa sortie), ou `None` s'il ne se lance pas. Sa
        sortie d'erreur n'est jamais lue."""
        try:
            r = subprocess.run(
                [sys.executable, "-X", "utf8", "-B", str(script), *args],
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=DELAI,
                check=False,
            )
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None
        sortie = r.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
        return r.returncode, [ligne for ligne in sortie.split("\n") if ligne]

    # --- le relevé ---

    def lancer(self) -> int:
        try:
            pages = self._gh(
                "dépôts",
                "",
                ["api", "user/repos", "-X", "GET", "-f", "affiliation=owner", "-f", "per_page=100"]
                + ["--paginate", "--slurp"],
            )
        except _GhAbsent:
            return _usage("gh ne se lance pas")
        except _SansAcces:
            return _usage("gh sans accès (dépôts : authentification requise, code 4)")
        except _Erreur as e:
            # un accès refusé est une erreur d'usage ; une erreur passagère, un dépôt non relevé
            if e.args[1] == "401":
                return _usage("gh sans accès (dépôts : erreur 401)")
            self._dire("non relevé", "dépôts", f"erreur {e.args[1]}")
            return EXIT_A_LIRE
        except _NonReleve as e:
            self._dire("non relevé", *e.args)
            return EXIT_A_LIRE
        depots = _aplatir(pages)
        if depots is None:
            self._dire("non relevé", "dépôts", "réponse illisible")
            return EXIT_A_LIRE
        depots = [
            d
            for d in depots
            if isinstance(d, dict)
            and str((d.get("owner") or {}).get("login", "")).casefold() == self.compte.casefold()
        ]
        projets = lus = non_releves = a_lire = 0
        for depot in sorted(depots, key=lambda d: str(d.get("name", ""))):
            if depot.get("archived"):
                continue
            resultat = self._projet(depot)
            if resultat is None:
                continue
            incomplet, aussi_a_lire = resultat
            projets += 1
            non_releves += incomplet
            lus += not incomplet
            a_lire += aussi_a_lire
        # aucun projet : rien n'est lu, et un `--compte` faux ne passe pas pour un relevé propre
        if not projets:
            self._dire(AUCUN_PROJET)
        self._dire(LIMITES)
        self._dire(
            f"{len(depots)} dépôts examinés, {projets} projets, {lus} lus, "
            f"{non_releves} non relevés, {a_lire} à lire"
        )
        return EXIT_A_LIRE if non_releves or a_lire or not projets else EXIT_RIEN

    def _projet(self, depot: dict) -> tuple[bool, bool] | None:
        """Un dépôt : `None` s'il n'est pas un projet ; sinon (non relevé, à lire)."""
        self.a_lire = False
        self.incomplet = False
        nom = str(depot.get("name", ""))
        affiche = self._nom(nom) if nom else "?"
        try:
            if _NOM.fullmatch(nom) is None:
                raise _NonReleve("nom illisible")
            if not self._relever(nom, depot):
                return None
        except _Erreur as e:
            rubrique, statut = e.args
            self._dire(affiche, "non relevé", rubrique, f"erreur {statut}")
            return True, self.a_lire
        except _NonReleve as e:
            self._dire(affiche, "non relevé", *e.args)
            return True, self.a_lire
        return self.incomplet, self.a_lire

    def _relever(self, nom: str, depot: dict) -> bool:
        branche = str(depot.get("default_branch", ""))
        if _BRANCHE.fullmatch(branche) is None or ".." in branche:
            raise _NonReleve("branche illisible")
        depot_api = f"repos/{self.compte}/{nom}"
        try:
            reponse = self._api(
                "réponses", nom, f"{depot_api}/contents/.copier-answers.yml", f"ref={branche}"
            )
        except _Erreur as e:
            if e.args[1] == "404":
                return False
            raise
        texte = _contenu(reponse)
        if texte is None:
            raise _NonReleve("réponses", "réponse illisible")
        reponses = _lire_reponses(texte)
        if _DU_MODELE.search(reponses.get("_src_path", "")) is None:
            return False
        if reponses.get("cible") == "donnees" and "nature" not in reponses:
            reponses["nature"] = "donnees"
        version = reponses.get("_commit", "")
        self._dire(
            nom,
            f"{_valeur(version)}, cible {_valeur(reponses.get('cible'))}, "
            f"nature {_valeur(reponses.get('nature'))}, fusion {_valeur(reponses.get('fusion'))}",
        )
        if _VERSION.fullmatch(version) is None or ".." in version:
            raise _NonReleve("version illisible")
        sha = self._sha(version)
        if sha is None:
            raise _NonReleve(VERSION_ABSENTE)
        reponse = self._api("arbre", nom, f"{depot_api}/git/trees/{branche}", "recursive=1")
        if not isinstance(reponse, dict) or not isinstance(reponse.get("tree"), list):
            raise _NonReleve("arbre", "réponse illisible")
        if reponse.get("truncated"):
            raise _NonReleve("arbre tronqué")
        arbre = {
            e["path"]: e["sha"]
            for e in reponse["tree"]
            if isinstance(e, dict)
            and e.get("type") == "blob"
            and isinstance(e.get("path"), str)
            and isinstance(e.get("sha"), str)
        }
        ancienne = self._scripts(sha)
        tete = self._scripts(self.tete)
        if ancienne is None or tete is None:
            raise _NonReleve("scripts illisibles dans le clone")
        self._plans(nom, depot_api, arbre, ancienne, tete)
        self._ouvertes(nom, depot_api)
        self._textes(nom, depot_api, ancienne, tete)
        self._regle(nom, depot_api, branche, bool(depot.get("private")))
        self._fichiers_geres(nom, arbre, reponses, sha, version)
        return True

    # --- les rubriques ---

    def _plans(self, nom: str, depot_api: str, arbre: dict, ancienne: Path, tete: Path) -> None:
        plans = sorted(p for p in arbre if p.startswith(PLANS) and p.endswith(".md"))
        if not plans:
            self._dire(nom, "plans", "aucun plan en cours")
            return
        if not (ancienne / "plan.py").is_file() or not (tete / "plan.py").is_file():
            raise _NonReleve("plans", "plan.py absent d'une version")
        travail = self._dossier("plans-")
        lus = []
        for chemin in plans:
            relatif = chemin.removeprefix(PLANS)
            segments = relatif.split("/")
            if _ILLISIBLE.search(relatif) or any(s in ("", ".", "..") for s in segments):
                self._dire(nom, "plans", self._nom(relatif), "non relevé (nom illisible)")
                self.incomplet = True
                continue
            octets = _octets(self._api("plans", nom, f"{depot_api}/git/blobs/{arbre[chemin]}"))
            if octets is None:
                raise _NonReleve("plans", "réponse illisible")
            fichier = travail.joinpath(*chemin.split("/"))
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_bytes(octets)
            lus.append(chemin)
        for chemin in lus:
            affiche = self._nom(chemin.removeprefix(PLANS))
            prefixe = f"plan : {self._nom(chemin)} : "
            avant = self._verdict_du_plan(ancienne, chemin, prefixe, travail, [])
            apres = self._verdict_du_plan(tete, chemin, prefixe, travail, [])
            neuf = self._verdict_du_plan(tete, chemin, prefixe, travail, ["--neuf"])
            echecs = [
                cote
                for cote, verdict in (
                    ("version du projet", avant),
                    ("tête", apres),
                    ("tête par --neuf", neuf),
                )
                if verdict is None
            ]
            if echecs:
                self.incomplet = True
                self._dire(
                    nom, "plans", affiche, f"non relevé (plan.py en échec : {', '.join(echecs)})"
                )
                continue
            if avant == apres:
                commun = "passe" if avant[0] == 0 else "refuse"
                self._dire(nom, "plans", affiche, f"même verdict ({commun})")
            else:
                self.a_lire = True
                self._dire(nom, "plans", affiche, "verdict changé")
                self._ecarts(nom, "plans", affiche, avant, apres)
            if neuf[0] != 0:
                self._dire(nom, "plans", affiche, NEUF)
                for ligne in neuf[1]:
                    self._dire(nom, "plans", affiche, "neuf", ligne)

    def _verdict_du_plan(self, scripts: Path, chemin: str, prefixe: str, travail: Path, en_plus):
        """(code, lignes) de `plan.py --sans-lieux` sur un plan, sans le résumé ni la ligne
        `refus`, chaque ligne sans son préfixe ; `None` s'il ne se lance pas, plante ou sort en
        erreur d'usage (`_resultat`)."""
        lance = self._lancer(scripts / "plan.py", [chemin, "--sans-lieux", *en_plus], travail)
        resultat = _resultat(lance, REFUS_DU_PLAN)
        if resultat is None:
            return None
        code, lignes = resultat
        gardees = [
            ligne.removeprefix(prefixe)
            for ligne in lignes
            if ligne.startswith(prefixe) and _RESUME.match(ligne.removeprefix(prefixe)) is None
        ]
        return code, gardees

    def _ecarts(self, nom: str, rubrique: str, affiche: str, avant, apres) -> None:
        """Ce qui distingue deux verdicts : les codes, s'ils diffèrent, puis les lignes propres à
        chacun."""
        if avant[0] != apres[0]:
            self._dire(nom, rubrique, affiche, "version du projet", f"code {avant[0]}")
            self._dire(nom, rubrique, affiche, "tête", f"code {apres[0]}")
        for ligne in avant[1]:
            if ligne not in apres[1]:
                self._dire(nom, rubrique, affiche, "version du projet", ligne)
        for ligne in apres[1]:
            if ligne not in avant[1]:
                self._dire(nom, rubrique, affiche, "tête", ligne)

    def _ouvertes(self, nom: str, depot_api: str) -> None:
        pages = self._api(
            "PR ouvertes", nom, f"{depot_api}/pulls", "state=open", "per_page=100", pages=True
        )
        ouvertes = _aplatir(pages)
        if ouvertes is None:
            raise _NonReleve("PR ouvertes", "réponse illisible")
        ajoutent = 0
        for pr in ouvertes:
            numero = _numero(pr)
            if numero is None:
                raise _NonReleve("PR ouvertes", "réponse illisible")
            fichiers = _aplatir(
                self._api(
                    "PR ouvertes",
                    nom,
                    f"{depot_api}/pulls/{numero}/files",
                    "per_page=100",
                    pages=True,
                )
            )
            if fichiers is None:
                raise _NonReleve("PR ouvertes", "réponse illisible")
            ajouts = sorted(
                f["filename"]
                for f in fichiers
                if isinstance(f, dict)
                and f.get("status") in ("added", "renamed")
                and isinstance(f.get("filename"), str)
                and f["filename"].startswith(PLANS)
                and f["filename"].endswith(".md")
            )
            for ajout in ajouts:
                self._dire(
                    nom,
                    "PR ouvertes",
                    f"PR {numero}",
                    "ajoute un plan",
                    self._nom(ajout[len(PLANS) :]),
                )
            if ajouts:
                ajoutent += 1
                self.a_lire = True
        self._dire(nom, "PR ouvertes", f"{len(ouvertes)} ouvertes, {ajoutent} ajoutent un plan")

    def _textes(self, nom: str, depot_api: str, ancienne: Path, tete: Path) -> None:
        pulls = self._api("textes", nom, f"{depot_api}/pulls", "state=all", f"per_page={self.prs}")
        if not isinstance(pulls, list):
            raise _NonReleve("textes", "réponse illisible")
        lues = changes = absentes = 0
        fermetures: dict[int, dict] = {}
        travail = self.tmp
        if pulls:
            if not (ancienne / "texte_pr.py").is_file() or not (tete / "texte_pr.py").is_file():
                raise _NonReleve("textes", "texte_pr.py absent d'une version")
            reponse = self._gh(
                "textes",
                nom,
                ["api", "graphql", "-f", f"query={REQUETE}", "-f", f"owner={self.compte}"]
                + ["-f", f"name={nom}", "-F", f"n={self.prs}"],
            )
            fermetures = _fermetures(reponse)
            if fermetures is None:
                raise _NonReleve("textes", "réponse illisible")
            travail = self._dossier("textes-")
        for pr in pulls:
            numero = _numero(pr)
            if numero is None:
                raise _NonReleve("textes", "réponse illisible")
            if numero in fermetures:
                echecs, verdicts = self._verdicts_du_texte(
                    pr, numero, fermetures[numero], ancienne, tete, travail
                )
                raison = f"texte_pr.py en échec : {', '.join(echecs)}"
            else:
                verdicts, raison = None, "absente de la réponse GraphQL"
            if verdicts is None:
                absentes += 1
                self.incomplet = True
                self._dire(nom, "textes", f"PR {numero}", f"non relevés ({raison})")
                continue
            lues += 1
            avant, apres = verdicts
            verdict = _verdict_du_texte(avant, apres)
            if verdict is not None:
                changes += 1
                self.a_lire = True
                self._dire(nom, "textes", f"PR {numero}", verdict)
                self._ecarts(nom, "textes", f"PR {numero}", avant, apres)
        self._dire(
            nom, "textes", f"{lues} PR lues, {changes} verdicts changés, {absentes} non relevées"
        )

    def _verdicts_du_texte(self, pr: dict, numero: int, references, ancienne, tete, travail):
        """Les verdicts du `texte_pr.py` des deux versions sur une PR : (côtés en échec, puis
        les deux verdicts, ou `None` si l'un des deux ne se lance pas, plante ou sort en erreur
        d'usage, `_resultat`)."""
        fichier = travail / f"fermetures-{numero}.json"
        fichier.write_text(
            json.dumps(
                {"data": {"repository": {"pullRequest": {"closingIssuesReferences": references}}}}
            ),
            encoding="utf-8",
        )
        env = dict(
            os.environ,
            CORPS=str(pr.get("body") or "").replace("\0", ""),
            AUTEUR=str((pr.get("user") or {}).get("login") or ""),
            TETE=str((pr.get("head") or {}).get("sha") or ""),
        )
        verdicts = []
        echecs = []
        for cote, scripts in (("version du projet", ancienne), ("tête", tete)):
            lance = self._lancer(
                scripts / "texte_pr.py", ["--fermetures", str(fichier)], travail, env
            )
            resultat = _resultat(lance, REFUS_DU_TEXTE)
            if resultat is None:
                echecs.append(cote)
                continue
            code, lignes = resultat
            verdicts.append((code, [ligne for ligne in lignes if ligne != REFUS_DU_TEXTE]))
        if echecs:
            return echecs, None
        return [], (verdicts[0], verdicts[1])

    def _regle(self, nom: str, depot_api: str, branche: str, prive: bool) -> None:
        regles = self._api("règle", nom, f"{depot_api}/rules/branches/{branche}")
        if not isinstance(regles, list):
            raise _NonReleve("règle", "réponse illisible")
        contextes: set[str] = set()
        for regle in regles:
            if not isinstance(regle, dict) or regle.get("type") != "required_status_checks":
                continue
            controles = (regle.get("parameters") or {}).get("required_status_checks") or []
            contextes |= {c["context"] for c in controles if isinstance(c, dict) and "context" in c}
        if not regles:
            self._dire(nom, "règle", "aucune règle")
            if prive:
                return
        absents = sorted(self.geres - contextes)
        for controle in absents:
            self.a_lire = True
            self._dire(nom, "règle", "contrôle géré absent", self._nom(str(controle)))
        for controle in sorted(contextes - self.geres):
            self._dire(nom, "règle", "contrôle propre", self._nom(str(controle)))
        if not absents:
            self._dire(nom, "règle", "contrôles gérés présents")

    def _fichiers_geres(self, nom: str, arbre: dict, reponses: dict, sha: str, version: str):
        base = self.depuis or sha
        du_projet = self._blobs(sha)
        de_la_base = self._blobs(base)
        de_la_tete = self._blobs(self.tete)
        changes = {
            chemin
            for chemin in de_la_base.keys() | de_la_tete.keys()
            if de_la_base.get(chemin) != de_la_tete.get(chemin)
        }
        verdicts = []
        for chemin in changes:
            rendu, jinja = _rendre(chemin, reponses)
            if rendu is None or not _gere(rendu) or rendu == MIXTE:
                continue
            if any(fnmatch.fnmatchcase(rendu, motif) for motif in self.semes):
                continue
            if jinja:
                verdict = "non comparé (rendu)"
            elif chemin not in du_projet:
                if chemin not in de_la_tete:
                    continue
                verdict = "nouveau dans le modèle"
            elif rendu not in arbre:
                verdict = "absent du projet"
            elif arbre[rendu] == du_projet[chemin]:
                verdict = "identique"
            else:
                verdict = "modifié dans le projet"
                self.a_lire = True
            verdicts.append((rendu, verdict))
        if not verdicts:
            depuis = _valeur(self.depuis_nom if self.depuis else version)
            self._dire(nom, "fichiers gérés", f"aucun changé depuis {depuis}")
        for rendu, verdict in sorted(verdicts):
            self._dire(nom, "fichiers gérés", self._nom(rendu), verdict)


class _Erreur(_NonReleve):
    """Une erreur de `gh api` : (rubrique, statut)."""


class _GhAbsent(_NonReleve):
    """`gh` trouvé, mais qui ne se lance pas : (rubrique, raison)."""


class _SansAcces(_NonReleve):
    """`gh` qui sort par 4, sans connexion : (rubrique, raison)."""


def _resultat(lance, refus: str) -> tuple[int, list[str]] | None:
    """Le verdict d'un script du modèle, (code, lignes), ou `None` : un script qui ne s'est pas
    lancé, qui a planté ou qui est sorti en erreur d'usage. Un vrai refus rend 1 et finit par la
    ligne de refus du script (`refus`) ; un code 1 sans elle est un plantage, une exception non
    rattrapée ; tout autre code qu'un 0 ou un 1 n'est pas un verdict."""
    if lance is None:
        return None
    code, lignes = lance
    if code == 0 or (code == 1 and lignes and lignes[-1] == refus):
        return lance
    return None


def _contextes_geres(clone: Path) -> set[str] | None:
    """Les contrôles requis du fichier géré `ruleset-main.json` de la tête ; `None` s'il est
    absent, illisible, d'une autre forme, ou s'il n'en nomme aucun."""
    # absent de la tête, `git show` n'écrit rien : un JSON vide, illisible
    r = _git(clone, "show", f"HEAD:{REGLE}")
    try:
        regle = json.loads(r.stdout.decode("utf-8"))
        contextes = {
            c["context"]
            for regles in regle["rules"]
            if regles.get("type") == "required_status_checks"
            for c in regles["parameters"]["required_status_checks"]
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if not contextes or not all(isinstance(c, str) and c for c in contextes):
        return None
    return contextes


def _statut(sortie: bytes, erreur: bytes) -> str:
    """Le statut HTTP d'une erreur de `gh api` : le `status` du JSON qu'il écrit sur sa sortie,
    sinon le `HTTP NNN` de sa sortie d'erreur, sinon `?`."""
    try:
        reponse = json.loads(sortie.decode("utf-8", errors="replace"))
    except ValueError:
        reponse = None
    if isinstance(reponse, dict):
        statut = str(reponse.get("status", ""))
        if _STATUT.fullmatch(statut):
            return statut
    m = _HTTP.search(erreur.decode("utf-8", errors="replace"))
    return m.group(1) if m else "?"


def _aplatir(pages) -> list | None:
    """Les éléments d'une réponse de `--paginate --slurp` : une page par élément du tableau."""
    if not isinstance(pages, list) or not all(isinstance(page, list) for page in pages):
        return None
    return [element for page in pages for element in page]


def _octets(reponse) -> bytes | None:
    """Le contenu d'un blob ou d'un fichier de l'API, en base64 coupé de fins de ligne."""
    if not isinstance(reponse, dict) or not isinstance(reponse.get("content"), str):
        return None
    if reponse.get("encoding", "base64") != "base64":
        return None
    try:
        return base64.b64decode(reponse["content"])
    except (binascii.Error, ValueError):
        return None


def _contenu(reponse) -> str | None:
    octets = _octets(reponse)
    return None if octets is None else octets.decode("utf-8", errors="replace")


def _numero(pr) -> int | None:
    numero = pr.get("number") if isinstance(pr, dict) else None
    return numero if isinstance(numero, int) and not isinstance(numero, bool) else None


def _fermetures(reponse) -> dict[int, dict] | None:
    """Les fermetures de chaque PR, par numéro, lues dans la réponse GraphQL ; `None` si elle est
    mal formée."""
    try:
        noeuds = reponse["data"]["repository"]["pullRequests"]["nodes"]
        fermetures = {}
        for noeud in noeuds:
            if isinstance(noeud, dict) and isinstance(noeud.get("number"), int):
                fermetures[noeud["number"]] = noeud["closingIssuesReferences"]
        return fermetures
    except (KeyError, TypeError):
        return None


def _verdict_du_texte(avant, apres) -> str | None:
    if avant[0] == 0 and apres[0] != 0:
        return "passait, refuse"
    if avant[0] != 0 and apres[0] == 0:
        return "refusait, passe"
    if avant != apres:
        return "message changé"
    return None


def _valeur(valeur: str | None) -> str:
    """Une réponse affichée : un nom de version, de cible, de nature ou de mode, sinon `?`."""
    return valeur if valeur is not None and _VALEUR.fullmatch(valeur) else "?"


def _usage(raison: str) -> int:
    print(f"{PREFIXE}usage invalide : {raison} (voir --help)", file=sys.stderr)
    return EXIT_USAGE


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str):  # le message reçu pourrait citer l'entrée : on ne l'affiche pas
        self.exit(EXIT_USAGE, f"{PREFIXE}usage invalide (voir --help)\n")


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    p = _Analyseur(
        prog="releve.py",
        description=(
            "Le relevé des projets nés du modèle : leurs plans, leurs PR ouvertes, les textes de "
            "leurs PR, leur règle et leurs fichiers gérés, par les scripts de deux versions."
        ),
    )
    p.add_argument("--compte", default=COMPTE, help=f"le compte des dépôts (défaut : {COMPTE})")
    p.add_argument(
        "--prs", type=int, default=PRS, metavar="N", help=f"les N dernières PR (défaut : {PRS})"
    )
    p.add_argument(
        "--depuis", metavar="ÉTIQUETTE", help="le début des fichiers gérés comparés, pour tous"
    )
    p.add_argument("--clone", metavar="DOSSIER", help="le clone du modèle (défaut : celui d'ici)")
    p.add_argument("--gh", default="gh", metavar="GH", help="le programme gh (défaut : gh)")
    try:
        args = p.parse_args(argv)
    except SystemExit as sortie:
        return 0 if sortie.code in (0, None) else EXIT_USAGE
    if not 1 <= args.prs <= PRS_MAX:
        return _usage(f"--prs de 1 à {PRS_MAX}")
    if _COMPTE.fullmatch(args.compte) is None:
        return _usage("--compte : un compte GitHub")
    gh = shutil.which(args.gh)
    if gh is None:
        return _usage("gh introuvable")
    clone = _clone(args.clone)
    if clone is None:
        return _usage("dossier qui n'est pas un clone du modèle")
    if args.depuis is not None and (
        _VERSION.fullmatch(args.depuis) is None
        or ".." in args.depuis
        or _git(clone, "rev-parse", "--verify", "--quiet", f"{args.depuis}^{{commit}}").returncode
    ):
        return _usage("--depuis : étiquette absente du clone")
    geres = _contextes_geres(clone)
    if geres is None:
        return _usage(GERES_ILLISIBLES)
    tmp = tempfile.mkdtemp(prefix="releve-")
    code = EXIT_A_LIRE
    retire = False
    try:
        code = _Releve(gh, clone, Path(tmp), args.compte, args.prs, args.depuis, geres).lancer()
    finally:
        # il porte des plans de dépôts privés : un échec du retrait se dit, sans le chemin
        try:
            shutil.rmtree(tmp)
            retire = True
        except OSError:
            print(PREFIXE + TEMPORAIRE_NON_RETIRE, flush=True)
    return code if retire else max(code, EXIT_A_LIRE)


if __name__ == "__main__":
    sys.exit(main())
