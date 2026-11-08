"""Le texte de la PR (`scripts/modele/texte_pr.py`) : la section « Écarts à la spec » (LE-37), et la
tête relue d'une PR qui ferme une issue (LE-55)."""

import json
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
# une réponse partielle : le compte est lu, mais une erreur l'accompagne (le doute d'un dépôt privé
# et de `issues: read`) ; seule la clé `errors` la fait refuser
FERME_EN_ERREUR = FERME_RIEN[:-1] + ',"errors":[{"type":"FORBIDDEN"}]}'
FERME_NEGATIF = FERME_RIEN.replace('"totalCount":0', '"totalCount":-1')
# un booléen est un entier pour Python : `false` passerait pour 0, `true` pour 1
FERME_FAUX = FERME_RIEN.replace('"totalCount":0', '"totalCount":false')
FERME_VRAI = FERME_RIEN.replace('"totalCount":0', '"totalCount":true')
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
        # un commentaire en tête de ligne, puis un écart : GitHub rend la ligne en bloc HTML, son
        # texte tel quel, jamais en puce
        ("Aucun.\n<!-- x --> " + ECART, 1, "ligne 3 de la section : ni « Aucun. » ni un écart"),
        (
            "Aucun.\n\n<!-- - <écart> — promesse : <§> — accord d'Edouard : JJ/MM/AAAA -->",
            0,
            "aucun",
        ),
        ("Aucun.\n\n```\n" + ECART + "\n```", 0, "aucun"),
        ("Aucun.\n\n<!--\n" + ECART, 1, "commentaire HTML non fermé"),
        # la forme stricte : l'écart, puis la promesse, puis l'accord, dont la date termine la ligne
        (
            ECART.replace("07/11/2026", "07/11/2026 puis"),
            1,
            "ligne 2 de la section : texte après la date de l'accord, qui termine la ligne",
        ),
        (
            ECART + "\n  à l'oral",  # une ligne de continuation après la date
            1,
            "ligne 2 de la section : texte après la date de l'accord, qui termine la ligne",
        ),
        (
            "- x — accord d'Edouard : 07/11/2026 — promesse : § 2",
            1,
            (
                "ligne 2 de la section : l'écart, puis « promesse : », puis « accord d'Edouard :"
                " JJ/MM/AAAA » en fin de ligne"
            ),
        ),
        (
            "- — promesse : § 2 — accord d'Edouard : 07/11/2026",
            1,
            "ligne 2 de la section : écart vide avant « promesse : »",
        ),
        # l'écart peut contenir un séparateur
        ("- a — b — promesse : § 2 — accord d'Edouard : 07/11/2026", 0, "1 déclaré"),
        # un commentaire en tête de ligne, collé à la puce : GitHub rend la ligne en bloc HTML,
        # jamais en puce ; de même après un écart, où il ne le continue pas
        (
            ECART + "\n<!-- x -->- y — promesse : § 1 — accord d'Edouard : 07/11/2026",
            1,
            "ligne 3 de la section : ni « Aucun. » ni un écart",
        ),
        (ECART + "\n   <!-- x --> suite", 1, "ligne 3 de la section : ni « Aucun. » ni un écart"),
        (
            ECART + "\n<!-- x\ny --> suite",  # le texte suit la fermeture, sur sa ligne
            1,
            "ligne 4 de la section : ni « Aucun. » ni un écart",
        ),
        ("Aucun.\n\n```\n<!-- x -->- y\n```", 0, "aucun"),  # dans un bloc clôturé
        # un bloc indenté de quatre espaces : il continue l'écart d'avant, ou il refuse
        ("- un écart long\n    — promesse : § 2 — accord d'Edouard : 07/11/2026", 0, "1 déclaré"),
        ("Aucun.\n\n    un bloc indenté", 1, "ligne 4 de la section : ni « Aucun. » ni un écart"),
        # un commentaire après quatre espaces, puis un texte : au-delà de la borne des trois
        # espaces, la ligne continue l'écart d'avant, et GitHub la montre dans la puce
        # (relecture de la revue finale du lot 15, ronde 3)
        (
            "- un écart long — promesse : § 2\n    <!-- c --> — accord d'Edouard : 07/11/2026",
            0,
            "écarts à la spec : 1 déclaré",
        ),
        # une ligne qui commence par `-` sans être une puce, faute d'un blanc après lui, ou qui
        # porte un marqueur au milieu : elle continue l'écart d'avant, et GitHub la montre dans la
        # puce (relecture de la revue finale du lot 15, ronde 4)
        (
            (
                "- un écart — promesse : spec § 4.1\n  -v est l'option\n"
                "  — accord d'Edouard : 07/11/2026"
            ),
            0,
            "écarts à la spec : 1 déclaré",
        ),
        (
            (
                "- un écart\n  le cas - un autre cas\n"
                "  — promesse : § 2 — accord d'Edouard : 07/11/2026"
            ),
            0,
            "écarts à la spec : 1 déclaré",
        ),
        (
            (
                "- un écart\n  voir le point 3) plus haut\n"
                "  — promesse : § 2 — accord d'Edouard : 07/11/2026"
            ),
            0,
            "écarts à la spec : 1 déclaré",
        ),
    ],
)
def test_ecarts(lancer, section, code, attendu):
    rendu, sortie = lancer(corps_avec(section))
    assert rendu == code, sortie
    assert attendu in sortie, sortie
    assert (REFUS in sortie) == (code == 1), sortie


