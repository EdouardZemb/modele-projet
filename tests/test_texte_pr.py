"""Le texte de la PR (`scripts/modele/texte_pr.py`) : la section « Écarts à la spec » (LE-37), et la
tête relue d'une PR qui ferme une issue (LE-55)."""

import shutil
import subprocess
import sys
import unicodedata

import pytest
import texte_pr as t
from conftest import RACINE, SCRIPTS

TETE = "a" * 40
ECART = "- le seuil passe à 45 min — promesse : spec § 4.1 — accord d'Edouard : 07/11/2026"
FERME_RIEN = (
    '{"data":{"repository":{"pullRequest":'
    '{"closingIssuesReferences":{"totalCount":0,"nodes":[]}}}}}'
)
FERME_UNE = FERME_RIEN.replace('"totalCount":0', '"totalCount":1')
REFUS = "texte de la PR : refus"
ABSENTE = "ferme une issue : ligne « Tête relue : <SHA complet> » absente"
ILLISIBLES = "fermetures illisibles (réponse de l'API absente, en erreur ou mal formée)"


@pytest.fixture
def lancer(tmp_path, monkeypatch, capsys):
    """Donne lancer(corps, auteur, tete, fermetures) -> (code, sortie). Le fichier des fermetures
    est écrit dans `tmp_path`, ou absent si `fermetures` vaut None ; une variable à None est
    retirée de l'environnement."""

    def _lancer(corps, auteur="EdouardZemb", tete=TETE, fermetures=FERME_RIEN, options=()):
        fichier = tmp_path / "fermetures.json"
        fichier.unlink(missing_ok=True)
        if fermetures is not None:
            fichier.write_text(fermetures, encoding="utf-8")
        for nom, valeur in (("CORPS", corps), ("AUTEUR", auteur), ("TETE", tete)):
            if valeur is None:
                monkeypatch.delenv(nom, raising=False)
            else:
                monkeypatch.setenv(nom, valeur)
        code = t.main(["--fermetures", str(fichier), *options])
        captee = capsys.readouterr()
        return code, captee.out + captee.err

    return _lancer


def corps_avec(section):
    """Un corps de PR : « Ce que fait cette PR », la section des écarts si elle n'est pas None,
    puis « Vérifications »."""
    corps = "## Ce que fait cette PR\n\nx\n"
    if section is not None:
        corps += "\n## Écarts à la spec\n\n" + section + "\n"
    return corps + "\n## Vérifications\n"


@pytest.mark.parametrize(
    ("section", "code", "attendu"),
    [
        (None, 1, "section absente (titre de niveau 2 « Écarts à la spec »)"),
        ("", 1, "section vide"),
        ("Aucun.", 0, "écarts à la spec : aucun"),
        (ECART, 0, "écarts à la spec : 1 déclaré"),
        (ECART + "\n" + ECART.replace("45", "50"), 0, "écarts à la spec : 2 déclarés"),
        # une ligne qui continue la puce d'avant
        ("- un écart long\n  — promesse : § 2 — accord d'Edouard : 07/11/2026", 0, "1 déclaré"),
        ("- x — accord d'Edouard : 07/11/2026", 1, "ligne 2 de la section : promesse absente"),
        (
            "- x — promesse :  — accord d'Edouard : 07/11/2026",
            1,
            "ligne 2 de la section : promesse absente",
        ),
        (
            "- x — promesse : § 2",
            1,
            "ligne 2 de la section : accord d'Edouard absent ou date invalide",
        ),
        (ECART.replace("07/11/2026", "7/11/2026"), 1, "date invalide"),  # une date à un chiffre
        (ECART.replace("07/11/2026", "31/02/2026"), 1, "date invalide"),
        ("Aucun.\n" + ECART, 1, "« Aucun. » à côté d'un écart"),
        ("Rien de neuf.", 1, "ligne 2 de la section : ni « Aucun. » ni un écart"),
        # un commentaire en tête de ligne, puis un écart : GitHub rend la suite hors de toute liste
        ("Aucun.\n<!-- x --> " + ECART, 1, "ligne 3 de la section : ni « Aucun. » ni un écart"),
        (
            "Aucun.\n\n<!-- - <écart> — promesse : <§> — accord d'Edouard : JJ/MM/AAAA -->",
            0,
            "aucun",
        ),
        ("Aucun.\n\n```\n" + ECART + "\n```", 0, "aucun"),
        ("Aucun.\n\n<!--\n" + ECART, 1, "commentaire HTML non fermé"),
    ],
)
def test_ecarts(lancer, section, code, attendu):
    rendu, sortie = lancer(corps_avec(section))
    assert rendu == code, sortie
    assert attendu in sortie, sortie
    assert (REFUS in sortie) == (code == 1), sortie


