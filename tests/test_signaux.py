"""Tests de signaux.py : ce qui est rouge sur GitHub au démarrage d'une session."""

import json
import os
import sys
import time
import types
from datetime import datetime, timedelta, timezone

import pytest
import signaux
from conftest import appels_de, faux_gh, faux_gh_lent

MAINTENANT = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def run(nom, conclusion, quand, statut="completed", event="push"):
    return {
        "workflowName": nom,
        "event": event,
        "status": statut,
        "conclusion": conclusion,
        "createdAt": quand,
        "url": f"https://exemple.invalid/{nom}",
    }


def pr(numero=24, titre="chore: bump", controles=()):
    return {
        "number": numero,
        "title": titre,
        "url": f"https://exemple.invalid/pr/{numero}",
        "statusCheckRollup": list(controles),
    }


def test_dernier_run_rouge_affiche():
    lignes, n = signaux.executions_rouges(
        [run("historique", "failure", "2026-10-26T10:51:00Z", event="schedule")], MAINTENANT
    )
    assert lignes == [
        "- rouge : historique (schedule, 26/10 10:51 UTC) https://exemple.invalid/historique"
    ]
    assert n == 1


def test_rouge_repare_par_un_vert_absent():
    runs = [
        run("ci", "success", "2026-10-26T10:00:00Z"),
        run("ci", "failure", "2026-10-25T10:00:00Z"),
    ]
    assert signaux.executions_rouges(runs, MAINTENANT) == ([], 1)


def test_vert_puis_rouge_est_rouge():
    runs = [
        run("ci", "failure", "2026-10-26T10:00:00Z"),
        run("ci", "success", "2026-10-25T10:00:00Z"),
    ]
    lignes, n = signaux.executions_rouges(runs, MAINTENANT)
    assert len(lignes) == 1
    assert n == 1


@pytest.mark.parametrize("conclusion", sorted(signaux.CONCLUSIONS_ROUGES))
def test_chaque_conclusion_rouge(conclusion):
    quand = "2026-10-26T10:00:00Z"
    lignes, _ = signaux.executions_rouges([run("ci", conclusion, quand)], MAINTENANT)
    assert len(lignes) == 1
    assert lignes[0].startswith("- rouge : ci")


@pytest.mark.parametrize("conclusion", ["success", "skipped", "neutral", ""])
def test_conclusion_non_rouge(conclusion):
    statut = "completed" if conclusion else "in_progress"
    runs = [run("ci", conclusion, "2026-10-27T11:50:00Z", statut=statut)]
    assert signaux.executions_rouges(runs, MAINTENANT) == ([], 1)


@pytest.mark.parametrize("statut", sorted(signaux.STATUTS_EN_ATTENTE))
def test_attente_de_plus_d_une_heure(statut):
    long = run("ci", None, iso(MAINTENANT - timedelta(hours=2)), statut=statut)
    lignes, _ = signaux.executions_rouges([long], MAINTENANT)
    assert lignes == [
        "- en attente depuis plus d'une heure : ci (push, 27/10 10:00 UTC) https://exemple.invalid/ci"
    ]
    court = run("ci", None, iso(MAINTENANT - timedelta(minutes=30)), statut=statut)
    assert signaux.executions_rouges([court], MAINTENANT)[0] == []


def test_fenetre_de_sept_jours():
    dedans = run("a", "failure", iso(MAINTENANT - timedelta(days=6, hours=23)))
    dehors = run("b", "failure", iso(MAINTENANT - timedelta(days=7, hours=1)))
    lignes, n = signaux.executions_rouges([dedans, dehors], MAINTENANT)
    assert len(lignes) == 1
    assert "a (" in lignes[0]
    assert n == 1


def controle(nom, conclusion="FAILURE"):
    return {"__typename": "CheckRun", "name": nom, "conclusion": conclusion}


def test_pr_rouge():
    p = pr(controles=[controle("tests (windows-latest)")])
    assert signaux.prs_rouges([p]) == [
        ("- PR #24 « chore: bump » : contrôle rouge (tests (windows-latest)) "
         "https://exemple.invalid/pr/24")
    ]


