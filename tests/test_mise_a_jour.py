"""La mise à jour par Copier propage le géré et préserve le semé (spec §8, critère 3)."""

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import copier
import masques
import pytest
import yaml
from conftest import (
    CLE_HORS_LIGNE_DE_TEST,
    CLE_SERVEUR_DE_TEST,
    RACINE,
    REPONSES_PAR_DEFAUT,
    REPONSES_SERVEUR,
    git,
)
from copier.errors import UserMessageError

SH = shutil.which("sh") or (
    r"C:\Program Files\Git\bin\sh.exe" if Path(r"C:\Program Files\Git\bin\sh.exe").exists() else None
)

IGNORES = shutil.ignore_patterns(
    ".git", ".superpowers", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv"
)
LIGNE_PROJET = "Ligne ajoutée par le projet"
LIGNE_MODELE = "Ligne ajoutée en v0.0.2"


def _modele_v1(tmp_path, env):
    modele = tmp_path / "modele"
    shutil.copytree(RACINE, modele, ignore=IGNORES)
    git(modele, env, "init", "-q", "-b", "main")
    git(modele, env, "config", "core.autocrlf", "false")
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.1")
    git(modele, env, "tag", "v0.0.1")
    return modele


def _projet_v1(tmp_path, env, modele, reponses=REPONSES_PAR_DEFAUT):
    projet = tmp_path / "projet"
    copier.run_copy(
        str(modele),
        str(projet),
        data=reponses,
        defaults=True,
        vcs_ref="v0.0.1",
        quiet=True,
    )
    git(projet, env, "init", "-q", "-b", "main")
    git(projet, env, "config", "core.autocrlf", "false")
    git(projet, env, "add", "-A")
    git(projet, env, "commit", "-q", "-m", "etat initial")
    return projet


