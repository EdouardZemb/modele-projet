"""Les retouches du relais qui marque le staging (`scripts/modele/marque.py`, cible `serveur`).

Le fichier du modèle porte un nom de gabarit, sans `.jinja` : Copier en rend le nom, jamais le
contenu. Le test le charge donc par un `SourceFileLoader`, sans quoi un nom qui ne finit pas par
`.py` rend `None`. Les valeurs de la spec sont écrites ici en littéraux, jamais par les constantes
du module : un mutant de la constante doit faire échouer le test.
"""

import base64
import importlib.machinery
import importlib.util
import struct
import tracemalloc
import zlib

import pytest
from conftest import RACINE

CHEMIN = RACINE / "template/scripts/modele/{% if cible == 'serveur' %}marque.py{% endif %}"


def _charger():
    chargeur = importlib.machinery.SourceFileLoader("marque", str(CHEMIN))
    spec = importlib.util.spec_from_file_location("marque", CHEMIN, loader=chargeur)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


marque = _charger()

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def bloc(nom, donnees):
    crc = zlib.crc32(nom + donnees) & 0xFFFFFFFF
    return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", crc)


def filtrer(type_filtre, ligne, precedente, bpp):
    """La ligne `ligne` filtrée par le filtre `type_filtre` (0 à 4), d'après la spec PNG."""
    sortie = bytearray()
    for i, x in enumerate(ligne):
        a = ligne[i - bpp] if i >= bpp else 0
        b = precedente[i]
        c = precedente[i - bpp] if i >= bpp else 0
        if type_filtre == 0:
            p = 0
        elif type_filtre == 1:
            p = a
        elif type_filtre == 2:
            p = b
        elif type_filtre == 3:
            p = (a + b) >> 1
        else:
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            p = a if pa <= pb and pa <= pc else b if pb <= pc else c
        sortie.append((x - p) & 255)
    return bytes([type_filtre]) + bytes(sortie)


