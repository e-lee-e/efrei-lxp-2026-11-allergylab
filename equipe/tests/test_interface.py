"""Tests de l'interface : la page ne calcule rien, elle met en forme.

Aucun réseau, aucun serveur : on teste la seule fonction qui décide de ce que
l'écran affiche, avec un agent remplacé par une fonction.
"""

import pytest

from equipe import interface


class FausseTrace:
    """Remplace la trace du kit : les tests n'écrivent rien dans traces/."""

    def __init__(self):
        self.notes = {}

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def noter(self, **notes):
        self.notes.update(notes)


@pytest.fixture(autouse=True)
def sans_trace(monkeypatch):
    monkeypatch.setattr(interface.traces, "appel", lambda *a, **k: FausseTrace())
    # L'historique vit hors du dépôt : les tests n'y écrivent pas.
    monkeypatch.setattr(interface.historique, "enregistrer", lambda entree, *a, **k: [entree])


def test_une_reponse_normale_arrive_telle_quelle(monkeypatch):
    monkeypatch.setattr(
        interface.agent,
        "repondre",
        lambda question: {"statut": "reponse", "valeur": 4271, "justification": "4 271 lignes dans le fichier."},
    )
    sortie = interface.traiter("Combien de patients ?")

    assert sortie["statut"] == "reponse"
    assert sortie["valeur"] == 4271
    assert sortie["justification"] == "4 271 lignes dans le fichier."
    assert sortie["cout"] == 0
    assert sortie["duree"] >= 0
    assert sortie["couche"] == "—"  # aucune couche enregistrée par l'agent remplacé
    assert sortie["etapes"] == 0
    assert sortie["fichier"]  # le nom du fichier lu, pour rattacher la question à sa série


def test_une_abstention_n_est_pas_une_panne(monkeypatch):
    monkeypatch.setattr(
        interface.agent,
        "repondre",
        lambda question: {
            "statut": "abstention",
            "valeur": None,
            "justification": "Le fichier ne donne pas les seuils de positivité.",
        },
    )
    sortie = interface.traiter("Quel seuil de positivité ?")

    assert sortie["statut"] == "abstention"
    assert sortie["valeur"] is None
    assert "seuil" in sortie["justification"]


def test_une_reponse_hors_contrat_devient_illisible(monkeypatch):
    monkeypatch.setattr(interface.agent, "repondre", lambda question: "un objet brut")
    sortie = interface.traiter("Combien de patients ?")

    assert sortie["statut"] == "illisible"
    assert sortie["valeur"] is None
    assert "format" in sortie["justification"]


def test_une_panne_du_moteur_ne_casse_pas_la_page(monkeypatch):
    def boum(question):
        raise RuntimeError("réseau indisponible")

    monkeypatch.setattr(interface.agent, "repondre", boum)
    sortie = interface.traiter("Combien de patients ?")

    assert sortie["statut"] == "erreur"
    assert "RuntimeError" in sortie["justification"]


def test_chaque_couche_a_un_libelle_en_francais():
    attendues = {"cache", "hors-sujet", "routeur", "traducteur", "smolagents", "delai"}
    assert attendues <= set(interface.COUCHES)
    assert all(libelle and "_" not in libelle for libelle in interface.COUCHES.values())
