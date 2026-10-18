"""verifier_secrets.py : les secrets chiffrés par sops, contrôlés sans être déchiffrés."""

import os
import subprocess
import sys

import verifier_secrets
from conftest import SCRIPTS, exiger

SCRIPT = SCRIPTS / "verifier_secrets.py"
TEMOIN = "TEMOIN-NE-PAS-AFFICHER"
# Construits par concaténation : le dépôt est public, aucune adresse ne s'y écrit en entier.
DEST_A = "age1" + "a" * 58
DEST_B = "age1" + "b" * 58


def enc(cles, destinataires, valeur=TEMOIN):
    lignes = [f"{c}=ENC[AES256_GCM,data:{valeur},iv:xx,tag:yy,type:str]" for c in cles]
    for i, d in enumerate(destinataires):
        lignes.append(f"sops_age__list_{i}__map_recipient={d}")
        lignes.append(
            f"sops_age__list_{i}__map_enc=-----BEGIN AGE ENCRYPTED FILE-----\\n{valeur}\\n-----END AGE ENCRYPTED FILE-----\\n"
        )
    lignes += [
        "sops_lastmodified=2026-10-18T10:00:00Z",
        f"sops_mac=ENC[AES256_GCM,data:{valeur}]",
        "sops_unencrypted_suffix=_unencrypted",
        "sops_version=3.13.3",
    ]
    return "\n".join(lignes) + "\n"


def monter(tmp_path, *, cles=("HC_SONDE", "TOKEN"), chiffre=None, destinataires=(DEST_A,), sops_yaml=(DEST_A,)):
    d = tmp_path / "depot"
    (d / "deploiement/secrets").mkdir(parents=True)
    if sops_yaml is not None:
        (d / ".sops.yaml").write_text("creation_rules:\n  - age: " + ",".join(sops_yaml) + "\n", encoding="utf-8")
    if cles is not None:
        (d / "deploiement/secrets/prod.cles").write_text("# clés\n\n" + "\n".join(cles) + "\n", encoding="utf-8")
    if chiffre is not False:
        contenu = chiffre if chiffre is not None else enc(cles or [], destinataires)
        (d / "deploiement/secrets/prod.env.enc").write_text(contenu, encoding="utf-8")
    return d


def lancer(racine):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--racine", str(racine)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def sortie(r):
    return r.stdout + r.stderr


def test_conforme(tmp_path):
    r = lancer(monter(tmp_path))
    assert r.returncode == 0, sortie(r)


def test_cle_manquante(tmp_path):
    r = lancer(monter(tmp_path, chiffre=enc(["TOKEN"], [DEST_A])))
    assert r.returncode == 1
    assert "HC_SONDE" in sortie(r)


def test_cle_en_trop(tmp_path):
    r = lancer(monter(tmp_path, chiffre=enc(["HC_SONDE", "TOKEN", "EXTRA"], [DEST_A])))
    assert r.returncode == 1
    assert "EXTRA" in sortie(r)


def test_autre_destinataire(tmp_path):
    r = lancer(monter(tmp_path, destinataires=(DEST_A, DEST_B)))
    assert r.returncode == 1


def test_destinataire_manquant(tmp_path):
    r = lancer(monter(tmp_path, sops_yaml=(DEST_A, DEST_B)))
    assert r.returncode == 1


def test_cles_exigees_par_la_mecanique(tmp_path):
    d = monter(tmp_path, cles=("TOKEN",))
    exiges = {"deploiement/secrets/prod.cles": ["HC_SONDE"]}
    refus = [c for c in verifier_secrets.verifier(d, exiges) if c.niveau == "refus"]
    assert refus
    assert "HC_SONDE" in refus[0].message
    assert verifier_secrets.main(["--racine", str(d)], exiges) == 1
    assert verifier_secrets.main(["--racine", str(d)], {}) == 0


