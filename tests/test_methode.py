"""Les fichiers gérés de la méthode : méthode, ADR hérités, /consigner, modèles."""

import re

import pytest
import yaml
from conftest import RACINE, REGISTRE_ENTETE, REPONSES_SERVEUR

TEMPLATE = RACINE / "template"
METHODE = TEMPLATE / "docs/modele/methode.md"
DECISIONS = TEMPLATE / "docs/modele/decisions"

SECTIONS = [
    "## Le cycle d'un lot",
    "## Les outils",
    "## Les worktrees",
    "## « Fini »",
    "## Les commits",
    "## Les questions groupées",
    "## Les invariants communs",
    "## Les garde-fous",
    "## Les fichiers gérés par le modèle",
    "## Le registre",
    "## Les familles de garde-fous de l'écosystème",
]


def lire(chemin):
    return chemin.read_text(encoding="utf-8")


def test_methode_sections():
    lignes = lire(METHODE).splitlines()
    assert lignes[0] == "# La méthode des projets nés du modèle"
    assert [ligne for ligne in lignes if ligne.startswith("## ")] == SECTIONS


def test_methode_sans_jinja():
    texte = lire(METHODE)
    assert "{{" not in texte
    assert "{%" not in texte


def test_invariants_communs():
    texte = lire(METHODE)
    section = texte.split("## Les invariants communs", 1)[1].split("\n## ", 1)[0]
    assert len(re.findall(r"^\d+\. ", section, flags=re.MULTILINE)) == 5
    # L'invariant 3, au mot près de la spec (§5.2) : il vaut pour tous, Edouard compris.
    assert (
        "3. Personne n'écrit sur le serveur après son amorçage : tout y arrive par git. "
        "Une session y lit, elle n'y écrit jamais." in " ".join(section.split())
    )


# Les ADR hérités selon la cible : M-0003 et M-0004 pour `serveur`, M-0005 avec les sauvegardes.
ADR_SOCLE = [
    "M-0001-ecosysteme-des-applications-personnelles.md",
    "M-0002-garde-fous-et-confidentialite.md",
]
ADR_SERVEUR = ["M-0003-contrat-de-l-image.md", "M-0004-chaine-de-livraison.md"]
ADR_SAUVEGARDES = ["M-0005-sauvegardes-et-restauration.md"]


@pytest.mark.parametrize(
    ("reponses", "attendus"),
    [
        ({}, ADR_SOCLE),
        ({**REPONSES_SERVEUR, "sauvegardes": False}, ADR_SOCLE + ADR_SERVEUR),
        (REPONSES_SERVEUR, ADR_SOCLE + ADR_SERVEUR + ADR_SAUVEGARDES),
    ],
    ids=["aucune", "serveur-sans-sauvegardes", "serveur-avec-sauvegardes"],
)
def test_adr_herites_format(rendre, reponses, attendus):
    adr = sorted((rendre(**reponses) / "docs/modele/decisions").iterdir())
    assert [a.name for a in adr] == attendus
    for chemin in adr:
        lignes = lire(chemin).splitlines()
        assert re.match(rf"^# {chemin.name[:6]} — .+ : .+$", lignes[0]), chemin.name
        date = "2026-10-16" if chemin.name in ADR_SOCLE else "2026-10-18"
        assert f"- **Statut** : accepté le {date}" in lignes, chemin.name
        for titre in ("## Contexte", "## Décision", "## Conséquences", "## Révision"):
            assert titre in lignes, (chemin.name, titre)


def test_skill_consigner():
    texte = lire(TEMPLATE / ".claude/skills/consigner/SKILL.md")
    _, entete, corps = texte.split("---", 2)
    meta = yaml.safe_load(entete)
    assert meta["name"] == "consigner"
    assert str(meta["description"]).strip()
    assert meta["argument-hint"] == "[constat en une phrase]"
    assert REGISTRE_ENTETE in corps
    assert "$ARGUMENTS" in corps


def test_formulaire_lot():
    formulaire = yaml.safe_load(lire(TEMPLATE / ".github/ISSUE_TEMPLATE/lot.yml"))
    assert formulaire["name"] == "Lot"
    champs = {c["id"]: c for c in formulaire["body"] if c["type"] == "textarea"}
    assert set(champs) == {"objectif", "criteres", "hors-perimetre"}
    for champ in champs.values():
        assert champ["validations"]["required"] is True


