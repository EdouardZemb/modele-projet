"""Tests de la porte de confidentialité. Aucun faux secret n'est écrit en clair : tout est construit."""

import subprocess
import sys

import confidentialite as c
import pytest
from conftest import SCRIPTS

CLE_AGE = "AGE-SECRET-KEY-1" + "Q" * 58
SCRIPT = SCRIPTS / "confidentialite.py"

ECHANTILLONS = {
    "adresse IP privée": "serveur 192.168" + ".1.20",
    "adresse Tailscale": "noeud 100.101" + ".2.3",
    "cible SSH": "ssh " + "-oBatchMode=yes " + "deploy" + "@" + "hote.exemple",
    "cible scp": "scp f " + "deploy" + "@" + "hote:/tmp/f",
    "clé privée age": CLE_AGE,
    "clé privée PEM": "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----",
    "jeton GitHub": "ghp_" + "A" * 36,
    "JWT": "eyJ" + "a" * 10 + ".eyJ" + "b" * 10 + "." + "c" * 10,
    "jeton de tunnel Cloudflare": "eyJ" + "A" * 120,
    "adresse de ping Healthchecks": "hc-ping.com/" + "a" * 24,
}


def test_tous_les_motifs_ont_un_echantillon():
    assert {m.nom for m in c.MOTIFS_GENERIQUES} == set(ECHANTILLONS)


@pytest.mark.parametrize("nom", [m.nom for m in c.MOTIFS_GENERIQUES])
def test_motifs_generiques_detectent(nom):
    constats = c.examiner([("f.txt:1", ECHANTILLONS[nom])], c.MOTIFS_GENERIQUES)
    assert [x.motif for x in constats] == [nom]
    assert constats[0].emplacement == "f.txt:1"


@pytest.mark.parametrize(
    "texte",
    [
        "git@github.com:EdouardZemb/x.git",
        "noreply@anthropic.com",
        "corepack pnpm@10.34.2",
        "version 10.34.2",
        "@docs/modele/methode.md",
        "age1" + "q" * 58,
    ],
)
def test_faux_positifs_ecartes(texte):
    assert c.examiner([("f.txt:1", texte)], c.MOTIFS_GENERIQUES) == []


def test_motifs_prives_litteral_et_regex():
    motifs = c.charger_motifs_prives("# commentaire\nValeur-Privee\nre:^machine-\\d+$\n")
    assert len(motifs) == 2
    a = c.examiner([("f:1", "valeur-privee")], motifs)
    assert [x.motif for x in a] == ["motif privé n°1"]
    b = c.examiner([("f:1", "machine-42")], motifs)
    assert [x.motif for x in b] == ["motif privé n°2"]


def test_motifs_prives_crlf_et_regex_invalide():
    motifs = c.charger_motifs_prives("abc\r\n\r\nxyz\r\n")
    assert len(motifs) == 2
    with pytest.raises(ValueError) as e:
        c.charger_motifs_prives("re:(secret-inconnu")
    assert "secret-inconnu" not in str(e.value)
    assert "n°1" in str(e.value)