@pytest.mark.parametrize(
    "sous_liste",
    [
        *(f"  {puce} une sous-puce" for puce in ("-", "*", "+", "1.", "1)", "2.")),
        # « 2. » et une sous-puce à six espaces, que GitHub joint à la puce d'avant, et une
        # sous-puce à quatre espaces, qu'il imbrique : tous refusés (relecture de la revue finale
        # du lot 15, ronde 2)
        "    - une sous-puce",
        "      - une sous-puce",
        # une puce seule en fin de ligne : jointe, elle laisserait un texte après la date, à la
        # ligne 2 (relecture de la revue finale du lot 15)
        "  -",
    ],
)
def test_ecarts_sous_liste(lancer, sous_liste):
    """Une ligne indentée qui commence par une puce ou un numéro est une sous-liste, pas la suite
    de l'écart d'avant : elle refuse, à son rang, au lieu d'être jointe sans être lue."""
    code, sortie = lancer(corps_avec(ECART + "\n" + sous_liste))
    assert code == 1, sortie
    assert "ligne 3 de la section : ni « Aucun. » ni un écart" in sortie, sortie


def test_ecarts_section_en_double(lancer):
    """Deux sections « Écarts à la spec » : la seconde refuse, au lieu d'être jointe à la première."""
    corps = "## Écarts à la spec\n\nAucun.\n\n## Écarts à la spec\n\n" + ECART + "\n"
    code, sortie = lancer(corps)
    assert code == 1, sortie
    assert "écarts à la spec : section en double (un seul titre de niveau 2" in sortie, sortie
    assert REFUS in sortie, sortie


def test_le_code_en_ligne_vient_de_documentation():
    """`texte_pr.py` lit le code en ligne comme `documentation.py`, sans sa propre copie."""
    import documentation as d

    assert not hasattr(t, "_CODE_EN_LIGNE")
    assert d._CODE_OU_COMMENTAIRE.pattern.endswith("|" + d.CODE_EN_LIGNE.pattern)
    assert d._CODE_OU_COMMENTAIRE.pattern.startswith(d.COMMENTAIRE.pattern + "|")