def test_ecarts_titres_varies(lancer):
    """Un titre de niveau 3 n'est pas la section ; un titre en NFD l'est ; un titre de tout niveau
    la borne."""
    code, sortie = lancer("### Écarts à la spec\n\nAucun.\n")
    assert code == 1, sortie
    assert "section absente" in sortie, sortie
    code, sortie = lancer(unicodedata.normalize("NFD", "## Écarts à la spec\n\nAucun.\n"))
    assert (code, "écarts à la spec : aucun" in sortie) == (0, True), sortie
    code, sortie = lancer("## Écarts à la spec\n\nAucun.\n\n### Note\n\nDu texte libre.\n")
    assert (code, "écarts à la spec : aucun" in sortie) == (0, True), sortie


def test_texte_pr_corps_de_l_interface_web(lancer):
    """Un corps édité dans l'interface web de GitHub arrive en CRLF ; une session écrit selon son
    outil une apostrophe typographique, des espaces insécables, un tiret demi-cadratin."""
    ligne = (
        "- le seuil passe à 45 min \u2013 promesse\u00a0: spec § 4.1 \u2013 accord d\u2019Edouard"
        "\u00a0: 07/11/2026"
    )
    corps = (
        "## Ce que fait cette PR\r\n\r\nx\r\n\r\n## Écarts à la spec\r\n\r\n"
        + ligne
        + "\r\n\r\n## Fin\r\n"
    )
    assert "\r" in corps
    code, sortie = lancer(corps)
    assert code == 0, sortie
    assert "écarts à la spec : 1 déclaré" in sortie, sortie


def test_auteurs(lancer):
    """Seul `dependabot[bot]` est exempté, sans rien lire d'autre ; toute autre application, ou un
    nom qui lui ressemble, est soumise à la section."""
    code, sortie = lancer("", auteur="dependabot[bot]", fermetures=None)
    assert code == 0, sortie
    assert "texte de la PR : PR de dependabot[bot] : écarts et tête relue non exigés" in sortie
    for auteur in ("dependabot", "renovate[bot]", "github-actions[bot]"):
        code, sortie = lancer("", auteur=auteur)
        assert code == 1, (auteur, sortie)
        assert "section absente" in sortie, (auteur, sortie)