def test_enc_sans_cles(tmp_path):
    r = lancer(monter(tmp_path, cles=None, chiffre=enc(["TOKEN"], [DEST_A])))
    assert r.returncode == 1


def test_cles_sans_enc_avertit(tmp_path):
    r = lancer(monter(tmp_path, chiffre=False))
    assert r.returncode == 0
    assert "avertissement" in sortie(r)


def test_sans_sops_yaml(tmp_path):
    r = lancer(monter(tmp_path, sops_yaml=None))
    assert r.returncode == 1


def test_ligne_illisible(tmp_path):
    contenu = enc(["HC_SONDE", "TOKEN"], [DEST_A]) + f"ligne sans egal {TEMOIN}\n"
    numero = contenu.count("\n")
    r = lancer(monter(tmp_path, chiffre=contenu))
    assert r.returncode == 1
    assert f":{numero}" in sortie(r)
    assert TEMOIN not in sortie(r)


def test_aucun_fichier(tmp_path):
    r = lancer(tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_ne_divulgue_rien(tmp_path):
    cas = [
        monter(tmp_path / "a"),
        monter(tmp_path / "b", chiffre=enc(["TOKEN"], [DEST_A, DEST_B])),
        monter(tmp_path / "c", chiffre=enc(["HC_SONDE", "TOKEN", "EXTRA"], [DEST_A]) + f"{TEMOIN}\n"),
        monter(tmp_path / "d", cles=None, chiffre=enc(["TOKEN"], [DEST_A])),
        monter(tmp_path / "e", sops_yaml=None),
        monter(tmp_path / "f", chiffre=False),
    ]
    for d in cas:
        assert TEMOIN not in sortie(lancer(d))


def test_usage():
    r = subprocess.run([sys.executable, str(SCRIPT), "--bidon"], check=False, capture_output=True, text=True)
    assert r.returncode == 64


def test_cles_doublon_et_forme(tmp_path):
    d = monter(tmp_path / "z", cles=("A", "A"), chiffre=enc(["A"], [DEST_A]))
    assert any(c.niveau == "refus" for c in verifier_secrets.verifier(d, {}))
    d = monter(tmp_path / "y", cles=("minuscule",), chiffre=enc(["minuscule"], [DEST_A]))
    assert any(c.niveau == "refus" for c in verifier_secrets.verifier(d, {}))


def test_vrai_fichier_sops(tmp_path):
    exiger("sops", "age-keygen")
    cle = tmp_path / "cle.txt"
    subprocess.run(["age-keygen", "-o", str(cle)], check=True, capture_output=True)
    publique = next(
        ligne.split(":", 1)[1].strip()
        for ligne in cle.read_text(encoding="utf-8").splitlines()
        if ligne.startswith("# public key:")
    )
    d = tmp_path / "depot"
    (d / "deploiement/secrets").mkdir(parents=True)
    (d / ".sops.yaml").write_text(
        "creation_rules:\n"
        "  - path_regex: ^deploiement[\\\\/]secrets[\\\\/][a-z]+\\.env\\.enc$\n"
        f"    age: {publique}\n",
        encoding="utf-8",
    )
    (d / "deploiement/secrets/prod.cles").write_text("HC_SONDE\nTOKEN\n", encoding="utf-8")
    env = {**os.environ, "SOPS_AGE_KEY_FILE": str(cle)}
    r = subprocess.run(
        [
            "sops", "encrypt", "--filename-override", "deploiement/secrets/prod.env.enc",
            "--input-type", "dotenv", "--output-type", "dotenv",
            "--output", "deploiement/secrets/prod.env.enc",
        ],
        cwd=d,
        env=env,
        input="HC_SONDE=valeur-un\nTOKEN=valeur-deux\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stderr
    cles, destinataires = verifier_secrets.lire_chiffre(d / "deploiement/secrets/prod.env.enc")
    assert cles == {"HC_SONDE", "TOKEN"}
    assert destinataires == {publique}
    assert verifier_secrets.main(["--racine", str(d)], {}) == 0