def test_modele_de_pr():
    texte = lire(TEMPLATE / ".github/pull_request_template.md")
    for titre in (
        "## Ce que fait cette PR",
        "## Vérifications",
        "## Reste ouvert",
        "## Registre",
        "## Pour un fix : cause racine et prévention",
    ):
        assert titre in texte.splitlines(), titre


# --- revue finale du lot 1 ---

CHEMINS_GERES = (
    "`.githooks/`",
    "`scripts/modele/`",
    "`docs/modele/`",
    "`.github/modele/`",
    "`.github/workflows/modele-*.yml`",
    "`.claude/skills/consigner/`",
)


def test_chemins_geres_exclus_des_formateurs():
    texte = lire(METHODE)
    section = texte.split("## Les fichiers gérés par le modèle", 1)[1].split("\n## ", 1)[0]
    assert "exclus des formateurs et des linters" in section
    for chemin in CHEMINS_GERES:
        assert chemin in section, chemin


def test_garde_fous_a_jour():
    section = lire(METHODE).split("## Les garde-fous", 1)[1].split("\n## ", 1)[0]
    for fragment in (
        "`Monitor`",
        "tout outil MCP",
        "sauf la réparation `git config core.hooksPath .githooks`",
        "tout l'historique chaque semaine et à la demande (`modele-historique.yml`)",
        "des messages de commit",
        "| Dependabot |",
        "un envoi direct de cette tête est accepté et marque la PR fusionnée, sans squash",
        "avertit sur ce qui identifie et refuse toujours les secrets",
        "`DEPOT_PRIVE`",
        "Avant de passer un dépôt privé en public",
        "quatre étapes obligatoires",
        "`git commit -F <fichier>`",
        "`gh pr create --body-file <fichier>`",
        "git log -p --all --no-textconv --no-ext-diff --format='%H%n%B'",
        "--exiger-prives --public --fichiers",
    ):
        assert fragment in section, fragment
    assert "gitleaks sur tout l'historique ;" not in section


def adr_rendu(rendre, nom, **reponses):
    rendu = rendre(**{**REPONSES_SERVEUR, **reponses})
    return " ".join(lire(rendu / "docs/modele/decisions" / nom).split())


def test_m0003_dit_ce_que_la_ci_ne_prouve_pas(rendre):
    """R23 : la CI lance les deux commandes par `docker exec`, qui contourne l'`ENTRYPOINT`."""
    texte = adr_rendu(rendre, "M-0003-contrat-de-l-image.md")
    assert "Le contrat se vérifie à chaque PR" not in texte
    assert "`SAUVEGARDER` et `VERIFIER` dans le conteneur, par `docker exec`" in texte
    assert "La CI ne prouve pas la clause de l'`ENTRYPOINT`" in texte
    assert "le test de restauration" in texte
    # R24 : la mécanique ne pose que deux variables en CI, le projet peut en ajouter
    assert "la mécanique ne pose que `ESSAI_ENV=ci` et `ESSAI_URL_PUBLIQUE`" in texte


@pytest.mark.parametrize("sauvegardes", [True, False])
def test_m0004_ne_renvoie_a_m0005_qu_avec_sauvegardes(rendre, sauvegardes):
    """R24 : sans sauvegardes, M-0005 n'est pas rendu, et M-0004 n'y renvoie pas."""
    texte = adr_rendu(rendre, "M-0004-chaine-de-livraison.md", sauvegardes=sauvegardes)
    assert ("M-0005" in texte) is sauvegardes
    assert ("instantané" in texte) is sauvegardes


def test_m0002_amende():
    texte = lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md")
    assert "le contrôle de dérive en tient compte" not in texte
    assert "le garde de Claude est alors la seule serrure côté agent" in texte
    assert "elle avertit sur ce qui identifie" in texte
    assert "refuse toujours les secrets" in texte
    assert "gitleaks n'est pas concerné" not in texte
    assert "github.event.repository.private" in texte
    assert "quatre étapes obligatoires" in texte
    assert "git log -p --all" in texte
    assert "`Monitor`" in texte
    assert "PR obligatoire" not in texte
    # amendement du 18/10 : qui fusionne (`fusion`), et les étiquettes réservées à Edouard
    assert "- **Amendé** le 2026-10-18" in texte
    assert "`fusion`" in texte
    assert "étiquette" in texte