@pytest.mark.parametrize(
    ("ligne", "fermetures", "code", "attendu"),
    [
        (f"Tête relue : {TETE}", FERME_UNE, 0, "tête relue égale à la tête aaaaaaaaaaaa"),
        (f"Tête relue : `{TETE}`", FERME_UNE, 0, "tête relue égale à la tête aaaaaaaaaaaa"),
        (f"TÊTE RELUE : {TETE.upper()}", FERME_UNE, 0, "tête relue égale à la tête aaaaaaaaaaaa"),
        (f"Tête relue : {'b' * 40}", FERME_UNE, 1, f"différente de la tête {TETE}"),
        ("", FERME_UNE, 1, ABSENTE),
        ("Tête relue : ", FERME_UNE, 1, ABSENTE),
        (f"Tête relue : {TETE[:12]}", FERME_UNE, 1, ABSENTE),
        (f"<!-- Tête relue : {TETE} -->", FERME_UNE, 1, ABSENTE),
        ("", FERME_RIEN, 0, "ne ferme aucune issue : tête relue non exigée"),
        # l'API en erreur : un JSON sur la sortie, et une clé `errors`
        (
            "",
            '{"data":{"repository":{"pullRequest":null}},"errors":[{"type":"NOT_FOUND"}]}',
            1,
            ILLISIBLES,
        ),
        ("", '{"data":{"repository":{"pullRequest":null}}}', 1, ILLISIBLES),
        ("", "", 1, ILLISIBLES),  # un fichier vide
        ("", None, 1, ILLISIBLES),  # un fichier absent
        ("", FERME_UNE.replace('"totalCount":1', '"totalCount":"1"'), 1, ILLISIBLES),
    ],
)
def test_tete_relue(lancer, ligne, fermetures, code, attendu):
    corps = "## Écarts à la spec\n\nAucun.\n\n## Vérifications\n\n" + ligne + "\n"
    rendu, sortie = lancer(corps, fermetures=fermetures)
    assert rendu == code, sortie
    assert attendu in sortie, sortie
    assert (REFUS in sortie) == (code == 1), sortie
    if "b" * 40 in ligne:  # le refus nomme les deux SHA
        assert f"ferme une issue : tête relue {'b' * 40} différente de la tête {TETE}" in sortie


def test_le_gabarit_de_pr_passe_tel_quel(lancer):
    """Le gabarit de PR, pris tel quel pour corps : il passe quand la PR ne ferme rien, et refuse
    quand elle ferme une issue, faute de tête relue."""
    gabarit = (RACINE / "template/.github/pull_request_template.md").read_text(encoding="utf-8")
    code, sortie = lancer(gabarit, fermetures=FERME_RIEN)
    assert code == 0, sortie
    assert "écarts à la spec : aucun" in sortie, sortie
    code, sortie = lancer(gabarit, fermetures=FERME_UNE)
    assert code == 1, sortie
    assert ABSENTE in sortie, sortie


def test_usage(lancer):
    """Sans auteur, avec une tête qui n'est pas un SHA complet, ou une option inconnue : une erreur
    d'usage, qui ne cite rien du corps."""
    corps = corps_avec("SENTINELLE")
    for code, sortie in (
        lancer(corps, auteur=None),
        lancer(corps, tete="abc"),
        lancer(corps, options=("--inconnue", "SENTINELLE")),
    ):
        assert code == t.EXIT_USAGE == 64, sortie
        assert "SENTINELLE" not in sortie, sortie


def test_ne_cite_jamais_le_corps(lancer):
    """Un corps de PR est public, et peut porter un motif privé : le refus nomme la ligne par son
    rang, jamais par son texte."""
    code, sortie = lancer(corps_avec(ECART + "\nUne ligne de prose SENTINELLE."))
    assert code == 1, sortie
    assert "ligne 3 de la section : ni « Aucun. » ni un écart" in sortie, sortie
    assert "SENTINELLE" not in sortie, sortie
    assert "le seuil" not in sortie, sortie


def test_lancement_sans_b_n_ecrit_aucun_cache(tmp_path, env_isole):
    """Lancé sans `-B`, comme le lance la CI, le script n'écrit aucun `__pycache__` à côté de lui
    en important ses voisins."""
    copie = tmp_path / "modele"
    copie.mkdir()
    for nom in ("texte_pr.py", "documentation.py", "confidentialite.py"):
        shutil.copy2(SCRIPTS / nom, copie / nom)
    fermetures = tmp_path / "fermetures.json"
    fermetures.write_text(FERME_RIEN, encoding="utf-8")
    env = env_isole()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    env.update(CORPS=corps_avec("Aucun."), AUTEUR="EdouardZemb", TETE=TETE)
    r = subprocess.run(
        [sys.executable, str(copie / "texte_pr.py"), "--fermetures", str(fermetures)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "texte de la PR : écarts à la spec : aucun" in r.stdout
    assert [p.name for p in copie.rglob("__pycache__")] == []
