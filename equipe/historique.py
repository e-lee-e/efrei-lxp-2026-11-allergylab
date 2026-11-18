"""L'historique des questions posées, gardé hors du dépôt.

Le dépôt public ne doit contenir aucune réponse sur le fichier réel (règle 4) :
l'historique vit donc dans ~/.allergylab/questions.json, à côté de la clé, et
jamais dans equipe/.

Une seule règle de fond : **une question, une entrée**. Reposer la même question
ne crée pas de doublon, elle remplace la réponse et remonte l'entrée en tête —
c'est ce que la barre latérale montre, et un doublon y serait du bruit.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from equipe.cache import normaliser

FICHIER = Path.home() / ".allergylab" / "questions.json"
GARDEES = 200  # au-delà, les plus anciennes sortent : un fichier ne grossit pas sans fin


def charger(chemin=FICHIER):
    """Les entrées enregistrées, la plus récente d'abord. Un fichier absent ou abîmé rend une liste vide."""
    try:
        with open(chemin, encoding="utf-8") as fichier:
            entrees = json.load(fichier)
    except (OSError, ValueError):
        return []
    if not isinstance(entrees, list):
        return []
    return [entree for entree in entrees if isinstance(entree, dict) and entree.get("question")]


def enregistrer(entree, chemin=FICHIER):
    """Ajoute une entrée en tête, après avoir retiré la même question. Rend la liste à jour."""
    question = normaliser(str(entree.get("question") or ""))
    if not question:
        return charger(chemin)

    propre = dict(entree)
    propre.setdefault("quand", datetime.now().isoformat(timespec="seconds"))
    # La déduplication porte sur le couple (fichier, question) : la même question
    # posée sur deux jeux est deux entrées. Sur la question seule, la seconde
    # effaçait la première de la barre latérale de l'autre fichier.
    fichier = entree.get("fichier")
    reste = [
        autre
        for autre in charger(chemin)
        if not (normaliser(str(autre.get("question") or "")) == question and autre.get("fichier") == fichier)
    ]
    entrees = [propre] + reste
    ecrire(entrees[:GARDEES], chemin)
    return entrees[:GARDEES]


def vider(chemin=FICHIER):
    """Efface l'historique. Les réponses en cache, elles, restent : elles ne coûtent plus rien."""
    try:
        chemin.unlink()
    except OSError:
        pass
    return []


def du_fichier(nom, chemin=FICHIER):
    """Les entrées obtenues sur un fichier de données donné.

    Une réponse calculée sur un fichier n'a aucun sens sur un autre : la barre
    latérale ne montre que la série du fichier ouvert.
    """
    return [entree for entree in charger(chemin) if entree.get("fichier") == nom]


def ecrire(entrees, chemin=FICHIER):
    """Écrit la liste entière, en une seule fois et sans laisser de fichier à moitié écrit."""
    chemin.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    provisoire = chemin.with_name(f".{chemin.name}.{os.getpid()}")
    with open(provisoire, "w", encoding="utf-8") as fichier:
        json.dump(entrees, fichier, ensure_ascii=False, indent=1)
    os.chmod(provisoire, 0o600)
    provisoire.replace(chemin)
