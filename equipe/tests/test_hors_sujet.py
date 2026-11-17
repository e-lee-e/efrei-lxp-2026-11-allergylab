"""Le portier hors sujet, testé sans réseau ni modèle.

Deux défauts symétriques sont à éviter : laisser passer une question de culture
générale (elle coûte 0,002 $ pour rien) et bloquer une question d'analyse (elle
perd une réponse juste). C'est le second qui est grave, donc chaque test vérifie
aussi qu'une question du domaine passe.
"""

import pytest

from equipe.hors_sujet import examiner


@pytest.mark.parametrize(
    "question",
    (
        "Quand est né LeBron James ?",
        "Qui est le meilleur joueur de football ?",
        "Quel temps fait-il à Paris ?",
        "Combien coûte le bitcoin aujourd'hui ?",
        "Bonjour, que peux-tu faire ?",
        "Donne-moi une recette de cuisine sans gluten.",
    ),
)
def test_une_question_etrangere_au_fichier_s_arrete(question):
    refus = examiner(question)
    assert refus is not None
    assert refus["statut"] == "abstention"
    assert refus["valeur"] is None


@pytest.mark.parametrize(
    "question",
    (
        "Combien de patients compte le tableau ?",
        "Quelle est la répartition des trois puces de test ?",
        "Combien de patients sont allergiques aux acariens ?",
        "Les femmes sont-elles plus souvent sensibilisées que les hommes ?",
        "Quel est le cofacteur le plus fréquent ?",
        "Combien de lignes ?",
    ),
)
def test_une_question_du_domaine_passe(question):
    assert examiner(question) is None


def test_le_justificatif_tient_en_trois_phrases():
    assert examiner("Quand est né LeBron James ?")["justification"].count(".") <= 3