def png(
    largeur,
    hauteur,
    type_couleur,
    pixels,
    profondeur=8,
    entrelace=0,
    filtres=None,
    palette=None,
    trns=None,
):
    """Un PNG : `pixels` porte les échantillons de toutes les lignes, filtrés ligne à ligne."""
    long_ligne = len(pixels) // hauteur
    bpp = max(1, {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[type_couleur] * profondeur // 8)
    brut = bytearray()
    precedente = bytes(long_ligne)
    for y in range(hauteur):
        ligne = bytes(pixels[y * long_ligne : (y + 1) * long_ligne])
        brut += filtrer(filtres[y % len(filtres)] if filtres else 0, ligne, precedente, bpp)
        precedente = ligne
    entete = struct.pack(">IIBBBBB", largeur, hauteur, profondeur, type_couleur, 0, 0, entrelace)
    sortie = SIGNATURE + bloc(b"IHDR", entete)
    if palette is not None:
        sortie += bloc(b"PLTE", palette)
    if trns is not None:
        sortie += bloc(b"tRNS", trns)
    return sortie + bloc(b"IDAT", zlib.compress(bytes(brut), 6)) + bloc(b"IEND", b"")


def lire(donnees):
    """(largeur, hauteur, type, pixels, blocs) d'un PNG de sortie : filtre 0 partout, profondeur 8."""
    assert donnees.startswith(SIGNATURE)
    blocs = {}
    pos = 8
    while pos < len(donnees):
        (taille,) = struct.unpack_from(">I", donnees, pos)
        blocs.setdefault(donnees[pos + 4 : pos + 8], []).append(donnees[pos + 8 : pos + 8 + taille])
        pos += 12 + taille
    largeur, hauteur, profondeur, type_couleur, _, _, entrelace = struct.unpack(
        ">IIBBBBB", blocs[b"IHDR"][0]
    )
    assert (profondeur, entrelace) == (8, 0)
    brut = zlib.decompress(b"".join(blocs[b"IDAT"]))
    canaux = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[type_couleur]
    long_ligne = largeur * canaux
    pixels = bytearray()
    for y in range(hauteur):
        assert brut[y * (long_ligne + 1)] == 0
        pixels += brut[y * (long_ligne + 1) + 1 : (y + 1) * (long_ligne + 1)]
    return largeur, hauteur, type_couleur, bytes(pixels), blocs


def pixels_rgba(n):
    sortie = bytearray()
    for i in range(n):
        sortie += bytes([(i * 37) % 256, (i * 91) % 256, (i * 53) % 256, (i * 17) % 256])
    return bytes(sortie)


# --- les valeurs --------------------------------------------------------------------------------


def test_valeurs_de_la_spec():
    assert marque.RAMPE == (
        (0, (0x5C, 0x1A, 0x00)),
        (128, (0xE8, 0x59, 0x0C)),
        (255, (0xFF, 0xE3, 0xC2)),
    )
    assert marque.ORANGE == (0xE8, 0x59, 0x0C)
    assert marque.PLAFOND_PAGE == 5 * 1024 * 1024
    assert marque.COTE_MAX == 1024
    assert marque.ICONE_MAX == 4 * 1024 * 1024
    assert marque.LECTURE_ICONE_MAX == 5 * 1024 * 1024
    assert marque.ICONES_GARDEES == 32
    assert marque.CACHE_OCTETS == 16 * 1024 * 1024
    assert marque.LECTURES_ICONE == 2
    assert marque.DELAI_AMONT == 120
    assert marque.DELAI_INACTIF == 75
    assert marque.HOTE_ECOUTE == "0.0.0.0"
    assert marque.CHEMIN_RESERVE == "/.marque/"
    assert marque.PREFIXE_TITRE == b"test &middot; "
    assert marque.PREFIXE_NOM == "test · "
    assert marque.PREFIXE_NOM_COURT == "test "
    assert marque.LIEN_FEUILLE == b'<link rel="stylesheet" href="/.marque/marque.css">'


def test_rampe_aux_trois_arrets():
    assert marque.couleur_de(0) == (0x5C, 0x1A, 0x00)
    assert marque.couleur_de(128) == (0xE8, 0x59, 0x0C)
    assert marque.couleur_de(255) == (0xFF, 0xE3, 0xC2)
    assert marque.couleur_de(64) == (0xA2, 0x3A, 0x06)
    assert marque.couleur_de(192) == (0xF4, 0x9F, 0x68)
    suite = [marque.couleur_de(i) for i in range(256)]
    for canal in range(3):
        valeurs = [c[canal] for c in suite]
        assert valeurs == sorted(valeurs)
    assert marque.luminance(255, 255, 255) == 255
    assert marque.luminance(0, 0, 0) == 0


# --- le PNG -------------------------------------------------------------------------------------


def test_png_rgba_recolore():
    brut = pixels_rgba(25)
    sortie = marque.recolorer_png(png(5, 5, 6, brut, filtres=[0, 1, 2, 3, 4]))
    largeur, hauteur, type_couleur, pixels, _ = lire(sortie)
    assert (largeur, hauteur, type_couleur) == (5, 5, 6)
    for i in range(25):
        r, g, b, a = brut[4 * i : 4 * i + 4]
        attendu = marque.couleur_de(marque.luminance(r, g, b)) + (a,)
        assert tuple(pixels[4 * i : 4 * i + 4]) == attendu
    blanc = marque.recolorer_png(png(1, 1, 6, bytes([255, 255, 255, 77])))
    assert lire(blanc)[3] == bytes([0xFF, 0xE3, 0xC2, 77])


def test_png_types_0_2_4_recolores():
    gris = marque.recolorer_png(png(2, 1, 0, bytes([0, 255])))
    assert lire(gris)[2:4] == (2, bytes([0x5C, 0x1A, 0x00, 0xFF, 0xE3, 0xC2]))
    gris_alpha = marque.recolorer_png(png(2, 1, 4, bytes([0, 9, 255, 200])))
    assert lire(gris_alpha)[2:4] == (6, bytes([0x5C, 0x1A, 0x00, 9, 0xFF, 0xE3, 0xC2, 200]))
    rvb = marque.recolorer_png(png(1, 2, 2, bytes([255, 255, 255, 0, 0, 0]), filtres=[2]))
    assert lire(rvb)[2:4] == (2, bytes([0xFF, 0xE3, 0xC2, 0x5C, 0x1A, 0x00]))


def test_png_trns_cle_gardee():
    gris = marque.recolorer_png(png(3, 1, 0, bytes([10, 20, 10]), trns=b"\x00\x0a"))
    type_couleur, pixels = lire(gris)[2:4]
    assert type_couleur == 6
    assert [pixels[4 * i + 3] for i in range(3)] == [0, 255, 0]
    rvb = marque.recolorer_png(
        png(2, 1, 2, bytes([1, 2, 3, 1, 2, 4]), trns=b"\x00\x01\x00\x02\x00\x03")
    )
    type_couleur, pixels = lire(rvb)[2:4]
    assert type_couleur == 6
    assert [pixels[4 * i + 3] for i in range(2)] == [0, 255]


def test_png_palette_recoloree():
    palette = bytes([255, 255, 255, 0, 0, 0, 10, 20, 30])
    indices = bytes([0, 1, 2, 2, 1, 0])
    sortie = marque.recolorer_png(
        png(3, 2, 3, indices, filtres=[1, 2], palette=palette, trns=b"\xff\x80")
    )
    _, _, type_couleur, pixels, blocs = lire(sortie)
    assert type_couleur == 3
    assert pixels == indices
    assert blocs[b"tRNS"] == [b"\xff\x80"]
    plte = blocs[b"PLTE"][0]
    assert plte[:6] == bytes([0xFF, 0xE3, 0xC2, 0x5C, 0x1A, 0x00])
    assert len(plte) == 9


def test_png_generique():
    pixel = bytes([1, 2, 3, 4])
    assert marque.recolorer_png(png(1, 1, 6, pixel * 1, profondeur=16)) is None
    assert marque.recolorer_png(png(2, 1, 3, bytes([0x1B]), profondeur=4, palette=b"\0" * 12)) is None
    assert marque.recolorer_png(png(1, 1, 6, pixel, entrelace=1)) is None
    assert marque.recolorer_png(png(1025, 1, 6, pixel * 1025)) is None
    assert marque.recolorer_png(png(1, 1025, 6, pixel * 1025)) is None
    assert marque.recolorer_png(b"\x00\x00\x01\x00" + b"\x00" * 100) is None
    assert marque.recolorer_png(b"quelconque") is None
    assert marque.recolorer_png(b"") is None
    entier = png(4, 4, 6, pixels_rgba(16))
    assert marque.recolorer_png(entier) is not None
    for coupe in (len(entier) - 1, len(entier) - 12, 40, 20, 9):
        assert marque.recolorer_png(entier[:coupe]) is None


def test_png_bombe_generique():
    entete = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
    bombe = zlib.compress(b"\x00" * (50 * 1024 * 1024), 9)
    donnees = (
        SIGNATURE + bloc(b"IHDR", entete) + bloc(b"IDAT", bombe) + bloc(b"IEND", b"")
    )
    assert marque.recolorer_png(donnees) is None
    court = SIGNATURE + bloc(b"IHDR", entete) + bloc(b"IDAT", zlib.compress(b"\x00" * 5)) + bloc(
        b"IEND", b""
    )
    assert marque.recolorer_png(court) is None


def test_png_1024_admis():
    pixels = bytes(range(256)) * (1024 * 1024 * 4 // 256)
    donnees = png(1024, 1024, 6, pixels)
    tracemalloc.start()
    try:
        sortie = marque.recolorer_png(donnees)
        _, pic = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert sortie is not None
    assert lire(sortie)[:3] == (1024, 1024, 6)
    assert pic < 48 * 1024 * 1024


# --- le SVG -------------------------------------------------------------------------------------


def test_svg_enveloppe():
    original = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 48"><path d="M0 0"/></svg>'
    sortie = marque.envelopper_svg(original)
    assert sortie.startswith(b"<svg")
    assert b"feColorMatrix" in sortie
    assert base64.b64encode(original) in sortie
    assert b'viewBox="0 0 24 48"' in sortie
    assert b'x="0" y="0" width="24" height="48"' in sortie
    assert b'filter="url(#m)"' in sortie
    sans = marque.envelopper_svg(b'<svg width="32px" height="16"></svg>')
    assert b'viewBox="0 0 32 16"' in sans
    rien = marque.envelopper_svg(b"<svg></svg>")
    assert b'viewBox="0 0 100 100"' in rien
    assert marque.envelopper_svg(b"<svg/>" + b" " * (4194304 - 6)) is not None
    assert marque.envelopper_svg(b"<svg/>" + b" " * (4194304 - 5)) is None


def test_icone_generique():
    largeur, hauteur, type_couleur, pixels, _ = lire(marque.icone_generique())
    assert (largeur, hauteur, type_couleur) == (512, 512, 2)
    assert pixels == bytes([0xE8, 0x59, 0x0C]) * (512 * 512)


# --- la feuille ---------------------------------------------------------------------------------


def test_feuille_trois_regles():
    feuille = marque.FEUILLE.decode("utf-8")
    ouvertures = ["html::before {", "dialog[open]::before {", ":popover-open::before {"]
    assert feuille.count("::before {") == 3
    for i, ouverture in enumerate(ouvertures):
        assert feuille.count(ouverture) == 1
        debut = feuille.index(ouverture)
        fin = feuille.index("}", debut)
        regle = feuille[debut:fin]
        for morceau in (
            'content: "TEST"',
            "height: 20px",
            "env(safe-area-inset-top",
            "#e8590c",
            "pointer-events: none",
            "z-index: 2147483647",
        ):
            assert morceau in regle, (ouverture, morceau)
    assert "," not in feuille.split("{")[0].split("*/")[-1]


# --- la page ------------------------------------------------------------------------------------


def test_page_lien_insere():
    lien = b'<link rel="stylesheet" href="/.marque/marque.css">'
    favicon = b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">'
    avec = marque.retoucher_page(b"<html><head><meta></head><body>x</body></html>", "/", None)
    assert avec == b"<html><head><meta>" + lien + favicon + b"</head><body>x</body></html>"
    sans_fin = marque.retoucher_page(b"<html><meta><body>x", "/", None)
    assert sans_fin == b"<html><meta>" + lien + favicon + b"<body>x"
    rien = marque.retoucher_page(b"<p>x</p>", "/", None)
    assert rien == b"<p>x</p>" + lien + favicon
    majuscules = marque.retoucher_page(b"<HEAD></HEAD><BODY>", "/", None)
    assert majuscules == b"<HEAD>" + lien + favicon + b"</HEAD><BODY>"


def test_page_ignore_les_commentaires():
    page = b"<head><!-- </head> <title>x</title> --><title>Vrai</title></head>"
    sortie = marque.retoucher_page(page, "/", None)
    lien = b'<link rel="stylesheet" href="/.marque/marque.css">'
    favicon = b'<link rel="icon" href="/.marque/icone?de=/favicon.ico">'
    assert sortie == (
        b"<head><!-- </head> <title>x</title> --><title>test &middot; Vrai</title>"
        + lien
        + favicon
        + b"</head>"
    )
    ouvert = marque.retoucher_page(b"<head><!-- </head><title>x</title>", "/", None)
    assert ouvert.count(b"test &middot; ") == 0
    assert ouvert.endswith(lien + favicon)


def test_titre_prefixe():
    page = marque.retoucher_page(b"<head><title>Veille emploi</title></head>", "/", None)
    assert b"<title>test &middot; Veille emploi</title>" in page
    majuscules = marque.retoucher_page(b'<head><TITLE lang="fr">Veille</TITLE></head>', "/", None)
    assert b'<TITLE lang="fr">test &middot; Veille</TITLE>' in majuscules
    sans = marque.retoucher_page(b"<head></head>", "/", None)
    assert b"<title" not in sans and b"&middot;" not in sans
    deux = marque.retoucher_page(b"<head><title>A</title><title>B</title></head>", "/", None)
    assert deux.count(b"&middot;") == 1


def test_liens_icone_reecrits():
    page = (
        b"<html><head>"
        b'<link rel="icon" href="/icone.svg">'
        b"<link href='/a.png' rel='shortcut icon'>"
        b"<link rel=icon href=/b.png>"
        b'<link rel="apple-touch-icon-precomposed" href="c.png">'
        b'<link rel="mask-icon" href="/m.svg">'
        b'<link rel="icon" href="https://autre.exemple/i.png">'
        b'<link rel="icon" href="//autre.exemple/i.png">'
        b'<link rel="icon" href="https://hote.exemple/i.png">'
        b"</head><body>"
        b'<link rel="icon" href="/z.png">'
    )
    sortie = marque.retoucher_page(page, "/x/y", "hote.exemple")
    assert b'<link rel="icon" href="/.marque/icone?de=/icone.svg">' in sortie
    assert b"<link href='/.marque/icone?de=/a.png' rel='shortcut icon'>" in sortie
    assert b'<link rel=icon href="/.marque/icone?de=/b.png">' in sortie
    assert b'<link rel="apple-touch-icon-precomposed" href="/.marque/icone?de=/x/c.png">' in sortie
    assert b'<link rel="mask-icon" href="/m.svg">' in sortie
    assert b'<link rel="icon" href="/z.png">' in sortie
    assert b'<link rel="icon" href="https://hote.exemple/i.png">' not in sortie
    assert b'<link rel="icon" href="/.marque/icone?de=/i.png">' in sortie
    assert sortie.count(b'href="/.marque/icone">') == 2
    assert b"autre.exemple" not in sortie
    # des liens d'icône sont là : le favicon par défaut n'est pas ajouté
    assert b"favicon.ico" not in sortie


def test_lien_icone():
    assert marque.lien_icone("/i.png?v=1&a=2", "/", "h") == "/.marque/icone?de=/i.png%3Fv%3D1%26a%3D2"
    assert marque.lien_icone("i.png", "/m/app.webmanifest", None) == "/.marque/icone?de=/m/i.png"
    assert marque.lien_icone("https://h/i.png", "/", None) == "/.marque/icone"
    assert marque.lien_icone("data:image/png;base64,AAAA", "/", "h") == "/.marque/icone"
    assert marque.lien_icone("/a b.png", "/", "h") == "/.marque/icone"


def test_page_sans_lien_recoit_favicon():
    sortie = marque.retoucher_page(b"<head><link rel=stylesheet href=/a.css></head>", "/", None)
    assert (
        b'<link rel="stylesheet" href="/.marque/marque.css">'
        b'<link rel="icon" href="/.marque/icone?de=/favicon.ico"></head>'
    ) in sortie


# --- le manifeste -------------------------------------------------------------------------------


def test_manifeste_noms_prefixes():
    corps = (
        b'{"name": "Veille", "short_name": "V", '
        b'"icons": [{"src": "i.png", "sizes": "1x1"}, {"src": 5}, "x"]}'
    )
    sortie = marque.retoucher_manifeste(corps, "/m/app.webmanifest", "h")
    assert sortie is not None
    assert "test · Veille".encode() in sortie
    assert b'"short_name": "test V"' in sortie
    assert b'"src": "/.marque/icone?de=/m/i.png"' in sortie
    assert b'"src": 5' in sortie
    import json

    assert json.loads(sortie)["name"] == "test · Veille"
    sans = marque.retoucher_manifeste(b'{"display": "standalone"}', "/manifest.json", None)
    assert b'"name": "test"' in sans
    court = marque.retoucher_manifeste(b'{"short_name": "V"}', "/manifest.json", None)
    assert b'"short_name": "test V"' in court and b'"name"' not in court


def test_manifeste_avec_bom():
    corps = b"\xef\xbb\xbf" + b'{"name": "App"}'
    assert "test · App".encode() in marque.retoucher_manifeste(corps, "/m.webmanifest", None)


def test_manifeste_illisible():
    assert marque.retoucher_manifeste(b"{", "/m.webmanifest", None) is None
    assert marque.retoucher_manifeste(b"[]", "/m.webmanifest", None) is None
    assert marque.retoucher_manifeste(b'{"name": "\xff\xfe"}', "/m.webmanifest", None) is None
    assert marque.retoucher_manifeste(b'{"name": "\\ud800"}', "/m.webmanifest", None) is None


def test_est_manifeste():
    assert marque.est_manifeste("/manifest.webmanifest", "application/json")
    assert marque.est_manifeste("/x/app.webmanifest?v=1", None)
    assert marque.est_manifeste("/manifest.json", None)
    assert marque.est_manifeste("/m", "application/manifest+json; charset=utf-8")
    assert not marque.est_manifeste("/api/manifest", "application/json")
    assert marque.est_page("text/html; charset=utf-8")
    assert marque.est_page("TEXT/HTML")
    assert not marque.est_page("application/json")
    assert not marque.est_page(None)


# --- le chemin ----------------------------------------------------------------------------------


def test_chemin_admis():
    assert marque.chemin_admis("/a")
    assert marque.chemin_admis("/a?b=c")
    assert marque.chemin_admis("/" + "a" * 1023)
    assert not marque.chemin_admis("/" + "a" * 1024)
    for refuse in ("", "a", "//x", "http://x/", "/a\\b", "/a b", "/a\x01", "/é"):
        assert not marque.chemin_admis(refuse), refuse


@pytest.mark.parametrize("nom", ["{{", "{%"])
def test_aucun_reste_de_jinja(nom):
    assert nom not in CHEMIN.read_text(encoding="utf-8")
