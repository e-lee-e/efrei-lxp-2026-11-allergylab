"""Le cache ne doit ni confondre deux questions, ni garder une erreur, ni survivre à un outil corrigé.

Une réponse fausse gardée est resservie à 0 $ et passe pour établie : ces tests
portent sur ce qui l'empêche. Aucun réseau, aucun modèle, aucun jeton.
"""

import json

import pytest

from equipe import agent, cache
from garde_fous import sans_fichier_reel, sans_reseau, sans_vrai_cache, sans_vraie_cle  # noqa: F401  (actifs d'office)
from kit import modele

QUESTION = "Quel est l'âge moyen des patients ?"
REPONSE = {"statut": "reponse", "valeur": 41.2, "justification": "Moyenne sur tous les patients."}
ABSTENTION = {"statut": "abstention", "valeur": None, "justification": "La colonne n'existe pas."}


@pytest.fixture(autouse=True)
def fichier_du_kit():
    cache.choisir_fichier(None)
    yield
    cache.choisir_fichier(None)


@pytest.mark.parametrize("a, b", [
    ("Combien de patients ont Age<18 ?", "Combien de patients ont Age>18 ?"),
    ("Dosage >= 0,3 pour Bet_v_1", "Dosage <= 0,3 pour Bet_v_1"),
    ("Écart de +5 ans", "Écart de -5 ans"),
])
def test_deux_questions_de_sens_contraire_ne_partagent_pas_de_cle(a, b):
    """normaliser() efface < > = + - : « Age<18 » et « Age>18 » se confondaient."""
    assert cache.cle(a) != cache.cle(b)


@pytest.mark.parametrize("a, b", [
    ("Quel est l'âge moyen ?", "quel est l age moyen"),
    ("Dosage > 0,3", "dosage > 0.3"),
])
def test_une_simple_reecriture_garde_la_meme_cle(a, b):
    assert cache.cle(a) == cache.cle(b)


def test_la_cle_suit_le_code_la_variante_et_le_modele(monkeypatch):
    base = cache.cle(QUESTION, "ouvert|5|2000")
    assert cache.cle(QUESTION, "ferme|5|2000") != base  # la variante
    assert cache.cle(QUESTION, "ouvert|8|2000") != base  # le plafond d'étapes
    monkeypatch.setattr(cache, "_code", "autre-version-des-outils")
    assert cache.cle(QUESTION, "ouvert|5|2000") != base  # un outil corrigé
    monkeypatch.undo()
    monkeypatch.setattr(modele, "en_cours", "officiel")
    assert cache.cle(QUESTION, "ouvert|5|2000") != base  # le modèle


def test_le_code_des_outils_entre_dans_l_empreinte():
    """Corriger equipe/outils/*.py change l'empreinte, donc invalide les réponses d'avant."""
    assert len(cache.code()) == 64 and cache.code() == cache.code()


def test_une_abstention_n_est_pas_gardee():
    assert cache.ecrire(QUESTION, ABSTENTION) is None
    assert cache.lire(QUESTION) is None


def test_une_reponse_est_gardee_puis_relue():
    cache.ecrire(QUESTION, REPONSE)
    assert cache.lire(QUESTION) == REPONSE


def test_un_fichier_de_cache_abime_ou_edite_n_est_pas_cru():
    chemin = cache.ecrire(QUESTION, REPONSE)
    chemin.write_text(json.dumps({"reponse": {"statut": "reponse", "valeur": 41.2}}), encoding="utf-8")  # sans justification
    assert cache.lire(QUESTION) is None
    chemin.write_text("pas du json", encoding="utf-8")
    assert cache.lire(QUESTION) is None


def test_sans_cache_ni_lecture_ni_ecriture(monkeypatch):
    monkeypatch.setenv("ALLERGYLAB_SANS_CACHE", "1")
    assert cache.ecrire(QUESTION, REPONSE) is None and cache.lire(QUESTION) is None


def test_le_cache_ne_passe_pas_avant_le_routeur(monkeypatch):
    """Une vieille réponse du modèle, même gardée, ne l'emporte pas sur un calcul sans modèle."""
    faux = {"statut": "reponse", "valeur": 999999, "justification": "Réponse ancienne et fausse."}
    monkeypatch.setattr(agent.cache, "lire", lambda question, contexte="": faux)
    monkeypatch.setattr(agent.routeur, "router", lambda question: REPONSE)
    modele.journal_neuf()
    assert agent.repondre(QUESTION) == REPONSE and modele.journal["moteur"] == "routeur"


def test_le_cache_sert_quand_aucune_couche_locale_ne_repond(monkeypatch):
    monkeypatch.setattr(agent.cache, "lire", lambda question, contexte="": REPONSE)
    monkeypatch.setattr(agent.routeur, "router", lambda question: None)
    monkeypatch.setattr(agent.hors_sujet, "examiner", lambda question: None)
    modele.journal_neuf()
    assert agent.repondre(QUESTION) == REPONSE and modele.journal["moteur"] == "cache"