def test_pr_noms_limites_a_trois():
    controles = [controle(n) for n in "abcd"]
    assert "(a, b, c, …)" in signaux.prs_rouges([pr(controles=controles)])[0]


def test_pr_status_context_en_erreur():
    for etat in ("ERROR", "FAILURE"):
        p = pr(controles=[{"__typename": "StatusContext", "context": "x", "state": etat}])
        assert "(x)" in signaux.prs_rouges([p])[0]
    p = pr(controles=[{"__typename": "StatusContext", "context": "x", "state": "SUCCESS"}])
    assert signaux.prs_rouges([p]) == []


def test_pr_sans_controle_ni_controle_en_cours():
    assert signaux.prs_rouges([pr(controles=[])]) == []
    sans = pr()
    sans["statusCheckRollup"] = None
    assert signaux.prs_rouges([sans]) == []
    assert signaux.prs_rouges([pr(controles=[controle("x", "")])]) == []


def test_workflows_desactives():
    wf = [
        {"name": "historique", "state": "disabled_inactivity"},
        {"name": "ci", "state": "disabled_manually"},
        {"name": "autre", "state": "active"},
    ]
    assert signaux.workflows_desactives(wf) == [
        "- désactivé : historique (inactivité)",
        "- désactivé : ci (à la main)",
    ]


def test_rien_de_rouge():
    assert (
        signaux.composer("main", ([], ""), ([], ""), ([], ""), MAINTENANT)
        == "signaux de la CI : rien de rouge (0 workflows exécutés en 7 jours, 0 PR ouvertes)"
    )


def test_rien_de_rouge_compte_workflows_et_prs():
    ok = "2026-10-26T10:00:00Z"
    runs = [run("a", "success", ok), run("b", "success", ok)]
    texte = signaux.composer("main", (runs, ""), ([pr()], ""), ([], ""), MAINTENANT)
    assert texte == (
        "signaux de la CI : rien de rouge (2 workflows exécutés en 7 jours, 1 PR ouvertes)"
    )


def test_du_rouge_et_une_lecture_manquante():
    runs = [run("ci", "failure", "2026-10-26T10:00:00Z")]
    texte = signaux.composer("main", (runs, ""), (None, "délai dépassé"), ([], ""), MAINTENANT)
    lignes = texte.split("\n")
    assert lignes[0] == "signaux de la CI (branche main) :"
    assert lignes[1].startswith("- rouge : ci")
    assert lignes[-1] == "- non lues : PR ouvertes (délai dépassé)"


def test_tout_non_lu():
    vide = (None, "gh absent")
    texte = signaux.composer("main", vide, vide, vide, MAINTENANT)
    assert texte == "signaux de la CI : non lus (gh absent)"


def test_vingt_elements_au_plus():
    runs = [run(f"w{i:02}", "failure", "2026-10-26T10:00:00Z") for i in range(25)]
    texte = signaux.composer("main", (runs, ""), ([], ""), ([], ""), MAINTENANT)
    lignes = texte.split("\n")
    assert lignes[0] == "signaux de la CI (branche main) :"
    assert len(lignes) == 1 + 20 + 1
    assert lignes[-1] == "… et 5 de plus"
    assert len(texte) < 10_000


def test_titre_long_borne():
    p = pr(titre="x" * 5000, controles=[controle("t")])
    assert len(signaux.prs_rouges([p])[0]) < 500


def test_sortie_hook():
    objet = json.loads(signaux.sortie_hook("é"))
    assert objet["systemMessage"] == "é"
    assert objet["hookSpecificOutput"] == {"hookEventName": "SessionStart", "additionalContext": "é"}


# --- main, avec un faux gh ---


def gh_en_tete(monkeypatch, dossier):
    monkeypatch.setenv("PATH", str(dossier) + os.pathsep + os.environ["PATH"])


def sorties(**autres):
    base = {"run list": (0, "[]"), "pr list": (0, "[]"), "workflow list": (0, "[]")}
    base.update({k.replace("_", " "): v for k, v in autres.items()})
    return base


