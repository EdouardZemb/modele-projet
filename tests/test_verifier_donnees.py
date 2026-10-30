"""verifier_donnees.py : un dépôt de données, vérifié contre les images de son dépôt de code
(M-0006, § 8), comme le serveur vérifie un couple (deploiement/lib.sh).

Le banc : un dépôt de données, avec le script et un reglages.py qui porte DEPOT_CODE ; le clone du
dépôt de code dans son dossier `code/`, comme le checkout de modele-donnees.yml ; un faux `docker`
en tête du PATH, qui note chaque appel et ce que chaque montage portait au moment de l'appel.
"""

import json
import os
import re
import shutil
import subprocess
import sys

import pytest
import verifier_donnees
from conftest import REPONSES_SERVEUR_CODE, SCRIPTS, git

COMPTE = "Compte-Essai"
BASE = "ghcr.io/compte-essai/essai"
DEUX_COMMANDES = "VERIFIER_CONFIG=verifier-config\nVERIFIER_CONTENU=verifier-contenu --strict\n"
JETABLES = [
    "--user", "1000:1000", "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true", "--memory", "384m",
]  # fmt: skip

# Le faux docker : chaque appel est une ligne JSON de `journal.jsonl` ; un `run` y note aussi son
# image, sa commande et, pour chaque montage, son mode et les fichiers de sa source à ce moment-là.
# `reglages.json` dit les images absentes du registre, et le code et la sortie de chaque commande,
# par « <image> <premier mot de la commande> ».
FAUX_DOCKER = r"""
import json
import sys
from pathlib import Path

ici = Path(__file__).parent
reglages = json.loads((ici / "reglages.json").read_text(encoding="utf-8"))
args = sys.argv[1:]
appel = {"args": args}
image, commande = None, []
if args[:1] == ["run"]:
    montages = {}
    i = 1
    while i < len(args):
        if args[i] in ("--rm", "--read-only"):
            i += 1
        elif args[i].startswith("-"):
            if args[i] == "-v":
                source, cible, mode = args[i + 1].rsplit(":", 2)
                racine = Path(source)
                montages[cible] = {
                    "mode": mode,
                    "existe": racine.is_dir(),
                    "fichiers": {
                        p.relative_to(racine).as_posix(): p.read_text(encoding="utf-8")
                        for p in sorted(racine.rglob("*"))
                        if p.is_file()
                    },
                    "source": source,
                }
            i += 2
        else:
            image, commande = args[i], args[i + 1 :]
            break
    appel.update(image=image, commande=commande, montages=montages)
with (ici / "journal.jsonl").open("a", encoding="utf-8") as f:
    f.write(json.dumps(appel) + "\n")
if args[:1] == ["pull"]:
    if args[-1] in reglages.get("absentes", []):
        print(f"Error response from daemon: manifest for {args[-1]} not found", file=sys.stderr)
        sys.exit(1)
    print(args[-1] + "@sha256:" + "0" * 64)
    sys.exit(0)
if args[:1] == ["run"] and image and commande:
    cle = f"{image} {commande[0]}"
    print(reglages.get("sorties", {}).get(cle, "sortie de " + commande[0]))
    sys.exit(reglages.get("codes", {}).get(cle, 0))
print("faux docker : appel inattendu " + " ".join(args), file=sys.stderr)
sys.exit(125)
"""


def poser_faux_docker(dossier):
    """Le faux docker dans `dossier`, lancé par un lanceur que trouve shutil.which, comme faux_gh :
    un .cmd sous Windows, un script sh ailleurs."""
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "faux_docker.py").write_text(FAUX_DOCKER, encoding="utf-8")
    (dossier / "reglages.json").write_text("{}", encoding="utf-8")
    if sys.platform == "win32":
        (dossier / "docker.cmd").write_text(
            f'@echo off\r\n"{sys.executable}" "%~dp0faux_docker.py" %*\r\nexit /b %ERRORLEVEL%\r\n',
            encoding="utf-8",
            newline="",
        )
    else:
        lanceur = dossier / "docker"
        lanceur.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/faux_docker.py" "$@"\n',
            encoding="utf-8",
        )
        lanceur.chmod(0o755)