def test_docstring_dit_les_refus_et_les_ecarts_du_rendu():
    """La docstring de `texte_pr.py` dit ce que dit `methode.md` (relecture de la revue finale du
    lot 15) : le rang n'est promis qu'aux refus d'une ligne, et la tête relue se cherche telle que
    GitHub la montre, à des écarts près, dont deux connus et une phrase pour les autres formes :
    une liste non close (sa ronde 3), tous bornés par le SHA, qui doit égaler la tête."""
    docstring = " ".join(t.__doc__.split())
    for fragment in (
        (
            "Le contrôle refuse, sans nommer de ligne : une section absente, vide ou en double ; "
            "« Aucun. » à côté d'un écart ; un `<!--` jamais fermé dans la section, qui cacherait "
            "la suite."
        ),
        (
            "Il refuse, en nommant la ligne par son rang dans la section, la ligne 1 étant celle "
            "qui suit le titre : une ligne qui n'est ni « Aucun. » ni un écart, une sous-liste "
            "comprise ; un écart vide, sans « promesse : » suivi d'un texte, sans « accord "
            "d'Edouard : » suivi d'une vraie date, avec un texte après la date, ou hors de cet "
            "ordre."
        ),
        (
            "une ligne qu'il cache est absente. À des écarts près, dont deux connus : un `<!--` "
            "jamais fermé, ouvert dans un élément de liste après quatre espaces ou plus (une puce "
            "imbriquée, ou une ligne qui continue la puce), cache sur GitHub tout ce qui le suit, "
            "et un `<?`, un `<!` suivi d'une majuscule (`<!DOCTYPE`) ou un `<![CDATA[` ouvert en "
            "tête de ligne, tout ce qui le suit jusqu'au premier `>`, même plusieurs lignes plus "
            "bas, ou jusqu'à la fin sans lui ; le contrôle lit encore ces lignes, la ligne « Tête "
            "relue » comme la section des écarts. D'autres formes HTML cachent aussi sur GitHub ce "
            "que le contrôle lit : un `<?` ou un `<!DOCTYPE` après une puce, ou en ligne et fermé "
            "plus bas ; un `<!--` jamais fermé dans une ligne de bloc HTML, comme "
            "`<div><!-- note</div>` ; un attribut ou un titre de lien sur plusieurs lignes. Tous "
            "sont bornés : le SHA de cette ligne doit toujours égaler la tête de la PR."
        ),
    ):
        assert fragment in docstring, fragment
    # la liste des écarts du rendu n'est plus close (relecture de la revue finale du lot 15,
    # ronde 3) : ni l'ancien décompte, ni l'ancienne borne, quelle que soit la casse
    for perime in ("à deux écarts près", "les deux écarts sont bornés"):
        assert perime not in docstring.casefold(), perime
    ancien = (
        "Le refus nomme la ligne par son rang dans la section, la ligne 1 étant celle qui suit le "
        "titre : une section absente"
    )
    assert ancien not in docstring


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
        (f"Tête relue : {TETE.upper()}", FERME_UNE, 0, "tête relue égale à la tête aaaaaaaaaaaa"),
        (f"TÊTE RELUE : {TETE}", FERME_UNE, 0, "tête relue égale à la tête aaaaaaaaaaaa"),
        (f"Tête relue : {'b' * 40}", FERME_UNE, 1, f"différente de la tête {TETE}"),
        ("", FERME_UNE, 1, ABSENTE),
        ("Tête relue : ", FERME_UNE, 1, ABSENTE),
        (f"Tête relue : {TETE[:12]}", FERME_UNE, 1, ABSENTE),
        (f"<!-- Tête relue : {TETE} -->", FERME_UNE, 1, ABSENTE),
        # la ligne se cherche hors des blocs de code et des commentaires : dans un bloc clôturé,
        # ou dans un commentaire fermé ouvert au milieu d'un paragraphe, elle est absente
        (f"```\nTête relue : {TETE}\n```", FERME_UNE, 1, ABSENTE),
        (f"texte <!--\nTête relue : {TETE}\n-->", FERME_UNE, 1, ABSENTE),
        # un commentaire jamais fermé, ouvert en tête de ligne ou après une puce, cache sur GitHub
        # tout ce qui le suit ; au milieu d'un paragraphe, il reste du texte, et la ligne se voit
        (f"<!-- note\n\nTête relue : {TETE}", FERME_UNE, 1, ABSENTE),
        (f"- <!-- note\n\nTête relue : {TETE}", FERME_UNE, 1, ABSENTE),
        (f"texte <!-- note\n\nTête relue : {TETE}", FERME_UNE, 0, "égale à la tête aaaaaaaaaaaa"),
        (f"Tête relue : {TETE}\n\n<!-- note", FERME_UNE, 0, "égale à la tête aaaaaaaaaaaa"),
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
        ("", FERME_EN_ERREUR, 1, ILLISIBLES),
        ("", FERME_NEGATIF, 1, ILLISIBLES),
        ("", FERME_FAUX, 1, ILLISIBLES),
        ("", FERME_VRAI, 1, ILLISIBLES),
        ("", "null", 1, ILLISIBLES),  # un JSON qui n'est pas un objet
        # une réponse qui n'est pas du JSON : la page d'un 502, une sortie tronquée
        ("", "<html>502</html>", 1, ILLISIBLES),
        ("", FERME_UNE[:-3], 1, ILLISIBLES),
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


