# La fausse app du modèle (spec §10.3) : le contrat de la cible `serveur` (§6.1) en quelques lignes
# de Python, sans dépendance. Le job `fausse-app` de la CI de modele-projet rend un projet
# `fausse-app` en cible `serveur`, nature code, y copie ce dossier, et lui fait passer l'action
# modele-image-construire du rendu : construction, santé, révision, sauvegarde, vérification, et
# l'exemple de l'instance ; puis tests/modele/epreuve-donnees.sh la déploie avec ses données.

# python:3.13-slim (Python 3.13.16, Debian trixie), résolue le 2026-10-18 par
# `docker buildx imagetools inspect` ; empreinte de l'index multi-architecture.
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

# /donnees : les données de l'app, semées à la construction pour qu'un instantané ne soit jamais
# vide. MARQUE est ce que `verifier` contrôle. Elles appartiennent à l'uid 1000, comme sur le
# serveur.
RUN mkdir -p /donnees/notes \
    && printf 'fausse-app\n' >/donnees/MARQUE \
    && printf 'une note\n' >/donnees/notes/premiere.txt \
    && printf 'un fichier caché\n' >/donnees/.cachee \
    && chown -R 1000:1000 /donnees

COPY app.py /app/app.py
# L'exemple de l'instance (M-0006, § 5), du code : l'app le sert quand /config ou /contenu manque,
# jamais en prod.
COPY exemple /app/exemple
COPY exemple-contenu /app/exemple-contenu
# Les commandes de deploiement/projet.env (SAUVEGARDER=sauvegarder, VERIFIER=verifier,
# VERIFIER_CONFIG=verifier-config, VERIFIER_CONTENU=verifier-contenu).
COPY --chmod=0755 sauvegarder verifier verifier-config verifier-contenu /usr/local/bin/

# La révision vient de la CI (SHA du commit). Elle est déclarée en dernier pour qu'un changement de
# révision ne rejoue que les couches ci-dessous.
ARG REVISION=local
ENV FAUSSE_APP_REVISION=$REVISION \
    PORT=3000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
LABEL org.opencontainers.image.revision=$REVISION

USER 1000:1000
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --start-interval=1s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/api/sante', timeout=4)"]

CMD ["python3", "/app/app.py"]