class Banc:
    """Le dépôt de données `essai-donnees`, son dépôt de code dans `code/`, et le faux docker."""

    def __init__(self, tmp_path, env, depot_code='DEPOT_CODE = "essai"\n'):
        self.env = {**env, "PYTHONUTF8": "1"}
        self.env.pop("GITHUB_REPOSITORY_OWNER", None)
        self.binaires = tmp_path / "bin"
        poser_faux_docker(self.binaires)
        self.env["PATH"] = str(self.binaires) + os.pathsep + env["PATH"]

        self.donnees = tmp_path / "essai-donnees"
        modele = self.donnees / "scripts/modele"
        modele.mkdir(parents=True)
        shutil.copy(SCRIPTS / "verifier_donnees.py", modele / "verifier_donnees.py")
        (modele / "reglages.py").write_text(
            f'BRANCHE_PRINCIPALE = "main"\nNATURE = "donnees"\n{depot_code}', encoding="utf-8"
        )
        self._init(self.donnees)
        self.code = self.donnees / "code"
        self.code.mkdir()
        self._init(self.code)

    def _init(self, depot):
        git(depot, self.env, "init", "-q", "-b", "main")
        git(depot, self.env, "config", "core.autocrlf", "false")

    def commit_du_code(self, projet_env, *etiquettes):
        """Un commit du code dont deploiement/projet.env vaut `projet_env` (None : pas de fichier),
        avec ces étiquettes."""
        chemin = self.code / "deploiement/projet.env"
        chemin.parent.mkdir(exist_ok=True)
        if projet_env is None:
            chemin.unlink(missing_ok=True)
        else:
            chemin.write_text(projet_env, encoding="utf-8", newline="\n")
        git(self.code, self.env, "add", "-A")
        git(self.code, self.env, "commit", "-q", "--allow-empty", "-m", "feat: code")
        for etiquette in etiquettes:
            git(self.code, self.env, "tag", etiquette)

    def commit_des_donnees(self, fichiers, *etiquettes):
        """Un commit des données dont config/ et contenu/ sont exactement `fichiers` (chemin -> texte),
        avec ces étiquettes. Le clone du code, à côté, n'y entre pas."""
        for dossier in ("config", "contenu"):
            shutil.rmtree(self.donnees / dossier, ignore_errors=True)
        for chemin, texte in fichiers.items():
            (self.donnees / chemin).parent.mkdir(parents=True, exist_ok=True)
            (self.donnees / chemin).write_text(texte, encoding="utf-8", newline="\n")
        git(self.donnees, self.env, "add", "-A", "--", "scripts", "config", "contenu")
        git(self.donnees, self.env, "commit", "-q", "--allow-empty", "-m", "feat: données")
        for etiquette in etiquettes:
            git(self.donnees, self.env, "tag", etiquette)

    def regler_docker(self, absentes=(), codes=None, sorties=None):
        reglages = {"absentes": list(absentes), "codes": codes or {}, "sorties": sorties or {}}
        (self.binaires / "reglages.json").write_text(json.dumps(reglages), encoding="utf-8")

    def lancer(self, *arguments, env=None):
        """`python scripts/modele/verifier_donnees.py …` à la racine du dépôt de données, comme
        modele-donnees.yml ; le journal du faux docker repart de zéro."""
        (self.binaires / "journal.jsonl").write_text("", encoding="utf-8")
        return subprocess.run(
            [sys.executable, "scripts/modele/verifier_donnees.py", *arguments],
            cwd=self.donnees,
            env={**self.env, **(env or {})},
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def appels(self):
        texte = (self.binaires / "journal.jsonl").read_text(encoding="utf-8")
        return [json.loads(ligne) for ligne in texte.splitlines()]

    def tires(self):
        return [a["args"][-1] for a in self.appels() if a["args"][:1] == ["pull"]]

    def lances(self):
        return [a for a in self.appels() if a["args"][:1] == ["run"]]


@pytest.fixture
def banc(tmp_path, env_isole):
    return Banc(tmp_path, env_isole())


def sortie(r):
    return r.stdout + r.stderr


def montages_de(appel):
    """Les montages d'un `run` : {cible: (mode, fichiers)}."""
    return {cible: (m["mode"], m["fichiers"]) for cible, m in appel["montages"].items()}


# --- Les règles de lib.sh, recopiées : un test les lie ------------------------------------------


def test_options_jetables_et_dossiers_comme_lib_sh(rendre):
    """Les options des conteneurs jetables et les dossiers de l'instance d'un dépôt de données sont
    ceux de lib.sh, à deux dépôts : une copie qui divergerait vérifierait autre chose que le
    serveur."""
    lib = (rendre(**REPONSES_SERVEUR_CODE) / "deploiement/lib.sh").read_text(encoding="utf-8")
    (options,) = re.findall(r"^ESSAI_OPTIONS_JETABLES=\(([^)]*)\)", lib, re.MULTILINE)
    assert tuple(options.split()) == verifier_donnees.OPTIONS_JETABLES
    assert tuple(JETABLES) == verifier_donnees.OPTIONS_JETABLES
    assert 'MODE_DONNEES="deux"' in lib
    debut = lib.index('if [ "$MODE_DONNEES" = deux ]; then')
    deux = lib[debut : lib.index("\nelse\n", debut)]
    assert f'SOUS_DOSSIER_CONFIG="{verifier_donnees.DOSSIER_CONFIG}"' in deux
    assert f'SOUS_DOSSIER_CONTENU="{verifier_donnees.DOSSIER_CONTENU}"' in deux


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        (None, ((), ())),
        ("", ((), ())),
        ("#VERIFIER_CONFIG=verifier-config\n", ((), ())),
        (DEUX_COMMANDES, (("verifier-config",), ("verifier-contenu", "--strict"))),
        # des espaces en trop, la dernière ligne sans fin de ligne, un commentaire
        (
            "# Réglages\n\nVERIFIER_CONFIG=  node  dist/cli.js   verifier \nVERIFIER_CONTENU=v",
            (("node", "dist/cli.js", "verifier"), ("v",)),
        ),
        # rien de déclaré : une ligne invalide ne se lit même pas (lire_projet_env_facultatif)
        ("AUTRE=a;b\nVERIFIER_CONFIG_X=x\n", ((), ())),
        # les symboles que valeur_sure accepte
        ("VERIFIER_CONFIG=a:b,c@d%e#f!g*h?i[j]k{l}m^n+o/p=q_r-s.t\n", (("a:b,c@d%e#f!g*h?i[j]k{l}m^n+o/p=q_r-s.t",), ())),
    ],
)  # fmt: skip
def test_declaration_lue_comme_lib_sh(texte, attendu):
    declaration = verifier_donnees.lire_declaration(texte, "projet.env")
    assert (declaration.config, declaration.contenu) == attendu