@pytest.mark.parametrize(
    ("fermetures", "total"),
    [(FERME_EN_ERREUR, 0), (FERME_NEGATIF, -1), (FERME_FAUX, False), (FERME_VRAI, True)],
)
def test_reponses_refusees_par_leur_seule_valeur(fermetures, total):
    """Ces réponses se lisent en JSON, avec la PR et son compte : elles ne refusent que par la clé
    `errors` ou par la valeur du compte. Mal formées, elles refuseraient pour une autre raison, et
    leur cas de `test_tete_relue` passerait à vide (LE-62)."""
    reponse = json.loads(fermetures)
    compte = reponse["data"]["repository"]["pullRequest"]["closingIssuesReferences"]["totalCount"]
    assert (compte, type(compte)) == (total, type(total))
    assert ("errors" in reponse) == (fermetures == FERME_EN_ERREUR)


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


def test_quarante_citations_sans_commentaire_se_lisent_vite(tmp_path, env_isole):
    """Un corps de PR, que n'importe qui peut écrire dans un dépôt public, ne fige pas le contrôle :
    une ligne de 40 `> `, puis une de 40 puces suivies de deux espaces, sans `<!--`, se lisent en
    moins de 2 s, les écarts comme la tête relue. Le contrôle tourne dans un sous-processus tué au
    bout de 30 s : un recul ne fige pas la suite."""
    fermetures = tmp_path / "fermetures.json"
    fermetures.write_text(FERME_UNE, encoding="utf-8")
    lignes = "> " * 40 + "\n\n" + "-  " * 40 + "\n"
    env = env_isole()
    env.update(
        CORPS=corps_avec("Aucun.") + "\n" + lignes + "\nTête relue : " + TETE + "\n",
        AUTEUR="EdouardZemb",
        TETE=TETE,
    )
    mesure = (
        "import sys, time\n"
        "import texte_pr\n"
        "debut = time.perf_counter()\n"
        "code = texte_pr.main(['--fermetures', sys.argv[1]])\n"
        "print('mesure', code, time.perf_counter() - debut)\n"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-B", "-c", mesure, str(fermetures)],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env=env,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("la lecture ne finit pas en 30 s : le motif recule")
    mesures = [ligne.split() for ligne in r.stdout.splitlines() if ligne.startswith("mesure ")]
    assert mesures, r.stdout + r.stderr
    _, code, duree = mesures[-1]
    assert code == "0", r.stdout + r.stderr
    assert "tête relue égale à la tête aaaaaaaaaaaa" in r.stdout, r.stdout
    assert float(duree) < 2, r.stdout


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