def test_source_motifs_prives(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("MOTIFS_INTERDITS", raising=False)
    assert c.source_motifs_prives(None) is None
    defaut = tmp_path / ".config/modele-projet/motifs-interdits.txt"
    defaut.parent.mkdir(parents=True)
    defaut.write_bytes(b"\xef\xbb\xbfpremier\r\n")
    assert (
        c.source_motifs_prives(None) == "premier\n" or c.source_motifs_prives(None) == "premier\r\n"
    )
    assert len(c.charger_motifs_prives(c.source_motifs_prives(None))) == 1
    # le BOM ne corrompt pas le premier motif
    m = c.charger_motifs_prives(c.source_motifs_prives(None))
    assert c.examiner([("f:1", "premier")], m)
    monkeypatch.setenv("MOTIFS_INTERDITS", "deuxieme")
    assert c.source_motifs_prives(None) == "deuxieme"
    fichier = tmp_path / "m.txt"
    fichier.write_text("troisieme", encoding="utf-8")
    assert c.source_motifs_prives(str(fichier)) == "troisieme"


def lancer(args, env, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
        cwd=cwd,
    )


def test_sortie_ne_divulgue_rien(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "valeur-privee-xyz"
    f = tmp_path / "f.txt"
    f.write_text(f"a valeur-privee-xyz\n{CLE_AGE}\n", encoding="utf-8")
    r = lancer(["--fichiers", str(f)], env)
    assert r.returncode == 1
    sortie = r.stdout + r.stderr
    assert "valeur-privee-xyz" not in sortie
    assert CLE_AGE not in sortie
    assert "motif privé n°1" in sortie
    assert "clé privée age" in sortie


def test_regex_invalide_ne_divulgue_pas(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "re:(motif-secret-zzz"
    f = tmp_path / "f.txt"
    f.write_text("x\n", encoding="utf-8")
    r = lancer(["--fichiers", str(f)], env)
    assert r.returncode == 64
    assert "motif-secret-zzz" not in r.stdout + r.stderr


def test_exiger_prives_sans_liste(tmp_path, env_isole):
    f = tmp_path / "f.txt"
    f.write_text("rien\n", encoding="utf-8")
    assert lancer(["--exiger-prives", "--texte", str(f)], env_isole()).returncode == 64


def test_usage(env_isole):
    assert lancer([], env_isole()).returncode == 64
    assert lancer(["--index", "--texte", "x"], env_isole()).returncode == 64


def git(cwd, env, *args):
    r = subprocess.run(
        ["git", *args],
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def depot(tmp_path, env):
    d = tmp_path / "depot"
    d.mkdir()
    git(d, env, "init", "-q", "-b", "main")
    git(d, env, "config", "core.autocrlf", "false")
    return d


def test_index_ne_regarde_que_les_ajouts(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "f.txt").write_text(CLE_AGE + "\n", encoding="utf-8")
    git(d, env, "add", "f.txt")
    git(d, env, "commit", "-qm", "init")
    (d / "f.txt").write_text("propre\n", encoding="utf-8")
    git(d, env, "add", "f.txt")
    assert lancer(["--index"], env, d).returncode == 0
    git(d, env, "commit", "-qm", "nettoyage")
    (d / "f.txt").write_text("propre\n" + CLE_AGE + "\n", encoding="utf-8")
    git(d, env, "add", "f.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "f.txt:2" in r.stderr
    assert CLE_AGE not in r.stdout + r.stderr


def test_index_examine_les_chemins(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = depot(tmp_path, env)
    (d / "nom-prive.txt").write_text("ok\n", encoding="utf-8")
    git(d, env, "add", "nom-prive.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "nom-prive" not in r.stdout + r.stderr


def test_diff_depuis_base(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a\n", encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    git(d, env, "switch", "-qc", "branche")
    (d / "b.txt").write_text(CLE_AGE + "\n", encoding="utf-8")
    git(d, env, "add", "b.txt")
    git(d, env, "commit", "-qm", "ajout")
    r = lancer(["--diff", "main"], env, d)
    assert r.returncode == 1
    assert "b.txt:1" in r.stderr
    r = lancer(["--diff", "0" * 40], env, d)
    assert r.returncode == 1
    assert "b.txt:1" in r.stderr


def test_fichier_binaire_ignore(tmp_path, env_isole):
    f = tmp_path / "b.bin"
    f.write_bytes(b"\0" + CLE_AGE.encode())
    assert lancer(["--fichiers", str(f)], env_isole()).returncode == 0


def test_message(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "valeur-privee-xyz"
    f = tmp_path / "msg.txt"
    f.write_text("feat: truc valeur-privee-xyz\n", encoding="utf-8")
    assert lancer(["--message", str(f)], env).returncode == 1