@pytest.mark.parametrize(
    ("texte", "message"),
    [
        ("VERIFIER_CONFIG=a;b\n", "ligne 1 invalide"),
        ("VERIFIER_CONFIG=\n", "ligne 1 invalide"),
        ("VERIFIER_CONFIG=   \n", "ligne 1 invalide"),
        ("VERIFIER_CONFIG=verifier\r\n", "ligne 1 invalide"),
        ("VERIFIER_CONFIG=verifier\tconfig\n", "ligne 1 invalide"),
        ("VERIFIER_CONFIG=$(touch x)\n", "ligne 1 invalide"),
        ("VERIFIER_CONTENU=v\nminuscule=x\n", "ligne 2 invalide"),
        ("VERIFIER_CONTENU=v\n # commentaire décalé\n", "ligne 2 invalide"),
        ("VERIFIER_CONFIG=a\nVERIFIER_CONFIG=b\n", "VERIFIER_CONFIG est déclarée deux fois"),
    ],
)
def test_declaration_illisible(texte, message):
    with pytest.raises(verifier_donnees.Illisible, match=re.escape(message)):
        verifier_donnees.lire_declaration(texte, "projet.env")


def test_plus_hautes_etiquettes():
    versions = ["v1.2.0", "v1.10.0", "v1.9.9", "v2.0", "v3.0.0-rc.1", "1.11.0", "x"]
    assert verifier_donnees.plus_haute_version(versions) == "v1.10.0"
    assert verifier_donnees.plus_haute_version(["v2.0", "main"]) is None
    donnees = [
        "donnees-2026.11.03.9",
        "donnees-2026.11.03.10",
        "donnees-2026.11.02.12",
        "donnees-2026.12.3.1",
        "donnees-2026.11.04.0",
        "donnees-2026.11.04.01",
        "v9.9.9",
    ]
    assert verifier_donnees.plus_haute_etiquette_donnees(donnees) == "donnees-2026.11.03.10"
    assert verifier_donnees.plus_haute_etiquette_donnees(["donnees-2026.11.3.1"]) is None


# --- Les images visées --------------------------------------------------------------------------


