"""Les réglages de l'application : modèle appelé et fichiers de données connus.

Ils vivent dans ~/.allergylab/reglages.json, hors du dépôt (règle 4). Le fichier
garde ce que la fenêtre a utilisé la dernière fois : quel modèle, quels fichiers,
lequel était ouvert.

Point important : le modèle choisi vaut pour **ce processus seulement**. Un
`uv run kit agent` lancé dans un terminal doit toujours partir sur Haiku, même si
la fenêtre a basculé sur Sonnet la veille — sinon la note d'électricité arrive
sans prévenir. C'est pourquoi `modele()` rend la valeur en mémoire, jamais celle
du fichier ; c'est la fenêtre qui la rétablit au démarrage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CHEMIN = Path.home() / ".allergylab" / "reglages.json"

# Les deux modèles que le kit déclare dans kit/reglages.toml. Les tarifs et les
# identifiants restent là-bas : ici, on ne choisit qu'un nom.
MODELES = {"developpement": "Haiku 5.5", "officiel": "Sonnet 5.5 (20× plus cher)"}

MODELE_EN_COURS = None  # None = celui du kit, « developpement »


def lire():
    """Le contenu du fichier de réglages ; un fichier absent ou abîmé rend un dictionnaire vide."""
    try:
        contenu = json.loads(CHEMIN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return contenu if isinstance(contenu, dict) else {}


def ecrire(**champs):
    """Enregistre les champs donnés et rend le contenu à jour."""
    contenu = lire()
    contenu.update(champs)
    CHEMIN.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    provisoire = CHEMIN.with_name(f".{CHEMIN.name}.{os.getpid()}")
    with open(provisoire, "w", encoding="utf-8") as fichier:
        json.dump(contenu, fichier, ensure_ascii=False, indent=1)
    os.chmod(provisoire, 0o600)
    provisoire.replace(CHEMIN)
    return contenu


def modele():
    """Le modèle de ce processus : celui du kit, sauf si la fenêtre en a choisi un autre."""
    return MODELE_EN_COURS or "developpement"


def choisir_modele(nom, garder=True):
    """Bascule le modèle du processus ; `garder` l'inscrit pour la prochaine session."""
    global MODELE_EN_COURS
    if nom not in MODELES:
        raise ValueError(f"modèle inconnu : {nom}")
    MODELE_EN_COURS = nom
    if garder:
        ecrire(modele=nom)
    return nom


def libelle(nom=None):
    """Le nom affichable du modèle en cours."""
    return MODELES.get(nom or modele(), "Haiku 5.5")


def fichiers():
    """Les fichiers de données connus, ceux qui existent encore."""
    connus = lire().get("fichiers")
    if not isinstance(connus, list):
        return []
    return [chemin for chemin in connus if isinstance(chemin, str) and Path(chemin).is_file()]


def ajouter_fichiers(chemins):
    """Ajoute des fichiers à la liste connue, sans doublon, et l'enregistre. Rend la liste à jour."""
    liste = fichiers()
    for chemin in chemins:
        if not chemin:
            continue
        propre = str(Path(chemin).expanduser().resolve())
        if propre not in liste:
            liste.append(propre)
    ecrire(fichiers=liste)
    return liste


def retenir_fichier(chemin):
    """Retient le fichier ouvert pour la prochaine session (None = celui du kit)."""
    ecrire(fichier=str(Path(chemin).expanduser().resolve()) if chemin else "")
    return chemin


def fichier_retenu():
    """Le fichier ouvert la dernière fois, s'il existe encore."""
    chemin = lire().get("fichier")
    return chemin if isinstance(chemin, str) and chemin and Path(chemin).is_file() else None