def lancer(capsys):
    code = signaux.main(["--branche", "main"])
    sortie = capsys.readouterr().out
    return code, json.loads(sortie)["systemMessage"]


def test_main_rien_de_rouge(tmp_path, monkeypatch, capsys):
    faux_gh(tmp_path, sorties())
    gh_en_tete(monkeypatch, tmp_path)
    code, texte = lancer(capsys)
    assert code == 0
    assert texte == (
        "signaux de la CI : rien de rouge (0 workflows exécutés en 7 jours, 0 PR ouvertes)"
    )
    appels = appels_de(tmp_path)
    assert "run list --branch main --limit 100" in appels
    assert "pr list --state open --limit 50" in appels
    assert "workflow list --all" in appels


def test_main_du_rouge(tmp_path, monkeypatch, capsys):
    quand = iso(datetime.now(timezone.utc) - timedelta(hours=3))
    runs = [run("historique", "failure", quand, event="schedule")]
    wf = [{"name": "ci", "state": "disabled_inactivity"}]
    faux_gh(tmp_path, sorties(run_list=(0, json.dumps(runs)), workflow_list=(0, json.dumps(wf))))
    gh_en_tete(monkeypatch, tmp_path)
    _, texte = lancer(capsys)
    assert texte.startswith("signaux de la CI (branche main) :")
    assert "- rouge : historique (schedule, " in texte
    assert "- désactivé : ci (inactivité)" in texte


def test_gh_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    code, texte = lancer(capsys)
    assert code == 0
    assert texte == "signaux de la CI : non lus (gh absent)"


def test_gh_en_erreur(tmp_path, monkeypatch, capsys):
    faux_gh(tmp_path, sorties(pr_list=(1, "[]")))
    gh_en_tete(monkeypatch, tmp_path)
    code, texte = lancer(capsys)
    assert code == 0
    assert texte.endswith("- non lues : PR ouvertes (erreur de gh)")


@pytest.mark.parametrize("sortie", ["pas du json", '{"a": 1}'])
def test_gh_illisible(tmp_path, monkeypatch, capsys, sortie):
    faux_gh(tmp_path, sorties(workflow_list=(0, sortie)))
    gh_en_tete(monkeypatch, tmp_path)
    code, texte = lancer(capsys)
    assert code == 0
    assert texte.endswith("- non lues : workflows (réponse illisible)")


def test_budget_epuise(tmp_path, monkeypatch, capsys):
    faux_gh_lent(tmp_path)
    gh_en_tete(monkeypatch, tmp_path)
    monkeypatch.setattr(signaux, "BUDGET", 0.5)
    debut = time.monotonic()
    code, texte = lancer(capsys)
    assert code == 0
    assert "délai dépassé" in texte
    assert time.monotonic() - debut < 2


def test_exception_interne_rend_zero(monkeypatch, capsys):
    def explose(*_):
        raise RuntimeError("boum")

    monkeypatch.setattr(signaux, "composer", explose)
    code, texte = lancer(capsys)
    assert code == 0
    assert texte == "signaux de la CI : non lus (erreur interne)"


def test_sortie_ascii_et_json(tmp_path, monkeypatch, capsys):
    p = pr(titre="réparer é", controles=[controle("t")])
    faux_gh(tmp_path, sorties(pr_list=(0, json.dumps([p]))))
    gh_en_tete(monkeypatch, tmp_path)
    code = signaux.main(["--branche", "main"])
    sortie = capsys.readouterr().out
    assert code == 0
    sortie.encode("ascii")
    objet = json.loads(sortie)
    assert "« réparer é »" in objet["systemMessage"]
    assert objet["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert objet["hookSpecificOutput"]["additionalContext"] == objet["systemMessage"]


def test_branche_des_reglages(tmp_path, monkeypatch, capsys):
    module = types.ModuleType("reglages")
    module.BRANCHE_PRINCIPALE = "trunk"
    monkeypatch.setitem(sys.modules, "reglages", module)
    faux_gh(tmp_path, sorties())
    gh_en_tete(monkeypatch, tmp_path)
    assert signaux.main([]) == 0
    capsys.readouterr()
    assert "--branch trunk" in appels_de(tmp_path)