def test_images_designees_et_commandes_comme_le_serveur(banc):
    banc.commit_du_code(DEUX_COMMANDES, "v1.2.0", "v1.10.0", "v1.9.0", "v2.0", "v3.0.0-rc.1")
    banc.commit_des_donnees(
        {
            "config/README.md": "notes\n",
            "config/profil.yml": "version: 1\n",
            "contenu/page.md": "page\n",
        }
    )
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 0, sortie(r)
    # :main et l'image de la plus haute vX.Y.Z (l'étiquette X.Y.Z que publie modele-version.yml)
    assert banc.tires() == [f"{BASE}:main", f"{BASE}:1.10.0"]
    lances = banc.lances()
    assert [(a["image"], a["commande"]) for a in lances] == [
        (f"{BASE}:main", ["verifier-config", "/config"]),
        (f"{BASE}:main", ["verifier-contenu", "--strict", "/contenu"]),
        (f"{BASE}:1.10.0", ["verifier-config", "/config"]),
        (f"{BASE}:1.10.0", ["verifier-contenu", "--strict", "/contenu"]),
    ]
    # comme le serveur : conteneur jetable, sans réseau, chaque dossier de HEAD en lecture seule
    config = lances[0]
    source = config["montages"]["/config"]["source"]
    assert config["args"] == [
        "run", "--rm", "--network", "none", *JETABLES, "-v", f"{source}:/config:ro",
        f"{BASE}:main", "verifier-config", "/config",
    ]  # fmt: skip
    assert montages_de(config) == {
        "/config": ("ro", {"README.md": "notes\n", "profil.yml": "version: 1\n"})
    }
    assert montages_de(lances[1]) == {"/contenu": ("ro", {"page.md": "page\n"})}
    # l'extraction ne survit pas au contrôle
    for appel in lances:
        for montage in appel["montages"].values():
            assert montage["existe"]
            assert not os.path.exists(montage["source"]), montage["source"]
    assert "configuration conforme (VERIFIER_CONFIG" in r.stdout
    assert f"{BASE}:1.10.0 (v1.10.0)" in r.stdout


def test_le_compte(banc):
    banc.commit_du_code("", "v1.0.0")
    banc.commit_des_donnees({})
    # celui du dépôt sur GitHub, sans --compte
    r = banc.lancer("--code", "code", env={"GITHUB_REPOSITORY_OWNER": "Autre-Compte"})
    assert r.returncode == 0, sortie(r)
    assert banc.tires() == ["ghcr.io/autre-compte/essai:main", "ghcr.io/autre-compte/essai:1.0.0"]
    # --compte l'emporte
    r = banc.lancer("--code", "code", "--compte", COMPTE, env={"GITHUB_REPOSITORY_OWNER": "Autre"})
    assert r.returncode == 0, sortie(r)
    assert banc.tires() == [f"{BASE}:main", f"{BASE}:1.0.0"]
    # ni l'un ni l'autre, ou un compte qui n'en est pas un : usage, rien n'est tiré
    for arguments, env in (
        ((), {}),
        ((), {"GITHUB_REPOSITORY_OWNER": ""}),
        (("--compte", "-x"), {}),
        (("--compte", "a b"), {}),
    ):
        r = banc.lancer("--code", "code", *arguments, env=env)
        assert r.returncode == 64, (arguments, env, sortie(r))
        assert banc.appels() == []


def test_sans_version_publiee_seule_main(banc):
    banc.commit_du_code(DEUX_COMMANDES, "v2.0", "donnees-2026.11.03.1")
    banc.commit_des_donnees({"config/profil.yml": "version: 1\n", "contenu/page.md": "page\n"})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 0, sortie(r)
    assert "aucune version publiée du code : seule :main est vérifiée" in r.stdout
    assert banc.tires() == [f"{BASE}:main"]
    assert {a["image"] for a in banc.lances()} == {f"{BASE}:main"}


