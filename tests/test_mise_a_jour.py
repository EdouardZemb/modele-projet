"""La mise à jour par Copier propage le géré et préserve le semé (spec §8, critère 3)."""

import hashlib
import shutil
import subprocess
from pathlib import Path

import copier
import pytest
import yaml
from conftest import RACINE, REPONSES_PAR_DEFAUT, REPONSES_SERVEUR, git

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
