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
            "Chip_Type": ["ISAC_V1", "ISAC_V1", "ALEX", "ALEX"],
            "French_Region": ["regionA", "regionB", "regionA", "regionA"],
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
        "Quel est l'âge moyen des patients ?",
        "Quelle est la répartition des trois puces de test ?",
        "Combien de patients ont plus de 11 ans ?",
        "Combien de patients sont positifs à Bet_v_1 avec un seuil de 0,3 ?",
    )
    for question in questions:
        justification = router(question, tableau)["justification"]
        assert phrases(justification) <= 3, question


def test_age_moyen(tableau):
    reponse = router("Quel est l'âge moyen des patients ?", tableau)
    assert reponse["valeur"] == 12.0
    assert "3 patients" in reponse["justification"]


def test_repartition_des_puces(tableau):
    valeur = router("Quelle est la répartition des trois puces de test ?", tableau)["valeur"]
    assert "ISAC_V1 : 2" in valeur
    assert "ALEX : 2" in valeur


def test_plus_de_n_ans(tableau):
    assert router("Combien de patients ont plus de 11 ans ?", tableau)["valeur"] == 2
    assert router("Combien de patients ont moins de 11 ans ?", tableau)["valeur"] == 1


def test_escalade_un_filtre_combine(tableau):
    assert router("Combien de patients ont plus de 11 ans et une sensibilisation ?", tableau) is None


def test_escalade_une_repartition_qui_n_est_pas_la_puce(tableau):
    assert router("Quelle est la répartition des sexes ?", tableau) is None


def test_taux_chez_les_jeunes():
    tableau = pd.DataFrame(
        {"Age": [10.0] * 40 + [30.0] * 40, "Sensitization": [1] * 30 + [0] * 10 + [0] * 40}
    )
    reponse = router("Quelle proportion des patients de moins de 18 ans est sensibilisée ?", tableau)
    assert reponse["valeur"] == 75.0
    assert "30 sur 40" in reponse["justification"]


def test_escalade_trop_peu_de_jeunes(tableau):
    # Quatre lignes dont deux de moins de 13 ans : sous le seuil de trente, on escalade.
    assert router("Quelle proportion des patients de moins de 13 ans est sensibilisée ?", tableau) is None


def test_region_dominante(tableau):
    assert router("Quelle est la région française la plus représentée ?", tableau)["valeur"] == "regionA"


def test_escalade_une_autre_formulation_de_region(tableau):
    assert router("Quelle région compte le plus de patients ?", tableau) is None


def _tableau_comparaison():
    """Quarante femmes et quarante hommes : au-dessus du seuil de trente patients."""
    return pd.DataFrame(
        {
            "Gender": [0.0] * 40 + [1.0] * 40,
            "Sensitization": [1] * 30 + [0] * 10 + [1] * 20 + [0] * 20,
            "Rural_or_urban_area": [0.0] * 40 + [1.0] * 40,
        }
    )


def test_comparaison_de_deux_groupes():
    reponse = router("les femmes sont-elles plus souvent sensibilisées que les hommes ?", _tableau_comparaison())
    assert reponse["valeur"] == "oui"  # 75 % contre 50 %
    assert "30 sur 40" in reponse["justification"]


def test_comparaison_au_reste_du_tableau():
    reponse = router("les femmes sont-elles plus souvent sensibilisées ?", _tableau_comparaison())
    assert reponse["valeur"] == "oui"
    assert "autres patients" in reponse["justification"]


def test_escalade_un_groupe_inconnu():
    assert router("les professeurs sont-ils plus souvent sensibilisés que les hommes ?", _tableau_comparaison()) is None


def test_escalade_deux_colonnes_differentes():
    assert router("les femmes sont-elles plus souvent sensibilisées que les ruraux ?", _tableau_comparaison()) is None


def test_escalade_une_comparaison_avec_un_age_precise():
    question = "les femmes de plus de 40 ans sont-elles plus souvent sensibilisées que les hommes ?"
    assert router(question, _tableau_comparaison()) is None


def test_apostrophe_typographique(tableau):
    """Une question copiée depuis un traitement de texte utilise « l’ » et non « l' »."""
    assert router("Quel est l’âge médian des patients ?", tableau)["valeur"] == 12.0


def test_patients_inclus_dans_le_jeu(tableau):
    assert router("combien de patients sont inclus dans le jeu de données ?", tableau)["valeur"] == 4


def test_repartition_entre_les_trois_types_de_puces(tableau):
    valeur = router("Quelle est la répartition des patients entre les trois types de puces ?", tableau)["valeur"]
    assert "ISAC_V1 : 2" in valeur


def test_effectifs_de_deux_groupes():
    assert router("Combien de patients sont des femmes et combien sont des hommes ?", _tableau_comparaison())[
        "valeur"
    ] == "40 femmes ; 40 hommes"