def test_chaque_image_avec_la_declaration_de_sa_version(banc):
    """:main suit le projet.env de la copie du code ; :X.Y.Z, celui de son étiquette. Une version
    qui ne déclare pas une commande ne la lance pas, et la règle des paires se juge contre elle."""
    banc.commit_du_code("VERIFIER_CONTENU=verifier-contenu\n", "v1.0.0")
    banc.commit_du_code(DEUX_COMMANDES)
    banc.commit_des_donnees({"config/profil.yml": "version: 1\n", "contenu/page.md": "page\n"})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {BASE}:1.0.0 (v1.0.0) : config/ sans VERIFIER_CONFIG" in r.stdout
    assert "main) : config/ sans" not in r.stdout
    # :main lance ses deux commandes ; l'image en défaut, aucune
    assert [(a["image"], a["commande"][0]) for a in banc.lances()] == [
        (f"{BASE}:main", "verifier-config"),
        (f"{BASE}:main", "verifier-contenu"),
    ]

    # la version déclare ce que les données portent : chacune ses commandes
    banc.commit_des_donnees({"contenu/page.md": "page\n"})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {BASE}:main (main) : VERIFIER_CONFIG sans config/" in r.stdout
    assert [(a["image"], a["commande"]) for a in banc.lances()] == [
        (f"{BASE}:1.0.0", ["verifier-contenu", "/contenu"])
    ]

    # une version sans projet.env ne déclare rien
    banc.commit_du_code(None, "v1.1.0")
    banc.commit_du_code("")
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {BASE}:1.1.0 (v1.1.0) : contenu/ sans VERIFIER_CONTENU" in r.stdout
    assert f"refus : {BASE}:main (main) : contenu/ sans VERIFIER_CONTENU" in r.stdout
    assert banc.lances() == []


def test_option_images_et_la_declaration_de_la_copie(banc):
    banc.commit_du_code("VERIFIER_CONTENU=ancienne\n", "v1.0.0")
    banc.commit_du_code("VERIFIER_CONTENU=verifier-contenu\n")
    banc.commit_des_donnees({"contenu/page.md": "page\n"})
    a, b = "registre.exemple.org/un/essai:1", "registre.exemple.org/deux/essai:2"
    # --images remplace la liste ; ni compte, ni dépôt de code nommé ne sont alors nécessaires
    r = banc.lancer("--code", "code", "--images", a, b)
    assert r.returncode == 0, sortie(r)
    assert banc.tires() == [a, b]
    assert [(x["image"], x["commande"]) for x in banc.lances()] == [
        (a, ["verifier-contenu", "/contenu"]),
        (b, ["verifier-contenu", "/contenu"]),
    ]
    assert f"{a} (déclaration de la copie)" in r.stdout


# --- La règle des paires ------------------------------------------------------------------------


def test_paires_sur_le_commit_head(banc):
    """Un dossier qui ne porte que son README.md compte comme absent ; un README.md plus bas compte ;
    un fichier non suivi ne compte pas : la règle se juge sur HEAD, pas sur la copie de travail."""
    banc.commit_du_code("")
    banc.commit_des_donnees({"config/README.md": "notes\n", "contenu/README.md": "notes\n"})
    (banc.donnees / "config/non-suivi.yml").write_text("x\n", encoding="utf-8")
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 0, sortie(r)
    assert banc.lances() == []

    banc.commit_des_donnees({"config/README.md": "notes\n", "contenu/pages/README.md": "page\n"})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {BASE}:main (main) : contenu/ sans VERIFIER_CONTENU" in r.stdout
    assert "config/ sans" not in r.stdout

    # la commande sans son dossier : un README.md seul n'en est pas un
    banc.commit_du_code("VERIFIER_CONFIG=verifier-config\n")
    banc.commit_des_donnees({"config/README.md": "notes\n"})
    (banc.donnees / "config/non-suivi.yml").write_text("x\n", encoding="utf-8")
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {BASE}:main (main) : VERIFIER_CONFIG sans config/" in r.stdout
    assert banc.lances() == []


def test_un_projet_env_illisible_refuse(banc):
    banc.commit_du_code("VERIFIER_CONFIG=verifier;config\n")
    banc.commit_des_donnees({"config/profil.yml": "version: 1\n"})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {BASE}:main (main) : deploiement/projet.env illisible" in r.stdout
    assert "ligne 1 invalide" in r.stdout
    assert banc.lances() == []


# --- Le contenu en service ----------------------------------------------------------------------


def test_en_service_le_contenu_de_la_plus_haute_etiquette(banc):
    banc.commit_du_code("VERIFIER_CONTENU=verifier-contenu\n")
    banc.commit_des_donnees({"contenu/page.md": "neuf\n"}, "donnees-2026.11.03.9")
    banc.commit_des_donnees({"contenu/page.md": "en service\n"}, "donnees-2026.11.03.10")
    # des formes que la chaîne ignore, même plus hautes en ordre de chaîne
    banc.commit_des_donnees({"contenu/page.md": "ignorée\n"}, "donnees-2026.12.3.1", "v9.9.9")
    banc.commit_des_donnees({"contenu/page.md": "visée\n"})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 0, sortie(r)
    (appel,) = banc.lances()
    assert appel["commande"] == ["verifier-contenu", "/contenu", "/en-service"]
    assert montages_de(appel) == {
        "/contenu": ("ro", {"page.md": "visée\n"}),
        "/en-service": ("ro", {"page.md": "en service\n"}),
    }
    i = appel["args"].index
    assert i("-v") < appel["args"].index(f"{BASE}:main")
    assert appel["args"][i("-v") + 1].endswith(":/contenu:ro")
    assert "donnees-2026.11.03.10" in r.stdout