def test_mise_a_jour_propage_et_preserve(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)

    with (projet / "CLAUDE.md").open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\n{LIGNE_PROJET}\n")
    git(projet, env, "commit", "-q", "-am", "claude du projet")

    with (modele / "template/docs/modele/methode.md").open(
        "a", encoding="utf-8", newline="\n"
    ) as f:
        f.write(f"\n{LIGNE_MODELE}\n")
    git(modele, env, "commit", "-q", "-am", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")

    copier.run_update(
        str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.2", quiet=True
    )

    assert LIGNE_MODELE in (projet / "docs/modele/methode.md").read_text(encoding="utf-8")
    assert LIGNE_PROJET in (projet / "CLAUDE.md").read_text(encoding="utf-8")
    assert not list(projet.rglob("*.rej"))
    for chemin in projet.rglob("*"):
        if chemin.is_file() and ".git" not in chemin.relative_to(projet).parts:
            try:
                texte = chemin.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            assert "<<<<<<<" not in texte, chemin
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["_commit"] == "v0.0.2"


def test_mise_a_jour_sans_changement(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)

    copier.run_update(
        str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.1", quiet=True
    )

    assert git(projet, env, "status", "--porcelain").strip() == ""


LIGNE_GABARIT = "Ligne ajoutée au gabarit en v0.0.2"
SEMES_RETOUCHES = ("template/CLAUDE.md.jinja", "template/docs/{% if cible != 'donnees' %}registre.md{% endif %}")


def _modele_v2(modele, env):
    """Une v0.0.2 qui ajoute une ligne aux gabarits de deux semés : ils ne doivent pas l'accueillir."""
    for gabarit in SEMES_RETOUCHES:
        with (modele / gabarit).open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n{LIGNE_GABARIT}\n")
    git(modele, env, "commit", "-q", "-am", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")


def _sans_conflit(projet):
    assert not list(projet.rglob("*.rej"))
    for chemin in projet.rglob("*"):
        if chemin.is_file() and ".git" not in chemin.relative_to(projet).parts:
            try:
                texte = chemin.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            assert "<<<<<<<" not in texte, chemin


def _retoucher(*chemins):
    for chemin in chemins:
        with chemin.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"\n# {LIGNE_PROJET}\n")


def test_passage_en_cible_serveur(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)
    _retoucher(projet / "CLAUDE.md", projet / "docs/registre.md")
    git(projet, env, "commit", "-q", "-am", "semés retouchés par le projet")
    claude = (projet / "CLAUDE.md").read_bytes()
    registre = (projet / "docs/registre.md").read_bytes()
    assert LIGNE_PROJET.encode() in claude
    assert not (projet / "deploiement").exists()
    _modele_v2(modele, env)

    copier.run_update(
        str(projet),
        data={"cible": "serveur", "sauvegardes": True, "fusion": "session"},
        defaults=True,
        overwrite=True,
        vcs_ref="v0.0.2",
        quiet=True,
    )

    assert (projet / "deploiement/lib.sh").is_file()
    assert (projet / "deploiement/projet.env").is_file()
    # Un projet de code passe en `serveur` à deux dépôts : son instance vivra dans ses données.
    assert not (projet / ".sops.yaml").exists()
    assert not (projet / "deploiement/env").exists()
    assert (projet / "docs/modele/decisions/M-0003-contrat-de-l-image.md").is_file()
    assert (projet / "CLAUDE.md").read_bytes() == claude
    assert (projet / "docs/registre.md").read_bytes() == registre
    assert LIGNE_GABARIT not in (projet / "CLAUDE.md").read_text(encoding="utf-8")
    assert LIGNE_GABARIT not in (projet / "docs/registre.md").read_text(encoding="utf-8")
    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["cible"] == "serveur"
    assert reponses["nature"] == "code"
    assert "bloc_ports" not in reponses


def test_retour_en_cible_aucune(tmp_path, env_isole):
    env = env_isole()
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele, REPONSES_SERVEUR)
    lib = projet / "deploiement/lib.sh"
    for present in (
        lib,
        projet / "deploiement/projet.env",
        projet / "deploiement/compose.projet.yml",
        projet / ".sops.yaml",
        projet / "tests/deploiement",
        projet / "docs/exploitation.md",
    ):
        assert present.exists(), present
    _retoucher(
        projet / "deploiement/projet.env", lib, projet / "CLAUDE.md", projet / "docs/registre.md"
    )
    claude = (projet / "CLAUDE.md").read_bytes()
    registre = (projet / "docs/registre.md").read_bytes()
    git(projet, env, "commit", "-q", "-am", "retouches du projet")
    _modele_v2(modele, env)

    copier.run_update(
        str(projet),
        data={"cible": "aucune", "fusion": "session"},
        defaults=True,
        overwrite=True,
        vcs_ref="v0.0.2",
        quiet=True,
    )

    # Le géré de l'ancienne cible disparaît, retouché ou non.
    assert not lib.exists()
    assert not (projet / ".sops.yaml").exists()
    # Écart au §8 de la spec : Copier supprime aussi les semés de l'ancienne cible, dossier
    # compris, retouchés ou non (observé avec Copier 9.19.1).
    assert not (projet / "deploiement").exists()
    assert not (projet / "tests/deploiement").exists()
    assert not (projet / "docs/exploitation.md").exists()
    # Les semés qui ne sont pas propres à la cible survivent, retouches comprises.
    assert (projet / "CLAUDE.md").read_bytes() == claude
    assert (projet / "docs/registre.md").read_bytes() == registre
    assert LIGNE_GABARIT not in (projet / "CLAUDE.md").read_text(encoding="utf-8")
    assert LIGNE_GABARIT not in (projet / "docs/registre.md").read_text(encoding="utf-8")
    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses["cible"] == "aucune"


