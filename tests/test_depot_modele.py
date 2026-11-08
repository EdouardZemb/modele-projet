"""Le dépôt modèle applique ses propres garde-fous, à sa racine."""

import hashlib
import json
import os
import re
import subprocess
import sys

import documentation
import yaml
from conftest import PERIMES, RACINE, sans_echappatoire, trouver_bash
from test_combinaisons import CLOTURE, SCHEMA, lien_casse

CI = RACINE / ".github/workflows/ci.yml"
TEXTE_PR = RACINE / ".github/workflows/texte-pr.yml"
COPIER = yaml.safe_load((RACINE / "copier.yml").read_text(encoding="utf-8"))


def test_ruleset_du_depot_modele():
    ruleset = json.loads((RACINE / ".github/ruleset-main.json").read_text(encoding="utf-8"))
    regles = {r["type"]: r for r in ruleset["rules"]}
    contextes = {
        c["context"]
        for c in regles["required_status_checks"]["parameters"]["required_status_checks"]
    }
    assert contextes == {
        "tests (ubuntu-latest)",
        "tests (windows-latest)",
        "secrets",
        "confidentialite",
        "mecanique",
        "fausse-app",
        "texte-pr",
    }

    jobs = [
        *yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"].values(),
        *yaml.safe_load(TEXTE_PR.read_text(encoding="utf-8"))["jobs"].values(),
    ]
    produits = set()
    for job in jobs:
        oses = job.get("strategy", {}).get("matrix", {}).get("os")
        if oses:
            produits |= {f"{job['name']} ({os})" for os in oses}
        else:
            produits.add(job["name"])
    assert contextes <= produits


def test_le_job_des_tests_a_40_minutes():
    """LE-29, puis LE-40 : sous Windows, la suite a dépassé 15, puis 25 min, sans test en échec."""
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    assert jobs["tests"]["timeout-minutes"] == 40


AUCUN_CACHE = "Aucun cache Python sous template/scripts/modele"