def test_sans_contenu_en_service_seul_contenu(banc):
    banc.commit_du_code("VERIFIER_CONTENU=verifier-contenu\n")
    # aucune étiquette de données
    banc.commit_des_donnees({"contenu/page.md": "visée\n"}, "donnees-2026.11.3.1")
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 0, sortie(r)
    (appel,) = banc.lances()
    assert appel["commande"] == ["verifier-contenu", "/contenu"]
    assert set(appel["montages"]) == {"/contenu"}
    # une étiquette dont le contenu/ ne porte que son README.md
    banc.commit_des_donnees({"contenu/README.md": "notes\n"}, "donnees-2026.11.03.1")
    banc.commit_des_donnees({"contenu/page.md": "visée\n"})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 0, sortie(r)
    (appel,) = banc.lances()
    assert appel["commande"] == ["verifier-contenu", "/contenu"]


# --- Les codes de l'image, l'image absente --------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (2, "configuration non conforme (VERIFIER_CONFIG : verifier-config /config : code 2)"),
        (64, "vérification impossible (VERIFIER_CONFIG : verifier-config /config : code 64)"),
        (3, "vérification impossible (VERIFIER_CONFIG : verifier-config /config : code 3)"),
    ],
)
def test_codes_de_l_image(banc, code, message):
    banc.commit_du_code(DEUX_COMMANDES, "v1.0.0")
    banc.commit_des_donnees({"config/profil.yml": "version: 1\n", "contenu/page.md": "page\n"})
    image = f"{BASE}:1.0.0"
    banc.regler_docker(
        codes={f"{image} verifier-config": code},
        sorties={f"{image} verifier-config": "version de schéma inconnue"},
    )
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    (refus,) = [ligne for ligne in r.stdout.splitlines() if ligne.startswith("refus : ")]
    assert refus.startswith(f"refus : {image} (v1.0.0) : {message}")
    assert refus.endswith("version de schéma inconnue")
    # l'autre commande et l'autre image tournent : tout ce qui refuse est dit
    assert len(banc.lances()) == 4


def test_une_image_absente_refuse(banc):
    banc.commit_du_code(DEUX_COMMANDES, "v1.0.0")
    banc.commit_des_donnees({"config/profil.yml": "version: 1\n", "contenu/page.md": "page\n"})
    banc.regler_docker(absentes=[f"{BASE}:1.0.0"])
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 1, sortie(r)
    assert f"refus : {BASE}:1.0.0 (v1.0.0) : image absente du registre, ou illisible" in r.stdout
    assert "not found" in r.stdout
    assert banc.tires() == [f"{BASE}:main", f"{BASE}:1.0.0"]
    assert {a["image"] for a in banc.lances()} == {f"{BASE}:main"}


# --- L'usage --------------------------------------------------------------------------------------


def test_usage(banc, tmp_path):
    banc.commit_du_code("")
    banc.commit_des_donnees({})
    (tmp_path / "pas-un-depot").mkdir()
    for arguments in (
        (),
        ("--code",),
        ("--code", str(tmp_path / "absent")),
        ("--code", str(tmp_path / "pas-un-depot")),
        ("--code", "code", "--images"),
        ("--code", "code", "--bidon"),
    ):
        r = banc.lancer(*arguments, "--compte", COMPTE)
        assert r.returncode == 64, (arguments, sortie(r))
        assert "Traceback" not in sortie(r)
        assert banc.appels() == []


def test_sans_depot_code_usage(tmp_path, env_isole):
    """Hors d'un dépôt de données (reglages.py sans DEPOT_CODE), aucune image ne se désigne."""
    banc = Banc(tmp_path, env_isole(), depot_code="")
    banc.commit_du_code("")
    banc.commit_des_donnees({})
    r = banc.lancer("--code", "code", "--compte", COMPTE)
    assert r.returncode == 64, sortie(r)
    assert "DEPOT_CODE" in sortie(r)
    assert banc.appels() == []