@pytest.mark.skipif(SH is None, reason="aucun sh trouvé")
def test_mise_a_jour_refuse_un_fichier_masque(tmp_path, env_isole):
    """Le critère de sortie de LE-8 : la vérification dans le test de mise à jour (LE-23)."""
    env = {**env_isole(), "MOTIFS_INTERDITS": "motif-interdit-essai"}
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele)
    git(projet, env, "config", "core.hooksPath", ".githooks")

    with (projet / ".gitignore").open("a", encoding="utf-8", newline="\n") as f:
        f.write("\n*secret*\n")
    git(projet, env, "add", ".gitignore")
    git(projet, env, "commit", "-q", "-m", "chore: ignorer les secrets")

    nouveau = modele / "template/scripts/modele/outil_secret.py"
    nouveau.write_text('"""Un outil du modèle que le .gitignore du projet masque."""\n', encoding="utf-8")
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")

    copier.run_update(str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.2", quiet=True)
    assert (projet / "scripts/modele/outil_secret.py").is_file()

    def valider():
        git(projet, env, "add", "-A")
        return subprocess.run(
            ["git", "commit", "-q", "-m", "chore: mise à jour du modèle"],
            check=False,
            cwd=projet,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    r = valider()
    assert r.returncode != 0
    assert "scripts/modele/outil_secret.py" in r.stderr

    with (projet / ".gitignore").open("a", encoding="utf-8", newline="\n") as f:
        f.write("!scripts/modele/outil_secret.py\n")
    r = valider()
    assert r.returncode == 0, r.stderr
    suivis = subprocess.run(
        ["git", "ls-files", "scripts/modele/outil_secret.py"],
        check=True,
        cwd=projet,
        env=env,
        capture_output=True,
        text=True,
    )
    assert "outil_secret.py" in suivis.stdout


def _modele_depuis(tmp_path, env, version):
    """Un modèle de test : la `version` du dépôt (v0.0.1), puis l'arbre de travail actuel (v0.0.2)."""
    modele = tmp_path / "modele"
    modele.mkdir()
    archive = tmp_path / f"{version}.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), version],
        check=True,
        cwd=RACINE,
        env=env,
    )
    shutil.unpack_archive(archive, modele, filter="data")
    git(modele, env, "init", "-q", "-b", "main")
    git(modele, env, "config", "core.autocrlf", "false")
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.1")
    git(modele, env, "tag", "v0.0.1")
    # L'arbre est vidé avant la copie : un fichier retiré depuis cette version doit l'être vraiment.
    for chemin in modele.iterdir():
        if chemin.name != ".git":
            shutil.rmtree(chemin) if chemin.is_dir() else chemin.unlink()
    shutil.copytree(RACINE, modele, ignore=IGNORES, dirs_exist_ok=True)
    git(modele, env, "add", "-A")
    git(modele, env, "commit", "-q", "-m", "v0.0.2")
    git(modele, env, "tag", "v0.0.2")
    return modele


def _projet_depuis(tmp_path, env, version, reponses):
    """Un projet rendu par la `version` du dépôt (la v0.0.1 du modèle de test), commité."""
    modele = _modele_depuis(tmp_path, env, version)
    projet = tmp_path / "projet"
    copier.run_copy(
        str(modele), str(projet), data=reponses, defaults=True, vcs_ref="v0.0.1", quiet=True
    )
    git(projet, env, "init", "-q", "-b", "main")
    git(projet, env, "config", "core.autocrlf", "false")
    git(projet, env, "add", "-A")
    git(projet, env, "commit", "-q", "-m", "etat initial")
    return projet


def _mettre_a_jour(projet, **update):
    """La mise à jour vers l'arbre de travail actuel (la v0.0.2 du modèle de test)."""
    copier.run_update(
        str(projet), defaults=True, overwrite=True, vcs_ref="v0.0.2", quiet=True, **update
    )


def _mettre_a_jour_depuis_v0_5_0(tmp_path, env, reponses, **update):
    projet = _projet_depuis(tmp_path, env, "v0.5.0", reponses)
    _mettre_a_jour(projet, **update)
    return projet


def test_mise_a_jour_d_un_projet_prive_serveur_garde_tout(tmp_path, env_isole):
    env = env_isole()
    reponses = {**REPONSES_SERVEUR, "visibilite": "prive"}
    projet = _mettre_a_jour_depuis_v0_5_0(tmp_path, env, reponses)

    reglages = (projet / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "donnees"' in reglages
    assert "VISIBILITE" not in reglages
    assert (projet / "deploiement/deployer.sh").is_file()
    reponses_finales = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses_finales["nature"] == "donnees"
    _sans_conflit(projet)


def test_mise_a_jour_d_un_projet_public_passe_en_code(tmp_path, env_isole):
    env = env_isole()
    reponses = {**REPONSES_PAR_DEFAUT, "visibilite": "public", "cible": "aucune"}
    projet = _mettre_a_jour_depuis_v0_5_0(tmp_path, env, reponses)

    reglages = (projet / "scripts/modele/reglages.py").read_text(encoding="utf-8")
    assert 'NATURE = "code"' in reglages
    assert "VISIBILITE" not in reglages
    reponses_finales = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert reponses_finales["nature"] == "code"
    _sans_conflit(projet)


# Lot 14 : le LICENSE est semé. Un projet de code rendu par la v0.8.1, sans lui, le reçoit à sa
# mise à jour ; un dépôt de données, de nature ou de cible, ne le reçoit jamais.
@pytest.mark.parametrize(
    ("reponses", "cree"),
    [
        (REPONSES_PAR_DEFAUT, True),
        ({**REPONSES_PAR_DEFAUT, "nature": "donnees"}, False),
        ({**REPONSES_PAR_DEFAUT, "nom": "essai-donnees", "cible": "donnees"}, False),
    ],
    ids=["code", "nature-donnees", "cible-donnees"],
)
def test_mise_a_jour_cree_la_licence(tmp_path, env_isole, reponses, cree):
    env = env_isole()
    projet = _projet_depuis(tmp_path, env, "v0.8.1", reponses)
    assert not (projet / "LICENSE").exists()
    _mettre_a_jour(projet)
    assert (projet / "LICENSE").is_file() == cree
    if cree:
        # Un semé retiré exprès revient à la mise à jour suivante.
        git(projet, env, "add", "-A")
        git(projet, env, "commit", "-q", "-m", "mise à jour")
        git(projet, env, "rm", "-q", "--", "LICENSE")
        git(projet, env, "commit", "-q", "-m", "sans licence")
        _mettre_a_jour(projet)
        assert (projet / "LICENSE").is_file()


# Lot 12 (M-0006, § 9) : les clés du parc sortent du modèle, et les fichiers de l'instance d'un
# projet à un dépôt sont semés. Rendu en v0.6.0, un tel projet monte de version sans --data : ses
# clés, son .sops.yaml et ses env/ restent tels quels, au caractère près. On compare des
# empreintes : les fichiers de la v0.6.0 portent des clés réelles, qu'aucun échec ne doit imprimer.
INSTANCE_A_UN_DEPOT = (
    ".sops.yaml",
    "deploiement/cles/serveur.pub",
    "deploiement/cles/hors-ligne.pub",
    "deploiement/env/prod.env",
    "deploiement/env/staging.env",
)


def _empreintes(projet, chemins):
    return {
        chemin: hashlib.sha256((projet / chemin).read_bytes()).hexdigest()
        if (projet / chemin).is_file()
        else None
        for chemin in chemins
    }


def test_mise_a_jour_d_un_projet_a_un_depot_garde_ses_cles(tmp_path, env_isole):
    env = env_isole()
    # Les réponses d'un projet de la v0.6.0, qui ne connaissait pas les clés du parc.
    reponses = {
        cle: valeur for cle, valeur in REPONSES_SERVEUR.items() if not cle.startswith("cle_")
    }
    projet = _projet_depuis(tmp_path, env, "v0.6.0", reponses)
    avant = _empreintes(projet, INSTANCE_A_UN_DEPOT)
    assert None not in avant.values(), [chemin for chemin, e in avant.items() if e is None]

    _mettre_a_jour(projet)

    assert _empreintes(projet, INSTANCE_A_UN_DEPOT) == avant
    finales = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert finales["_commit"] == "v0.0.2"
    assert finales["nature"] == "donnees"
    assert (finales["domaine"], finales["sous_domaine"], finales["bloc_ports"]) == (
        "exemple.org",
        "essai",
        4310,
    )
    assert (finales["cle_serveur"], finales["cle_hors_ligne"]) == ("", "")
    lib = (projet / "deploiement/lib.sh").read_text(encoding="utf-8")
    assert 'MODE_DONNEES="un"' in lib.splitlines()
    _sans_conflit(projet)


# La scission d'un projet à un dépôt (#94) : un projet comme `veille-emploi`, en cible `serveur` et
# de nature `donnees`, devient son dépôt de données par `copier update`, comme l'a fait `ancrage`
# le 07/11 (ancrage-donnees#207). Valeurs inventées, sur `exemple.test`, et clés `age` de test.
METHODE = RACINE / "template/docs/modele/methode.md"
REPONSES_A_UN_DEPOT = {
    **REPONSES_SERVEUR,
    "branche_principale": "principal",
    "domaine": "exemple.test",
    "bloc_ports": 4320,
    "port_app": 8000,
    "chemin_sante": "/sante",
}
SCISSION = {
    "cible": "donnees",
    "cible_code": "serveur",
    "nom": "essai-donnees",
    "sous_domaine": "essai",
    "cle_serveur": CLE_SERVEUR_DE_TEST,
    "cle_hors_ligne": CLE_HORS_LIGNE_DE_TEST,
}
# Ce que le modèle ne connaît pas : l'instance et les secrets chiffrés d'un projet à un dépôt, et
# où la voie préparée les déplace, là où la chaîne à deux dépôts les lit.
DEPLACES = {
    "deploiement/secrets/prod.env.enc": "secrets/prod.env.enc",
    "instance/config/projet.toml": "config/projet.toml",
}
HORS_DU_MODELE = tuple(DEPLACES)
# Des fichiers locaux, que les règles propres du .gitignore du projet gardent hors du dépôt.
LOCAUX = ("auth.json", "config/.env")


def _tous(racine):
    return {
        p.relative_to(racine).as_posix()
        for p in racine.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(racine).parts
    }


PHRASE_DES_RESTES = "à un dépôt devient un dépôt de données, ce sont "


def semes_restes_selon_la_methode():
    """Les semés que `methode.md` dit restés à leur contenu de cible `serveur` après la scission."""
    puce = METHODE.read_text(encoding="utf-8").split("- Changer de cible,", 1)[1]
    puce = " ".join(puce.split("\n\n", 1)[0].split())
    if PHRASE_DES_RESTES not in puce:
        return set()
    liste = puce.split(PHRASE_DES_RESTES, 1)[1].split(". ", 1)[0]
    return set(re.findall(r"`([^`]+)`", liste))


# Les règles du .gitignore de `veille-emploi` : tout dotenv, et tout ce qui nomme un secret. Sous
# elles, la correction à la main de `.gitignore` doit lever `secrets/` sans les secrets en clair.
REGLES_DU_PROJET = ("*.env", "*secret*")
PHRASE_DE_LA_CORRECTION = "Il se corrige à la main : pour un dépôt de données, "


def correction_selon_la_methode():
    """Les lignes que `methode.md` fait ajouter à la main au `.gitignore`, dans leur ordre."""
    puce = METHODE.read_text(encoding="utf-8").split("- Changer de cible,", 1)[1]
    puce = " ".join(puce.split("\n\n", 1)[0].split())
    m = re.search(re.escape(PHRASE_DE_LA_CORRECTION) + r"((?:`[^`]+`(?:, | puis ))*`[^`]+`)", puce)
    return [] if m is None else re.findall(r"`([^`]+)`", m.group(1))


def _projet_a_un_depot(tmp_path, env):
    """Le projet à un dépôt, retouché par lui et avec ce que le modèle ne connaît pas, commité ;
    son .gitignore a ses règles propres, et les fichiers locaux qu'elles masquent sont là."""
    modele = _modele_v1(tmp_path, env)
    projet = _projet_v1(tmp_path, env, modele, REPONSES_A_UN_DEPOT)
    _retoucher(projet / "deploiement/projet.env", projet / "docs/registre.md", projet / "CLAUDE.md")
    with (projet / ".gitignore").open("a", encoding="utf-8", newline="\n") as f:
        f.write("".join(f"{chemin}\n" for chemin in LOCAUX))
    for chemin in HORS_DU_MODELE + LOCAUX:
        (projet / chemin).parent.mkdir(parents=True, exist_ok=True)
        (projet / chemin).write_text("hors du modèle\n", encoding="utf-8", newline="\n")
    git(projet, env, "add", "-A")
    git(projet, env, "commit", "-q", "-m", "retouches du projet")
    assert git(projet, env, "status", "--porcelain").strip() == ""
    return modele, projet


def _masque(projet, env, chemin):
    """Vrai si le .gitignore du projet masque `chemin`, qu'il existe ou non."""
    r = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", chemin],
        cwd=projet,
        env=env,
        capture_output=True,
        check=False,
    )
    assert r.returncode in (0, 1), r.stderr
    return r.returncode == 0


def _rendu_neuf(tmp_path, modele, projet):
    """Un rendu neuf du modèle, avec les réponses du projet mis à jour."""
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    neuf = tmp_path / "neuf"
    copier.run_copy(
        str(modele),
        str(neuf),
        data={cle: valeur for cle, valeur in reponses.items() if not cle.startswith("_")},
        defaults=True,
        vcs_ref="v0.0.1",
        quiet=True,
    )
    return neuf


@pytest.mark.parametrize("preparee", [False, True], ids=["seule", "preparee"])
def test_scission_d_un_projet_a_un_depot(tmp_path, env_isole, capsys, preparee):
    env = env_isole()
    modele, projet = _projet_a_un_depot(tmp_path, env)
    restes = semes_restes_selon_la_methode()
    if preparee:
        # La voie préparée de methode.md : les semés retirés avant la mise à jour sont semés à neuf,
        # sauf `.gitignore`, corrigé à la main ; ce que le modèle ne connaît pas se déplace.
        assert ".gitignore" in restes, "methode.md ne nomme pas les semés restés"
        correction = correction_selon_la_methode()
        assert correction, "methode.md ne dit pas comment corriger `.gitignore`"
        git(projet, env, "rm", "-q", "--", *sorted(restes - {".gitignore"}))
        with (projet / ".gitignore").open("a", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"{ligne}\n" for ligne in (*REGLES_DU_PROJET, *correction)))
        for ancien, nouveau in DEPLACES.items():
            (projet / nouveau).parent.mkdir(parents=True, exist_ok=True)
            git(projet, env, "mv", "--", ancien, nouveau)
        git(projet, env, "add", "--", ".gitignore")
        git(projet, env, "commit", "-q", "-m", "scission préparée")
    hors = tuple(DEPLACES.values()) if preparee else HORS_DU_MODELE
    avant = {chemin: (projet / chemin).read_bytes() for chemin in _tous(projet)}

    copier.run_update(
        str(projet), data=SCISSION, defaults=True, overwrite=True, vcs_ref="v0.0.1", quiet=True
    )

    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert (reponses["cible"], reponses["cible_code"], reponses["nom"]) == (
        "donnees",
        "serveur",
        "essai-donnees",
    )
    assert (reponses["domaine"], reponses["bloc_ports"], reponses["sous_domaine"]) == (
        "exemple.test",
        4320,
        "essai",
    )
    for question in ("nature", "port_app", "chemin_sante", "sauvegardes"):
        assert question not in reponses, question
    apres = _tous(projet)
    # Le géré de la cible `serveur` part, et ses semés que la cible `donnees` ne rend pas, même
    # retouchés : rien de `deploiement/` ne reste, que ce que le modèle ne connaît pas, et que
    # Copier ne déplace pas.
    assert sorted(c for c in apres if c.startswith("deploiement/")) == sorted(
        c for c in hors if c.startswith("deploiement/")
    )
    for parti in (
        "deploiement/projet.env",
        "deploiement/compose.projet.yml",
        "deploiement/secrets/prod.cles",
        "deploiement/cles/serveur.pub",
        "deploiement/env/prod.env",
        "tests/deploiement",
        ".github/actions",
        ".github/workflows/modele-version.yml",
        ".github/ISSUE_TEMPLATE/lot.yml",
        ".claude/skills/consigner",
        "docs/registre.md",
        "docs/exploitation.md",
        "docs/cadrage.md",
        "docs/decisions/README.md",
        "docs/modele/decisions/M-0003-contrat-de-l-image.md",
    ):
        assert not (projet / parti).exists(), parti
    for chemin in hors:
        assert git(projet, env, "ls-files", "--", chemin).strip() == chemin, chemin
    # L'instance du dépôt de données arrive.
    for arrive in (
        "env/prod.env",
        "env/staging.env",
        "cles/serveur.pub",
        "cles/hors-ligne.pub",
        "config/README.md",
        "contenu/README.md",
        ".github/workflows/modele-donnees.yml",
    ):
        assert arrive in apres, arrive
    staging = (projet / "env/staging.env").read_text(encoding="utf-8").splitlines()
    assert staging[-1] == "ESSAI_BRANCHE_DONNEES=principal"
    assert (projet / "cles/serveur.pub").read_text(encoding="utf-8") == CLE_SERVEUR_DE_TEST + "\n"
    # Face à un rendu neuf : seuls diffèrent les semés que methode.md nomme, à leur ancien contenu.
    neuf = _rendu_neuf(tmp_path, modele, projet)
    attendus = _tous(neuf)
    assert sorted(attendus - apres) == []
    assert sorted(apres - attendus) == sorted(hors + LOCAUX)
    differents = {c for c in attendus if (projet / c).read_bytes() != (neuf / c).read_bytes()}
    if preparee:
        # `.gitignore` seul diffère : ses règles propres restent, et il protège les secrets.
        assert differents == {".gitignore"}
        lignes = (projet / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert set(LOCAUX) <= set(lignes)
        # Les secrets en clair restent masqués, à la racine comme dans un dossier `secrets/`
        # imbriqué ; un secret chiffré neuf, que `secrets.ps1 refaire` écrira, ne l'est pas.
        for masque in (*LOCAUX, "secrets/prod.env", "secrets/age.txt", "config/secrets/jeton.txt"):
            assert _masque(projet, env, masque), masque
        assert not _masque(projet, env, "secrets/prod.env.enc")
        assert not _masque(projet, env, "secrets/staging.env.enc")
        # Au commit de la mise à jour, la porte des masqués ne voit pas le secret chiffré, déjà
        # suivi : elle ne demande que les dotenv de l'instance, que `*.env` masque.
        git(projet, env, "add", "--", ".copier-answers.yml")
        assert masques.main(["--racine", str(projet)]) == 1
        err = capsys.readouterr().err
        refuses = re.findall(r" : (\S+) \(règle ", err)
        assert sorted(refuses) == ["env/prod.env", "env/staging.env"]
        # Ses remèdes, appliqués à la lettre : des lignes ancrées (#95, ronde 2).
        remedes = re.findall(r"Ajouter `([^`]+)` à ce fichier", err)
        assert sorted(remedes) == ["!/env/prod.env", "!/env/staging.env"]
        with (projet / ".gitignore").open("a", encoding="utf-8", newline="\n") as f:
            f.write("".join(f"{ligne}\n" for ligne in remedes))
        assert masques.main(["--racine", str(projet)]) == 0
    else:
        assert differents == restes
        assert restes
        assert {c: (projet / c).read_bytes() for c in restes} == {c: avant[c] for c in restes}


def test_scission_refuse_un_gitignore_retire(tmp_path, env_isole):
    """Le `git rm` d'avant la mise à jour ne vaut pas pour `.gitignore` : sans lui, les fichiers
    locaux qu'il masquait paraissent, et Copier refuse l'arbre sale (methode.md, « Changer de
    cible »)."""
    env = env_isole()
    _, projet = _projet_a_un_depot(tmp_path, env)
    git(projet, env, "rm", "-q", "--", ".gitignore")
    git(projet, env, "commit", "-q", "-m", "gitignore retiré")
    assert sorted(git(projet, env, "status", "--porcelain").splitlines()) == [
        "?? auth.json",
        "?? config/",
    ]
    with pytest.raises(UserMessageError, match="Destination repository is dirty"):
        copier.run_update(
            str(projet), data=SCISSION, defaults=True, overwrite=True, vcs_ref="v0.0.1", quiet=True
        )
    texte = " ".join(METHODE.read_text(encoding="utf-8").split())
    assert "Sauf `.gitignore`, qui ne se retire jamais" in texte
    assert "ce que Copier refuse comme un arbre sale" in texte


def test_scission_sans_cible_code_prend_aucune(tmp_path, env_isole):
    """`cible_code` est une question nouvelle : sous `--defaults`, elle prend `aucune` sans un mot,
    et le dépôt de données perd l'instance (methode.md, « Changer de cible »)."""
    env = env_isole()
    _, projet = _projet_a_un_depot(tmp_path, env)
    sans = {cle: valeur for cle, valeur in SCISSION.items() if cle != "cible_code"}

    copier.run_update(
        str(projet), data=sans, defaults=True, overwrite=True, vcs_ref="v0.0.1", quiet=True
    )

    _sans_conflit(projet)
    reponses = yaml.safe_load((projet / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert (reponses["cible"], reponses["cible_code"]) == ("donnees", "aucune")
    for question in ("domaine", "bloc_ports", "sous_domaine", "cle_serveur", "cle_hors_ligne"):
        assert question not in reponses, question
    for absent in (".sops.yaml", "env", "cles", ".github/workflows/modele-donnees.yml"):
        assert not (projet / absent).exists(), absent
    assert (projet / "config/README.md").is_file()
    assert (projet / "contenu/README.md").is_file()
    texte = " ".join(METHODE.read_text(encoding="utf-8").split())
    assert "`--data cible_code=serveur` est obligatoire" in texte
