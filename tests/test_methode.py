"""Les fichiers gérés de la méthode : méthode, ADR hérités, /consigner, modèles."""

import re

import yaml
from conftest import RACINE, REGISTRE_ENTETE

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


def test_adr_herites_format():
    adr = sorted(DECISIONS.glob("*.md"))
    assert [a.name[:6] for a in adr] == ["M-0001", "M-0002"]
    for chemin in adr:
        texte = lire(chemin)
        assert re.match(r"^# M-\d{4} — .+ : .+$", texte.splitlines()[0]), chemin.name
        assert "**Statut** : accepté le 2026-10-16" in texte, chemin.name
        for titre in ("## Contexte", "## Décision", "## Conséquences", "## Révision"):
            assert titre in texte.splitlines(), (chemin.name, titre)


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
        "avertit sans refuser",
        "Avant de passer un dépôt privé en public",
    ):
        assert fragment in section, fragment
    assert "gitleaks sur tout l'historique ;" not in section


def test_m0002_amende():
    texte = lire(DECISIONS / "M-0002-garde-fous-et-confidentialite.md")
    assert "le contrôle de dérive en tient compte" not in texte
    assert "le garde de Claude est alors la seule serrure côté agent" in texte
    assert "elle avertit sans refuser" in texte
    assert "`Monitor`" in texte
    assert "PR obligatoire" not in texte
