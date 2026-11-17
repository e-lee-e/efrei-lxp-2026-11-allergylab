"""Le routeur, sur une table inventée. Chaque route a son test « doit passer » et
son test « doit escalader » : c'est la seule façon d'éviter une réponse fausse
dite avec aplomb.
"""

import pandas as pd
import pytest

from equipe.routeur import router
from kit.reponse import phrases


@pytest.fixture
def tableau():
    return pd.DataFrame(
        {
            "Gender": [1.0, 0.0, 1.0, 0.0],
            "Age": [10.0, 12.0, 14.0, None],
            "Sensitization": [1, 1, 0, 1],
            "Bet_v_1": [0.5, 0.1, 0.3, None],
        }
    )


def test_compte_les_lignes(tableau):
    reponse = router("Combien de lignes compte le tableau ?", tableau)
    assert reponse == {
        "statut": "reponse",
        "valeur": 4,
        "justification": "Le tableau compte 4 lignes au total, sans filtrage.",
    }


def test_compte_les_patients_sans_verbe(tableau):
    assert router("combien de patients", tableau)["valeur"] == 4


def test_escalade_une_question_filtree(tableau):
    assert router("Combien de patients ont plus de 60 ans ?", tableau) is None


def test_age_median(tableau):
    reponse = router("Quel est l'âge médian des patients ?", tableau)
    assert reponse["valeur"] == 12.0
    assert "3 patients" in reponse["justification"]


def test_escalade_l_age_median_d_un_sous_groupe(tableau):
    assert router("Quel est l'âge médian des femmes ?", tableau) is None


def test_positifs_avec_seuil(tableau):
    reponse = router("Combien de patients sont positifs à Bet_v_1 avec un seuil de 0,3 ?", tableau)
    assert reponse["valeur"] == 2
    assert "3 mesurés" in reponse["justification"]


def test_positifs_sans_seuil_escalade(tableau):
    # Sans seuil écrit dans la question, la réponse serait un choix que la question ne fait pas.
    assert router("Combien de patients sont positifs à Bet_v_1 ?", tableau) is None


def test_une_autre_question_sur_la_meme_molecule_escalade(tableau):
    assert router("Quelle est la moyenne de Bet_v_1 ?", tableau) is None


def test_positifs_par_sexe_escalade(tableau):
    assert router("Combien de femmes sont positives à Bet_v_1 avec un seuil de 0,3 ?", tableau) is None


def test_les_justifications_du_routeur_tiennent_en_trois_phrases(tableau):
    questions = (
        "Combien de lignes compte le tableau ?",
        "Quel est l'âge médian des patients ?",
        "Combien de patients sont positifs à Bet_v_1 avec un seuil de 0,3 ?",
    )
    for question in questions:
        justification = router(question, tableau)["justification"]
        assert phrases(justification) <= 3, question