def test_aucun_cache_apres_les_tests(tmp_path):
    """AM-1 : après `pytest`, sur les deux systèmes, une étape échoue sur tout `__pycache__` sous
    `template/scripts/modele/`, que le garde protège. Elle lit le disque, pas git, qui ignore ce
    dossier ; sans le mot `pytest`, dont une seule commande du job peut porter le nom. Un `find` en
    échec (le dossier absent ou renommé) la fait échouer aussi, sans compter sur `-e` : sinon elle
    passerait à vide (LE-55)."""
    job = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["tests"]
    etapes = job["steps"]
    (lancement,) = [e for e in etapes if "pytest" in e.get("run", "")]
    (etape,) = [e for e in etapes if e.get("name") == AUCUN_CACHE]
    assert etapes.index(etape) > etapes.index(lancement)
    # Sans `shell:`, l'étape tournerait sous `pwsh` sous Windows, où `find` est un autre programme.
    assert etape["shell"] == "bash"
    sans_echappatoire(job, AUCUN_CACHE)
    for mot in ("pytest", "git"):
        assert mot not in etape["run"], mot

    def lancer(dossier, options):
        return subprocess.run(
            [trouver_bash(), "--noprofile", "--norc", *options, "-c", etape["run"]],
            cwd=dossier,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    propre = tmp_path / "propre"
    (propre / "template/scripts/modele").mkdir(parents=True)
    sale = tmp_path / "sale"
    (sale / "template/scripts/modele/__pycache__").mkdir(parents=True)
    (sale / "template/scripts/modele/__pycache__/x.pyc").write_bytes(b"")
    absent = tmp_path / "absent"
    (absent / "template/scripts").mkdir(parents=True)
    # Comme GitHub lance une étape `shell: bash`, puis sans `-e` ni `pipefail` : le refus est écrit.
    for options in (["-e", "-o", "pipefail"], []):
        r = lancer(propre, options)
        assert r.returncode == 0, (options, r.stdout + r.stderr)
        r = lancer(sale, options)
        assert r.returncode == 1, (options, r.stdout + r.stderr)
        assert "::error::un cache Python sous template/scripts/modele" in r.stdout, options
        r = lancer(absent, options)
        assert r.returncode == 1, (options, r.stdout + r.stderr)
        assert "::error::template/scripts/modele illisible" in r.stdout, options


def test_conftest_coupe_le_cache(tmp_path):
    """AM-1 : `tests/conftest.py` coupe le cache des imports des tests, et celui des scripts qu'ils
    lancent en sous-processus. Vérifié aussi dans un interprète neuf, sans `-B` ni la variable : un
    script importé plus tôt par la suite pose lui-même `sys.dont_write_bytecode`, et la variable
    peut venir de l'environnement du lancement."""
    assert sys.dont_write_bytecode is True
    assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    # Le cache de `conftest.py` lui-même s'écrit avant que son corps ne s'exécute : hors du dépôt.
    env["PYTHONPYCACHEPREFIX"] = str(tmp_path / "cache")
    code = (
        "import os, sys; sys.path.insert(0, sys.argv[1]); import conftest; "
        "print(sys.dont_write_bytecode, os.environ.get('PYTHONDONTWRITEBYTECODE'))"
    )
    r = subprocess.run(
        [sys.executable, "-c", code, str(RACINE / "tests")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["True", "1"], r.stdout + r.stderr


def test_mecanique_et_fausse_app_dans_la_ci_du_depot_modele():
    """R17 : seul le job mecanique lance les bats ; fausse-app passe l'action d'image d'un rendu."""
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]

    def commandes(job):
        return [e["run"] for e in jobs[job]["steps"] if "run" in e]

    (pytest_tests,) = [c for c in commandes("tests") if "pytest" in c]
    assert pytest_tests == "python -m pytest -q --ignore=tests/test_mecanique.py"
    installation = next(c for c in commandes("tests") if "sans_saut=" in c)
    listes = [set(s.split(",")) for s in re.findall(r"sans_saut=(\S+)", installation)]
    # Windows, puis Ubuntu. bash : les étapes de CI lancées par test_ci_serveur.py (R20).
    assert listes == [
        {"sops", "age", "age-keygen", "powershell", "bash"},
        {"sops", "age", "age-keygen", "pwsh", "shellcheck", "bash"},
    ]

    mecanique = jobs["mecanique"]
    assert mecanique["runs-on"] == "ubuntu-latest"
    (bats,) = [e for e in mecanique["steps"] if "test_mecanique" in e.get("run", "")]
    assert bats["run"] == "python -m pytest -q tests/test_mecanique.py"
    assert bats["env"] == {"MODELE_TESTS_SANS_SAUT": "1"}

    fausse_app = jobs["fausse-app"]
    etapes = fausse_app["steps"]
    assert fausse_app["runs-on"] == "ubuntu-latest"
    texte = "\n".join(commandes("fausse-app"))
    for fragment in (
        "copier copy --vcs-ref HEAD --defaults --trust",
        "--data nom=fausse-app",
        "--data cible=serveur",
        # la chaîne à deux dépôts (M-0006, § 6) : la fausse app est un dépôt de code
        "--data nature=code",
        # explicite : la preuve de la sauvegarde ne dépend pas d'un défaut de copier.yml (R20)
        "--data sauvegardes=true",
        ". rendu",
        # les dossiers d'exemple compris
        "cp -R tests/modele/fausse-app/. rendu/",
    ):
        assert fragment in texte, fragment
    # L'instance (le domaine, le bloc de ports) vit dans le dépôt de données, que l'épreuve fabrique.
    for absent in ("nature=donnees", "bloc_ports", "domaine="):
        assert absent not in texte, absent
    (rendre,) = [e for e in etapes if "copier copy" in e.get("run", "")]
    # projet.env déclare les deux commandes de l'instance, que verifier-image.sh lance sur l'exemple
    # et deployer.sh sur les instantanés.
    for ligne in ("VERIFIER_CONFIG=verifier-config", "VERIFIER_CONTENU=verifier-contenu"):
        assert ligne in rendre["run"], ligne
    assert "rendu/deploiement/projet.env" in rendre["run"]
    (construire,) = [e for e in etapes if "uses" in e and "modele-image" in e["uses"]]
    assert construire == {
        "uses": "./rendu/.github/actions/modele-image-construire",
        "with": {"dossier": "rendu"},
    }
    assert etapes.index(rendre) < etapes.index(construire)
    # L'épreuve du ménage des images (#19), sur le vrai Docker du job, après la construction.
    (epreuve,) = [e for e in etapes if "epreuve-menage" in e.get("run", "")]
    assert epreuve["run"] == "bash tests/modele/epreuve-menage.sh rendu"
    assert etapes.index(construire) < etapes.index(epreuve)
    # L'épreuve des données (#64), la chaîne à deux dépôts, sur l'image construite.
    (donnees,) = [e for e in etapes if "epreuve-donnees.sh" in e.get("run", "")]
    assert donnees["run"] == "bash tests/modele/epreuve-donnees.sh rendu"
    assert etapes.index(construire) < etapes.index(donnees)
    # Le registre et les conteneurs des épreuves sont retirés quoi qu'il arrive, puis la fausse app :
    # ce dernier retrait ferme le job.
    (menage,) = [e for e in etapes if "epreuve-registre" in e.get("run", "")]
    assert menage["if"] == "always()"
    assert "docker rm -f -v epreuve-registre epreuve-conteneur" in menage["run"]
    for nom in ("epreuve-donnees-registre", "fausse-app-app-1", "fausse-app-staging-app-1"):
        assert nom in menage["run"], nom
    assert etapes.index(epreuve) < etapes.index(menage)
    assert etapes.index(donnees) < etapes.index(menage)
    assert etapes[-1]["if"] == "always()"
    assert etapes[-1]["run"] == "docker rm -f -v fausse-app"
    assert etapes.index(menage) < len(etapes) - 1


EPREUVE_DONNEES = RACINE / "tests/modele/epreuve-donnees.sh"


def test_l_epreuve_des_donnees_epingle_sops():
    """sops vient de sa publication, à une version épinglée, et son empreinte est vérifiée avant
    usage ; age vient d'apt. Aucune clé ni aucun secret n'est écrit dans l'épreuve : ils naissent
    au moment où elle tourne."""
    texte = EPREUVE_DONNEES.read_text(encoding="utf-8")
    assert re.search(r"^SOPS_VERSION=\d+\.\d+\.\d+$", texte, re.MULTILINE)
    assert re.search(r"^SOPS_EMPREINTE=[0-9a-f]{64}$", texte, re.MULTILINE)
    # Dans cet ordre : le téléchargement, le contrôle de l'empreinte, puis seulement le bit
    # d'exécution et l'entrée dans le PATH, avant le premier appel de sops.
    telechargement = texte.index("https://github.com/getsops/sops/releases/download/")
    controle = texte.index("sha256sum -c")
    executable = texte.index('chmod +x "$OUTILS/sops"')
    chemin = texte.index('export PATH="$OUTILS:$PATH"')
    premier_appel = min(m.start() for m in re.finditer(r"\bsops (?:encrypt|--version)\b", texte))
    assert telechargement < controle < executable < premier_appel
    assert controle < chemin < premier_appel
    assert "apt-get install -y -qq age" in texte
    assert "age-keygen -o" in texte
    assert not re.search(r"age1[0-9a-z]{58}", texte)
    assert "AGE-SECRET-KEY" not in texte


def test_l_epreuve_des_donnees_part_d_un_dossier_vide():
    """Sur le serveur, le dossier de données de l'hôte est vide au premier déploiement, et cache le
    /donnees de l'image. L'épreuve ne le sème donc pas : elle constate qu'il est vide avant le
    premier déploiement de chaque environnement, et que l'app y a semé MARQUE après."""
    texte = EPREUVE_DONNEES.read_text(encoding="utf-8")
    assert '/MARQUE"' not in texte.split('echo "== 1.', 1)[0]
    assert not re.search(r"printf '[^']*' >\"\$TRAVAIL/donnees/", texte)
    for env in ("prod", "staging"):
        assert (
            f'verifier "le dossier de données de {env} est vide avant le premier déploiement"'
            in texte
        )
        assert f'verifier "MARQUE semée par l\'app dans le dossier de données de {env}"' in texte
    # le constat suit le déploiement de chaque environnement
    for point, env in (("1", "prod"), ("6", "staging")):
        bloc = texte.split(f'echo "== {point}.', 1)[1].split("fin_du_point", 1)[0]
        avant = bloc.index(f'vide avant le premier déploiement" vide "$DONNEES_{env.upper()}"')
        deploiement = bloc.index(f"deployer {point} {env} ")
        apres = bloc.index(f"MARQUE semée par l'app dans le dossier de données de {env}")
        assert avant < deploiement < apres, env


def test_sops_a_le_meme_epinglage_dans_l_epreuve_et_dans_le_job_tests():
    """L'épinglage de sops est écrit deux fois : l'épreuve des données et le job tests de la CI. Les
    deux disent la même version et la même empreinte du binaire linux amd64."""
    texte = EPREUVE_DONNEES.read_text(encoding="utf-8")
    version = re.search(r"^SOPS_VERSION=(\S+)$", texte, re.MULTILINE).group(1)
    empreinte = re.search(r"^SOPS_EMPREINTE=(\S+)$", texte, re.MULTILINE).group(1)
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    (installer,) = [e for e in jobs["tests"]["steps"] if e.get("name") == "Installer sops et age"]
    base = re.search(
        r"^SOPS_BASE=https://github\.com/getsops/sops/releases/download/v(\S+)$",
        installer["run"],
        re.MULTILINE,
    )
    assert base and base.group(1) == version
    assert f'"$SOPS_BASE/sops-v{version}.linux.amd64"' in installer["run"]
    assert re.findall(r"^\s*([0-9a-f]{64})  sops$", installer["run"], re.MULTILINE) == [empreinte]


def test_claude_md_du_depot_modele():
    premiere = (RACINE / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[0]
    assert premiere == "@template/docs/modele/methode.md"


def test_claude_md_dit_la_commande_des_plans():
    """Les plans du modèle vivent hors du dépôt, où l'étape « Les plans » de la CI ne les voit
    pas : « Commandes » donne la commande qui les vérifie, avec le clone voisin de `serveur`."""
    texte = (RACINE / "CLAUDE.md").read_text(encoding="utf-8")
    commandes = " ".join(texte.split("\n## Commandes\n", 1)[1].split("\n## ", 1)[0].split())
    assert (
        "`python -B template/scripts/modele/plan.py --racine . "
        "--depot serveur=C:\\src\\github.com\\EdouardZemb\\serveur <plan>`"
    ) in commandes
    assert "`Documents\\00-boite-de-reception\\`" in commandes
    assert "avant de soumettre un plan à Edouard et après chaque correction" in commandes


def test_hooks_du_depot_modele():
    hooks = sorted((RACINE / ".githooks").iterdir())
    assert {h.name for h in hooks} == {"pre-commit", "commit-msg", "pre-push"}
    for hook in hooks:
        assert "template/scripts/modele/" in hook.read_text(encoding="utf-8"), hook.name
    pre_commit = (RACINE / ".githooks/pre-commit").read_text(encoding="utf-8")
    assert "template/scripts/modele/masques.py" in pre_commit
    assert pre_commit.index("masques.py") < pre_commit.index("confidentialite.py")
    assert "--branche main" in (RACINE / ".githooks/pre-push").read_text(encoding="utf-8")


def test_depot_modele_passe_sa_porte(env_isole):
    """Le dépôt modèle est un dépôt de code : son arbre entier passe sa propre porte, règle des
    chemins de l'instance et clé publique `age` comprises, sans exception (M-0006, § 3)."""
    suivis = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
        cwd=RACINE,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    chemins = [c for c in suivis.split("\0") if c]
    assert "template/scripts/modele/confidentialite.py" in chemins
    r = subprocess.run(
        [sys.executable, str(RACINE / "template/scripts/modele/confidentialite.py")]
        + ["--fichiers", *chemins],
        cwd=RACINE,
        env=env_isole(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stderr


def test_documentation_du_depot_modele(env_isole):
    """La licence et la carte passent sur ce dépôt, lancées comme en CI, depuis la racine : son
    README lie `CLAUDE.md`, le seul autre `.md` de sa racine, et son `LICENSE` est là. Un
    `CLAUDE.local.md` posé dans un clone du modèle (par `/memory`) n'y est pas compté : le
    `.gitignore` de ce dépôt l'exclut, comme celui des projets, sans l'ignore global du poste."""
    ignores = (RACINE / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "CLAUDE.local.md" in ignores
    git = subprocess.run(
        ["git", "check-ignore", "-q", "CLAUDE.local.md"], cwd=RACINE, env=env_isole(), check=False
    )
    assert git.returncode == 0, "git n'ignore pas CLAUDE.local.md à la racine du modèle"
    r = subprocess.run(
        [sys.executable, str(RACINE / "template/scripts/modele/documentation.py")],
        cwd=RACINE,
        env=env_isole(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == [
        "documentation : licence : LICENSE présent (nature code)",
        "documentation : carte : 1 fichier .md à la racine, lié",
    ]


def test_licence_du_depot_modele(rendre):
    """Le `LICENSE` de ce dépôt est celui d'un rendu par défaut, à l'octet près. Par empreinte,
    pour qu'un échec n'imprime pas les deux textes."""
    depot = hashlib.sha256((RACINE / "LICENSE").read_bytes()).hexdigest()
    rendu = hashlib.sha256((rendre() / "LICENSE").read_bytes()).hexdigest()
    assert depot == rendu


COMMENTAIRE_HTML = re.compile(r"<!--.*?-->|<pre\b.*?</pre>", re.DOTALL | re.IGNORECASE)


def visible(texte: str) -> str:
    """Un texte Markdown sans ce que GitHub n'y affiche pas comme du texte : ses blocs de code
    clôturés, ses commentaires HTML et ses blocs `<pre>`."""
    return COMMENTAIRE_HTML.sub("", CLOTURE.sub("", texte))


def sections(texte: str) -> dict[str, str]:
    """Le corps de chaque titre `##` d'un texte, jusqu'au titre `##` suivant ; sous `""`, ce qui
    précède le premier."""
    morceaux = re.split(r"^## (.+)\n", texte, flags=re.MULTILINE)
    return {"": morceaux[0], **dict(zip(morceaux[1::2], morceaux[2::2], strict=True))}


def test_readme_nomme_chaque_reponse_a_choix():
    """Le README nomme chaque réponse à choix de `copier.yml` et chacun de ses choix, entre accents
    graves, sous « Démarrer », dans un élément de liste de premier niveau, ouvert en colonne 0
    comme l'écrit le README (une puce indentée peut être imbriquée sous une autre), d'une seule
    ligne, qu'ouvre sa question. Les choix se lisent dans `copier.yml`, la liste ou les valeurs du
    dictionnaire (pas ses libellés). Entre accents graves et sur la ligne de la question : une
    recherche nue passerait à vide, « code » ou « serveur » paraissant partout ; une puce qui
    nommerait plusieurs questions, ou une question nommée dans la puce d'une autre, ne rattacherait
    pas ses choix à leur question. Une liste dans un bloc de code, indenté ou clôturé, dans un bloc
    `<pre>` ou dans un commentaire HTML ne compte pas : GitHub ne l'affiche pas comme une liste."""
    a_choix = {
        nom: question["choices"]
        for nom, question in COPIER.items()
        if isinstance(question, dict) and "choices" in question
    }
    assert sorted(a_choix) == ["cible", "cible_code", "fusion", "nature"]
    demarrer = sections(visible((RACINE / "README.md").read_text(encoding="utf-8")))
    lignes = demarrer.get("Démarrer", "").splitlines()
    for nom, choix in a_choix.items():
        valeurs = list(choix.values()) if isinstance(choix, dict) else list(choix)
        assert valeurs, nom
        tete = rf"[-*+] `{re.escape(nom)}`"
        propres = [ligne for ligne in lignes if re.match(tete, ligne)]
        assert any(all(f"`{valeur}`" in ligne for valeur in valeurs) for ligne in propres), (
            nom,
            valeurs,
        )


def test_readme_du_depot_modele():
    """Le README de ce dépôt a la forme de la variante « code » : une phrase d'ouverture ; ses
    titres, dans l'ordre, ceux de « Démarrer » compris ; « Pourquoi » qui renvoie à l'état de
    `CLAUDE.md` et aux publications ; la colonne « À lire quand » ; la phrase de « Contribuer » ;
    `[MIT](LICENSE)` ; rien qui se périme ; il lie `CLAUDE.md`, `docs/aligner.md` et `LICENSE`, et
    chaque lien relatif (une ancre seule comprise) et chaque ancre mènent à un fichier et à un titre
    de ce dépôt, à la casse près, comme sur GitHub. Les titres se lisent dans ce que GitHub affiche,
    hors des blocs de code et des commentaires HTML."""
    texte = (RACINE / "README.md").read_text(encoding="utf-8")
    titres = re.findall(r"^## (.+)$", visible(texte), flags=re.MULTILINE)
    assert titres == ["Pourquoi", "Démarrer", "Où lire quoi", "Contribuer", "Licence"]
    corps = sections(visible(texte))
    ouverture = re.sub(r"^# .*$", "", corps[""], flags=re.MULTILINE).strip()
    assert ouverture.endswith("."), "pas de phrase d'ouverture avant « Pourquoi »"
    # Ce qu'est le modèle, et pour qui.
    assert "d'où naissent les projets d'Edouard" in " ".join(ouverture.split()), ouverture
    assert re.search(r"\bpour\b", ouverture), ouverture
    pourquoi = documentation.liens(corps["Pourquoi"], texte)
    assert "CLAUDE.md#état" in pourquoi, pourquoi
    assert "https://github.com/EdouardZemb/modele-projet/releases" in pourquoi, pourquoi
    assert re.findall(r"^### (.+)$", corps["Démarrer"], flags=re.MULTILINE) == [
        "Créer un projet",
        "Mettre à jour un projet",
        "Aligner un projet existant",
    ]
    # En début de ligne : un bloc indenté, que GitHub rend en code, ne compte pas.
    entete = r"^ {0,3}\| Document \| À lire quand \|$"
    assert re.search(entete, corps["Où lire quoi"], re.MULTILINE)
    contribuer = r"^ {0,3}Projet personnel : aucune contribution n'est attendue\.$"
    assert re.search(contribuer, corps["Contribuer"], re.MULTILINE)
    assert re.search(r"^ {0,3}\[MIT\]\(LICENSE\)$", corps["Licence"], re.MULTILINE)
    perime = PERIMES.search(texte)
    assert perime is None, perime
    liens = documentation.liens(texte)
    relatifs = [lien for lien in liens if not SCHEMA.match(lien)]
    locaux = {documentation.cible_locale(lien, RACINE) for lien in relatifs}
    assert {"CLAUDE.md", "docs/aligner.md", "LICENSE"} <= locaux, locaux
    assert any("#" in lien for lien in relatifs), relatifs
    casses = [lien for lien in relatifs if lien_casse(RACINE, "README.md", lien)]
    assert not casses, casses


def test_readme_dit_qu_un_seme_absent_revient():
    """« Mettre à jour un projet » dit, comme la méthode, qu'un semé absent revient à la mise à
    jour, et d'indexer le `LICENSE` qu'elle crée."""
    corps = sections(visible((RACINE / "README.md").read_text(encoding="utf-8")))
    maj = corps["Démarrer"].split("### Mettre à jour un projet", 1)[1].split("\n### ", 1)[0]
    plat = " ".join(maj.split())
    assert (
        "un semé présent n'est pas touché, mais un semé absent, retiré ou nouveau dans le modèle "
        "comme `LICENSE`, est semé à neuf"
    ) in plat
    assert "(`git add LICENSE`)" in plat
    assert "les fichiers semés ne sont pas touchés" not in plat


def test_aides_de_copier_yml():
    """Les aides de `description` et de `cible` valent celles que pose la spec du lot 14 :
    `description` dit ce qu'attend la première phrase du README ; `cible` ne promet aucune cible à
    venir, ni par un lot, ni par la cible statique (des mots entiers : « pilote » n'est pas un
    lot)."""
    assert COPIER["description"]["help"] == "Le projet en une phrase : ce que c'est, et pour qui"
    aide = COPIER["cible"]["help"]
    assert aide == "Ce que le modèle rend (aucune, serveur, ou donnees pour un dépôt de données)"
    assert re.search(r"\b(lots?|statiques?)\b", aide, flags=re.IGNORECASE) is None, aide


def test_exemples_de_description_suivent_l_aide():
    """Les exemples de `-Description`, dans ce README et dans l'aide du script du poste, disent
    comme l'aide de `description` ce qu'est le projet, et pour qui, et non ce qu'il fait. Un
    exemple sans un mot (`"..."`, `"<…>"`) ne compte pas ; chaque fichier en a au moins un."""
    for chemin in ("README.md", "poste/Nouveau-Projet.ps1"):
        texte = (RACINE / chemin).read_text(encoding="utf-8-sig")
        exemples = [e for e in re.findall(r'-Description "([^"]*)"', texte) if re.search(r"\w", e)]
        assert exemples, chemin
        assert all(
            "pour qui" in e and re.search(r"\bce qu'est\b", e, re.IGNORECASE) for e in exemples
        ), (chemin, exemples)


def test_settings_du_depot_modele():
    reglage = json.loads((RACINE / ".claude/settings.json").read_text(encoding="utf-8"))
    crochet = reglage["hooks"]["PreToolUse"][0]
    assert crochet["matcher"] == "Bash|PowerShell|Monitor|mcp__.*"
    assert "template/scripts/modele/garde_claude.py" in crochet["hooks"][0]["command"]
    assert "--branche main --fusion session" in crochet["hooks"][0]["command"]
    (groupe,) = reglage["hooks"]["SessionStart"]
    assert groupe["matcher"] == "startup|resume"
    (signaux,) = groupe["hooks"]
    assert signaux["timeout"] == 30
    assert "template/scripts/modele/signaux.py" in signaux["command"]
    assert signaux["command"].endswith("--branche main")


def test_dependabot_du_depot_modele():
    """Les épinglages du dépôt et des workflows gérés (revue finale, I6) montent dans la même PR.

    Une PR par dossier ne peut pas passer : test_ci_du_depot_modele_suit_le_socle exige les mêmes
    étapes des deux côtés.
    """
    doc = yaml.safe_load((RACINE / ".github/dependabot.yml").read_text(encoding="utf-8"))
    actions = [u for u in doc["updates"] if u["package-ecosystem"] == "github-actions"]
    assert len(actions) == 1
    assert actions[0]["directories"] == ["/", "/template/.github/workflows"]
    assert "directory" not in actions[0]
    groupes = actions[0]["groups"]
    assert [g["group-by"] for g in groupes.values()] == ["dependency-name"]
    assert list((RACINE / "template/.github/workflows").glob("*.yml"))
    # L'image de la fausse app, épinglée par empreinte, suit aussi ses versions (V8), sans majeure.
    (docker,) = [u for u in doc["updates"] if u["package-ecosystem"] == "docker"]
    assert docker["directory"] == "/tests/modele/fausse-app"
    assert (RACINE / "tests/modele/fausse-app/Dockerfile").is_file()
    for cle in ("schedule", "cooldown", "commit-message"):
        assert docker[cle] == actions[0][cle]
    assert docker["ignore"] == [
        {"dependency-name": "*", "update-types": ["version-update:semver-major"]}
    ]


def test_historique_du_depot_modele():
    """Les étapes du workflow du dépôt modèle sont celles du modèle, chemins préfixés."""
    modele = yaml.safe_load(
        (RACINE / "template/.github/workflows/modele-historique.yml").read_text(encoding="utf-8")
    )
    racine = yaml.safe_load(
        (RACINE / ".github/workflows/historique.yml").read_text(encoding="utf-8")
    )
    attendues = [
        {**e, "run": e["run"].replace("scripts/modele/", "template/scripts/modele/")}
        if "run" in e
        else e
        for e in modele["jobs"]["historique"]["steps"]
    ]
    assert racine["jobs"]["historique"]["steps"] == attendues
    assert any("template/scripts/modele/confidentialite.py" in e.get("run", "") for e in attendues)
    for cle in ("on", True, "permissions", "name"):
        assert racine.get(cle) == modele.get(cle)


def test_texte_pr_du_depot_modele():
    """Le dépôt modèle applique le workflow géré du texte de la PR : mêmes déclencheurs,
    permissions, concurrence, nom et job, chaque `run` préfixé de `template/`."""
    modele = yaml.safe_load(
        (RACINE / "template/.github/workflows/modele-texte-pr.yml").read_text(encoding="utf-8")
    )
    racine = yaml.safe_load(TEXTE_PR.read_text(encoding="utf-8"))
    attendues = [
        {**e, "run": e["run"].replace("scripts/modele/", "template/scripts/modele/")}
        if "run" in e
        else e
        for e in modele["jobs"]["texte-pr"]["steps"]
    ]
    assert racine["jobs"] == {"texte-pr": {**modele["jobs"]["texte-pr"], "steps": attendues}}
    assert any("template/scripts/modele/texte_pr.py" in e.get("run", "") for e in attendues)
    for cle in ("on", True, "permissions", "concurrency", "name"):
        assert racine.get(cle) == modele.get(cle), cle
    # l'en-tête aussi, après sa première ligne (« Géré par le modèle »), que la copie remplace par
    # deux lignes qui disent d'où elle vient
    gere = RACINE / "template/.github/workflows/modele-texte-pr.yml"
    entetes = [
        [ligne for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne[:1] == "#"]
        for chemin in (TEXTE_PR, gere)
    ]
    assert entetes[0][2:] == entetes[1][1:]


def test_ci_ne_revoit_plus_une_pr_modifiee(rendre):
    """Seul `texte-pr` écoute `edited` (AM-2) : une retouche du titre ou du corps d'une PR ne
    relance plus toute la CI, ni ici, ni dans un projet à naître. Aucun job du socle ne lit plus le
    corps de la PR."""
    rendus = [
        rendre() / ".github/workflows/ci.yml",
        rendre(cible="serveur") / ".github/workflows/ci.yml",
        rendre(nom="essai-donnees", cible="donnees") / ".github/workflows/ci.yml",
    ]
    for chemin in (CI, *rendus):
        doc = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        on = doc.get("on", doc.get(True))
        assert on["pull_request"]["types"] == ["opened", "synchronize", "reopened"], chemin
    for chemin in (CI, RACINE / "template/.github/workflows/modele-socle.yml"):
        assert "github.event.pull_request.body" not in chemin.read_text(encoding="utf-8"), chemin


def test_ci_du_depot_modele_suit_le_socle():
    """Les étapes du job confidentialite du dépôt modèle sont celles du socle, chemins préfixés."""
    socle = yaml.safe_load(
        (RACINE / "template/.github/workflows/modele-socle.yml").read_text(encoding="utf-8")
    )
    racine = yaml.safe_load(CI.read_text(encoding="utf-8"))
    attendues = [
        {**e, "run": e["run"].replace("scripts/modele/", "template/scripts/modele/")}
        if "run" in e
        else e
        for e in socle["jobs"]["confidentialite"]["steps"]
    ]
    assert racine["jobs"]["confidentialite"]["steps"] == attendues


def test_liste_d_alignement():
    texte = (RACINE / "docs/aligner.md").read_text(encoding="utf-8")
    assert texte.splitlines()[0] == "# Aligner un projet existant sur le modèle"
    for fragment in (
        "copier copy --defaults --vcs-ref",
        "git diff --name-only",
        "@docs/modele/methode.md",
        # lot 14 : le README à la forme de sa variante, et la licence d'un dépôt de code
        "docs/modele/documentation.md",
        "`LICENSE`",
        "needs:",
        "edited",
        # lot 15 : `edited` se retire, `texte-pr` l'écoute seul ; la règle existante se met à jour
        "retirer `edited`",
        "texte-pr",
        "PUT",
        "`.claude/settings.local.json`, `CLAUDE.local.md` et `__pycache__/`",
        # Le remède de la porte des masqués, ancré (#95, ronde 2).
        "le remède que donne la porte, des lignes ancrées qui n'admettent que ce qu'elle examine",
        # Un semé sous un ancêtre levé reste masqué : la porte ne l'examine pas (#95, ronde 3).
        "Un semé (`docs/cadrage.md`, `.github/workflows/ci.yml`…) sous un dossier exclu",
        # Le chemin tel que git le montre : un dossier se lève tout entier (#95, ronde 4).
        "que `git status --short --ignored` le montre : un dossier (`docs/decisions/`) se lève ainsi",
        "`.githooks` et `scripts/modele`",
        "excluent les chemins",
        "extensions.worktreeConfig",
        "--app dependabot",
        "squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY",
        "ruleset-main.json",
        "gh workflow run modele-historique.yml",
        "en avance rapide",
        "--dry-run",
        "aucune PR",
        "## Passer un dépôt en public",
        "--data nature=<code|donnees>",
        "la scission (M-0006, § 7)",
        "gh run list --branch",
        "--exiger-prives --index",
        ".gitleaksignore",
        # passer en cible serveur (lot 2)
        "## Passer en cible `serveur`",
        "--data cible=serveur",
        "modele-image-construire",
        "modele-version.yml",
        "se fusionne à la main",
        "--data fusion=<session|edouard>",
        "que le modèle ne sème pas",
        # V10 : les fichiers semés que le projet a déjà ne reçoivent rien de copier update
        "les deux blocs `package-ecosystem: docker` de `.github/dependabot.yml`",
        "a déjà un `docs/exploitation.md`",
        # I3 : activer les sauvegardes sur un projet en service
        "### Activer les sauvegardes sur un projet en service",
        "--data sauvegardes=true",
        "`SAUVEGARDER=<mots>` et `VERIFIER=<mots>`",
        "`HC_TEST_RESTAURATION`",
        "`TEST_RESTAURATION` à `projets/<nom>.env`",
        "Le premier déploiement ne prend pas d'instantané",
        # C0 : un état qu'une restauration ne doit pas défaire
        "déclare `REPORTER` et `REPORTER_SECTION` dans `deploiement/projet.env`",
        # revue finale du lot 2 (M6) : le tunnel d'un projet, ses instantanés d'avant l'alignement
        "**Un projet qui a déjà son propre tunnel**",
        "`--remove-orphans`",
        "« Faire passer une route d'un tunnel à un autre »",
        "**Les instantanés d'avant l'alignement**",
        # tout l'ancien deploiement/ : l'ancien restaurer.sh charge sa lib.sh à côté de lui
        "archive <commit> deploiement | tar -x -C <dossier temporaire>",
        # lot 12 : la porte par chemins, ce qui nomme l'instance selon la nature, l'instance lue
        "`instance/`, `config/` ou `contenu/` à la racine",
        "**Ce qui nomme l'instance dépend de la nature**",
        "`--data domaine=<domaine> --data bloc_ports=<bloc>`",
        "**Ses clés publiques ne servent qu'au premier rendu**",
        "sans entrer dans `.copier-answers.yml`",
        "**Une application qui lit son instance**",
        "`instance/config/` et `instance/contenu/`",
        "**La règle des paires**",
    ):
        assert fragment in texte, fragment
    a_plat = " ".join(texte.split())
    for regle in (
        # la CI du code exige l'exemple de chaque commande déclarée
        "La CI du code y lance la commande, et refuse une commande déclarée sans son exemple",
        # à deux dépôts, la CI des données clone le code sans jeton : il est public avant elle
        (
            "sa CI clone le dépôt de code sans jeton et tire son image `:main` : le dépôt de code "
            "est donc public, et son image publiée et publique, avant elle"
        ),
        # à un dépôt, la CI du code vérifie instance/ comme le fera le déploiement
        (
            "La CI du code vérifie `instance/` comme le fera le déploiement : la règle des paires, "
            "puis chaque commande déclarée sur son dossier ; le déploiement revérifie"
        ),
        # lot 14 : la PR d'alignement d'un dépôt privé de données est jugée en régime code en CI
        (
            "Dans un dépôt privé de nature `donnees`, la PR d'alignement est jugée en régime "
            "`code` en CI, puisque sa branche par défaut ne porte pas encore `NATURE` : l'étape "
            "« La documentation de la racine » y refuse la licence, et 👤 Edouard fusionne cette "
            "PR, comme celle qui apporte `fusion`."
        ),
        (
            "Dans un dépôt privé de nature `donnees`, `socle / confidentialite` y est rouge, par "
            "la licence"
        ),
        # une licence sous un autre nom, que Copier doublerait
        (
            "Une licence déjà présente sous un autre nom (`LICENSE.md`, `COPYING`…) se renomme en "
            "`LICENSE` avant le `copier copy`, sinon Copier en pose une seconde, MIT. La section "
            "« Licence » du README nomme la licence du fichier."
        ),
        # le lancement local ne dit ce que dira la CI qu'une fois tout indexé et validé
        "dit ce que la CI dira, LICENSE indexé, README et `CLAUDE.md` validés",
    ):
        assert regle in a_plat, regle
    assert "ne lit pas `instance/`" not in a_plat
    # un --data d'une question que le projet ne se voit pas poser n'entre pas dans ses réponses :
    # le bloc de ports ne s'ajoute qu'aux dépôts qui portent leur instance (lot 12)
    assert "--data cible=serveur --data bloc_ports=<bloc>" not in texte
    # le seul script ne suffit pas, il lui faut son arbre (revue des corrections du lot 2, I2)
    assert ":deploiement/restaurer.sh` dans un fichier temporaire" not in texte
    # avant le commit, --diff compare <base>...HEAD et n'examine rien (LE-15)
    assert "--exiger-prives --diff" not in texte
    # la liste suit la méthode, qui n'indexe que par chemins explicites
    for tout_indexer in ("git add -A", "git add ."):
        assert tout_indexer not in texte, tout_indexer
    assert "git add -- <chemins>" in texte
    # lot 15 : une règle qui existe déjà se met à jour après la fusion (§ 7), jamais avant la PR
    # (§ 6), puis les PR de Dependabot ouvertes se relancent
    six = texte.split("\n## 6. ", 1)[1].split("\n## ", 1)[0]
    sept = texte.split("\n## 7. ", 1)[1].split("\n## ", 1)[0]
    assert "PUT" not in six
    put = sept.index("gh api -X PUT repos/<dépôt>/rulesets/<id>")
    assert sept.index("Fusion en squash") < put < sept.index("@dependabot rebase")
    # la mise à jour est à Edouard (👤) ; la relecture de la règle et la relance des PR de
    # Dependabot, à la session, dans la case qui suit, sans 👤 (ronde 3)
    cases = sept.split("\n- [ ] ")[1:]
    (mise_a_jour,) = [case for case in cases if "gh api -X PUT" in case]
    assert mise_a_jour.startswith("👤 ")
    assert "@dependabot rebase" not in mise_a_jour
    suivante = cases[cases.index(mise_a_jour) + 1]
    assert "👤" not in suivante
    for fragment in ("gh api repos/<dépôt>/rulesets/<id>", "`texte-pr`", "@dependabot rebase"):
        assert fragment in suivante, fragment
    sept = " ".join(sept.split())
    assert "Un `POST` crée une règle ; il ne met pas à jour celle qui existe." in sept
    assert "en créerait une seconde" not in texte
    # le modèle de PR que propose GitHub vient de la branche par défaut, encore sans la section
    assert (
        "le modèle de PR que propose GitHub est celui de la branche par défaut, encore sans la "
        "section « Écarts à la spec » : l'écrire à la main dans le corps, `## Écarts à la spec` "
        "puis « Aucun. », ou les écarts"
    ) in sept
    for lien in ("CLAUDE.md", "README.md"):
        assert "docs/aligner.md" in (RACINE / lien).read_text(encoding="utf-8"), lien


def test_aucun_passage_planifie_ne_lit_le_contexte_du_depot():
    """Sur un déclenchement `schedule`, `github.event.repository` peut manquer : la visibilité
    se lit par l'API, pas par ce contexte."""
    planifies = []
    for dossier in (RACINE / "template/.github/workflows", RACINE / ".github/workflows"):
        for chemin in dossier.iterdir():
            texte = chemin.read_text(encoding="utf-8")
            if re.search(r"^\s+schedule:", texte, re.MULTILINE):
                planifies.append(chemin)
                assert "github.event.repository" not in texte, chemin.name
    assert len(planifies) >= 2
