"""Tests de la porte de confidentialité. Aucun faux secret n'est écrit en clair : tout est construit."""

import subprocess
import sys

import confidentialite as c
import pytest
from conftest import SCRIPTS, depot, git

CLE_AGE = "AGE-SECRET-KEY-1" + "Q" * 58
SCRIPT = SCRIPTS / "confidentialite.py"

ECHANTILLONS = {
    "adresse IP privée": "serveur 192.168" + ".1.20",
    "adresse Tailscale": "noeud 100.101" + ".2.3",
    "cible SSH": "ssh -p 22 " + "deploy" + "@" + "hote.exemple",
    "cible scp": "scp f " + "deploy" + "@" + "hote:/tmp/f",
    "cible scp à hôte pointé": "scp f " + "deploy" + "@" + "hote" + ".lan:/tmp/f",
    "adresse IPv6 Tailscale": "noeud fd7a" + ":115c" + ":a1e0::1",
    "nom MagicDNS Tailscale": "https://machine" + ".tailnet-ab12" + ".ts" + ".net/",
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
        "ssh -T git@github.com",
        "essai@example.com",
        "les noms *.ts" + ".net de Tailscale",
        "https://docs.ts" + ".network/x",
        "fd7a:1",
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


def test_fichier_binaire_signale_sans_refus(tmp_path, env_isole):
    f = tmp_path / "b.bin"
    f.write_bytes(b"\0" + CLE_AGE.encode())
    r = lancer(["--fichiers", str(f)], env_isole())
    assert r.returncode == 0
    assert f"confidentialité : fichier binaire non examiné : {f}" in r.stderr
    assert CLE_AGE not in r.stdout + r.stderr


def test_message(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "valeur-privee-xyz"
    f = tmp_path / "msg.txt"
    f.write_text("feat: truc valeur-privee-xyz\n", encoding="utf-8")
    assert lancer(["--message", str(f)], env).returncode == 1


@pytest.mark.parametrize(
    "commande",
    [
        "ssh -p 22 " + "u" + "@" + "machine",
        "ssh -i ~/.ssh/cle " + "u" + "@" + "machine",
        "ssh -J saut " + "u" + "@" + "machine",
        "ssh " + "Deploy" + "@" + "machine",
    ],
)
def test_cible_ssh_formes(commande):
    constats = c.examiner([("f:1", commande)], c.MOTIFS_GENERIQUES)
    assert [x.motif for x in constats] == ["cible SSH"]


def test_retour_chariot_isole_ne_cache_rien(tmp_path, env_isole):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a" + chr(10), encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    git(d, env, "switch", "-qc", "branche")
    (d / "b.txt").write_bytes(b"abc" + bytes([13]) + CLE_AGE.encode() + bytes([10]))
    git(d, env, "add", "b.txt")
    assert lancer(["--index"], env, d).returncode == 1
    git(d, env, "commit", "-qm", "ajout")
    assert lancer(["--diff", "main"], env, d).returncode == 1


@pytest.mark.parametrize("base", ["", "  ", "-x", "nexistepas"])
def test_base_invalide(tmp_path, env_isole, base):
    env = env_isole()
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a" + chr(10), encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    assert lancer(["--diff", base], env, d).returncode == 64


def test_chemin_absent_ou_dossier(tmp_path, env_isole):
    r = lancer(["--fichiers", str(tmp_path / "n-existe-pas.txt")], env_isole())
    assert r.returncode == 64
    assert "n-existe-pas" not in r.stdout + r.stderr
    assert lancer(["--fichiers", str(tmp_path)], env_isole()).returncode == 64


# --- revue finale du lot 1 : binaires, UTF-16, textconv (I3, L.13, L.14), BOM en variable (m1) ---

IP = "hote 192.168" + ".1.20"


def utf16(texte, ordre="le"):
    bom = b"\xff\xfe" if ordre == "le" else b"\xfe\xff"
    return bom + texte.encode(f"utf-16-{ordre}")


def test_source_motifs_prives_bom_en_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("MOTIFS_INTERDITS", "\ufeffmotif-essai\n")
    m = c.charger_motifs_prives(c.source_motifs_prives(None))
    assert [x.motif for x in c.examiner([("f:1", "un motif-essai ici")], m)] == ["motif privé n°1"]


def test_bom_en_variable_detecte(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "\ufeffmotif-essai"
    f = tmp_path / "f.txt"
    f.write_text("un motif-essai ici\n", encoding="utf-8")
    assert lancer(["--fichiers", str(f)], env).returncode == 1


@pytest.mark.parametrize("ordre", ["le", "be"])
def test_utf16_examine_fichiers(tmp_path, env_isole, ordre):
    f = tmp_path / "reseau.txt"
    f.write_bytes(utf16("entete\r\n" + IP + "\r\n", ordre))
    r = lancer(["--fichiers", str(f)], env_isole())
    assert r.returncode == 1
    assert f"{f}:2 — adresse IP privée" in r.stderr
    assert "192.168" not in r.stdout + r.stderr


def _depot_avec_base(tmp_path, env):
    d = depot(tmp_path, env)
    (d / "a.txt").write_text("a\n", encoding="utf-8")
    git(d, env, "add", "a.txt")
    git(d, env, "commit", "-qm", "init")
    git(d, env, "switch", "-qc", "branche")
    return d


def test_utf16_examine_index_et_diff(tmp_path, env_isole):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    (d / "reseau.txt").write_bytes(utf16(IP + "\n"))
    git(d, env, "add", "reseau.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "reseau.txt:1 — adresse IP privée" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    r = lancer(["--diff", "main"], env, d)
    assert r.returncode == 1
    assert "reseau.txt:1 — adresse IP privée" in r.stderr
    assert lancer(["--diff", "0" * 40], env, d).returncode == 1


def test_binaire_signale_index_et_diff(tmp_path, env_isole):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    (d / "b.dat").write_bytes(b"\0" + IP.encode())
    git(d, env, "add", "b.dat")
    r = lancer(["--index"], env, d)
    assert r.returncode == 0
    assert "confidentialité : fichier binaire non examiné : b.dat" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    r = lancer(["--diff", "main"], env, d)
    assert r.returncode == 0
    assert "fichier binaire non examiné : b.dat" in r.stderr


def test_binaire_au_chemin_prive_masque(tmp_path, env_isole):
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "nom-prive"
    d = _depot_avec_base(tmp_path, env)
    (d / "nom-prive.dat").write_bytes(b"\0x")
    git(d, env, "add", "nom-prive.dat")
    r = lancer(["--index"], env, d)
    assert "fichier binaire non examiné : <chemin masqué>" in r.stderr
    assert "nom-prive" not in r.stdout + r.stderr


def test_textconv_ne_vide_rien(tmp_path, env_isole):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    git(d, env, "config", "diff.vide.textconv", "sh -c ':'")
    (d / ".gitattributes").write_text("*.cfg diff=vide\n", encoding="utf-8")
    (d / "c.cfg").write_text(IP + "\n", encoding="utf-8")
    git(d, env, "add", ".gitattributes", "c.cfg")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "c.cfg:1 — adresse IP privée" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    assert lancer(["--diff", "main"], env, d).returncode == 1


@pytest.mark.parametrize("attribut", ["-diff", "binary"])
def test_texte_marque_binaire_examine(tmp_path, env_isole, attribut):
    env = env_isole()
    d = _depot_avec_base(tmp_path, env)
    (d / ".gitattributes").write_text(f"*.txt {attribut}\n", encoding="utf-8")
    (d / "note.txt").write_text("rien\n" + IP + "\n", encoding="utf-8")
    git(d, env, "add", ".gitattributes", "note.txt")
    r = lancer(["--index"], env, d)
    assert r.returncode == 1
    assert "note.txt:2 — adresse IP privée" in r.stderr
    git(d, env, "commit", "-qm", "ajout")
    assert lancer(["--diff", "main"], env, d).returncode == 1


DIFF_PLUSIEURS_HUNKS = [
    "diff --git a/x y.txt b/x y.txt",
    "--- a/x y.txt",
    "+++ b/x y.txt",
    "@@ -1 +1 @@",
    "-ancien",
    "+nouveau",
    "@@ -10,0 +11,2 @@",
    "++double plus",
    "+deux",
    "@@ -20,3 +23 @@",
    "-a",
    "-b",
    "-c",
    "+seul",
    "diff --git a/z b/z",
    "--- a/z",
    "+++ /dev/null",
    "@@ -1 +0,0 @@",
    "-supprimé",
]


def test_lignes_ajoutees():
    diff = chr(10).join(DIFF_PLUSIEURS_HUNKS)
    assert list(c.lignes_ajoutees(diff)) == [
        ("x y.txt:1", "nouveau"),
        ("x y.txt:11", "+double plus"),
        ("x y.txt:12", "deux"),
        ("x y.txt:23", "seul"),
    ]


# --- revue finale du lot 1, section I : un dépôt privé avertit sans refuser ---

AVERTISSEMENT = "1 constat(s), dépôt privé : avertissement, pas de refus"


def lancer_porte(script, args, env, cwd=None):
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
        cwd=cwd,
    )


def test_depot_prive_avertit(rendre, tmp_path, env_isole):
    script = rendre(visibilite="prive") / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text("rien\n" + IP + "\n", encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env_isole())
    assert r.returncode == 0, r.stderr
    assert f"{f}:2 — adresse IP privée" in r.stderr
    assert f"confidentialité : {AVERTISSEMENT}" in r.stderr
    assert "refus." not in r.stderr


def test_depot_public_refuse(rendre, tmp_path, env_isole):
    script = rendre(visibilite="public") / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text(IP + "\n", encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env_isole())
    assert r.returncode == 1
    assert "confidentialité : 1 constat(s), refus." in r.stderr
    assert "avertissement" not in r.stderr


def test_depot_modele_sans_reglages_refuse(tmp_path, env_isole):
    assert not (SCRIPTS / "reglages.py").exists()
    f = tmp_path / "f.txt"
    f.write_text(IP + "\n", encoding="utf-8")
    r = lancer(["--fichiers", str(f)], env_isole())
    assert r.returncode == 1
    assert "refus." in r.stderr


def test_depot_prive_ne_divulgue_rien(rendre, tmp_path, env_isole):
    script = rendre(visibilite="prive") / "scripts/modele/confidentialite.py"
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "valeur-privee-xyz"
    f = tmp_path / "f.txt"
    f.write_text(f"a valeur-privee-xyz\n{CLE_AGE}\n", encoding="utf-8")
    r = lancer_porte(script, ["--fichiers", str(f)], env)
    assert r.returncode == 0
    sortie = r.stdout + r.stderr
    assert "valeur-privee-xyz" not in sortie
    assert CLE_AGE not in sortie
    assert "motif privé n°1" in sortie
    assert "clé privée age" in sortie
    assert "2 constat(s), dépôt privé : avertissement, pas de refus" in sortie


def test_depot_prive_erreurs_toujours_64(rendre, tmp_path, env_isole):
    script = rendre(visibilite="prive") / "scripts/modele/confidentialite.py"
    f = tmp_path / "f.txt"
    f.write_text(IP + "\n", encoding="utf-8")
    exige = lancer_porte(script, ["--exiger-prives", "--fichiers", str(f)], env_isole())
    assert exige.returncode == 64
    env = env_isole()
    env["MOTIFS_INTERDITS"] = "re:(invalide"
    assert lancer_porte(script, ["--fichiers", str(f)], env).returncode == 64
    absent = str(tmp_path / "absent.txt")
    assert lancer_porte(script, ["--fichiers", absent], env_isole()).returncode == 64
