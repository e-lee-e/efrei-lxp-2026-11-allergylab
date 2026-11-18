"""Lecture des cellules du fichier et calculs par groupe, sur une table inventée.

La table est fausse exprès : elle contient un 9 (non renseigné), une cellule à
valeurs multiples, une case vide et un sexe inconnu, pour vérifier que les
dénominateurs sont justes. Ces cas viennent des anciens outils taux_par_groupe,
taux_par_presence et positifs, fusionnés dans `calculer` ; les mêmes chiffres
doivent sortir. Aucun réseau, aucun modèle, aucun jeton.
"""

import pandas as pd
import pytest

from equipe.outils import calculer
from equipe.outils.champs import codes, texte
from equipe.outils.positives import chiffres
from garde_fous import sans_fichier_reel, sans_reseau, sans_vrai_cache, sans_vraie_cle  # noqa: F401  (actifs d'office)


@pytest.fixture
def tableau():
    return pd.DataFrame(
        {
            "Gender": [1.0, 0.0, 1.0, 0.0, None, 9.0, 1.0, 0.0, 1.0, 0.0],
            "Sensitization": [1, 1, 0, 1, 1, 1, 9, 0, 1, 0],
            "General_cofactors": ["1, 10", "9", "4, 5", "0", None, "1", "10", "2", "9", "4"],
            "Bet_v_1": [0.5, 2.0, None, 0.3, 1.0, 0.0, 5.0, None, 0.29, 1.5],
        }
    )


def test_texte_ramene_les_flottants_entiers():
    assert texte(1.0) == "1" and texte("9") == "9" and texte(None) is None


def test_codes_separe_les_valeurs_multiples_et_ecarte_le_9():
    assert codes("4, 5, 10") == {"4", "5", "10"}
    assert codes("9") == set() and codes("") == set() and codes(None) == set()


def test_taux_par_groupe_exclut_les_non_renseignes_et_les_vides(tableau):
    """Ancien taux_par_groupe : par sexe, la part sensibilisée, sans le 9 ni le vide."""
    phrase = calculer.calculer_sur(tableau, "pourcentage", filtre="Sensitization=1", par="Gender")
    assert "1 : 66.6667 % des patients (2 sur 3" in phrase
    assert "0 : 50 % des patients (2 sur 4" in phrase
    assert "2 patients sans valeur écartés" in phrase  # le sexe vide et le sexe à 9


def test_taux_ne_confond_pas_1_et_10(tableau):
    """« 1 » ne se trouve pas dans « 10 » : on compare le code exact de la cellule."""
    phrase = calculer.calculer_sur(tableau, "pourcentage", filtre="General_cofactors=1", par="Gender")
    assert "1 : 33.3333 % des patients (1 sur 3" in phrase
    assert "0 : 0 % des patients (0 sur 3" in phrase


def test_taux_par_presence_regroupe_plusieurs_codes():
    """Ancien taux_par_presence : traité = 1 à 4 (cellule « 1,3 » comprise), contre non traité."""
    table = pd.DataFrame(
        {
            "Treatment_of_rhinitis": ["0", "1", "3", "9", "1,3", "1", None],
            "Sensitization": ["1", "1", "1", "1", "0", "0", "1"],
        }
    )
    phrase = calculer.calculer_sur(
        table, "pourcentage", filtre="Sensitization=1", par="Treatment_of_rhinitis dans 1,2,3,4"
    )
    assert "oui : 50 % des patients (2 sur 4" in phrase
    assert "non : 100 % des patients (1 sur 1" in phrase
    assert "2 patients sans valeur écartés" in phrase  # le 9 et la case vide


def test_cellule_multi_codes_comptee_une_fois_par_code():
    """Le cas des questions fausses : « 1,3 » ne doit pas être jetée comme un nombre illisible."""
    table = pd.DataFrame({"Treatment_of_athsma": ["1", "1,3", "3", "0", "10", "6,7"]})
    assert calculer.calculer_sur(table, "compter", filtre="Treatment_of_athsma=3").startswith("2 patients")
    assert calculer.calculer_sur(table, "compter", filtre="Treatment_of_athsma dans 6,7,8").startswith("1 patients")
    assert calculer.calculer_sur(table, "compter", filtre="Treatment_of_athsma=1").startswith("2 patients")  # pas le 10


def test_positifs_ecarte_les_cases_vides_du_denominateur(tableau):
    """Ancien positifs : un dosage vide n'est pas un zéro, il sort du dénominateur."""
    phrase = calculer.calculer_sur(tableau, "pourcentage", filtre="Bet_v_1>=0.3")
    assert phrase.startswith("75 % des patients (6 sur 8, 2 sans valeur ignorés")


def test_positifs_ventile_par_groupe(tableau):
    phrase = calculer.calculer_sur(tableau, "pourcentage", filtre="Bet_v_1>=0.3", par="Gender")
    assert "1 : 66.6667 % des patients (2 sur 3" in phrase
    assert "0 : 100 % des patients (3 sur 3" in phrase


def test_chiffres_du_routeur_donnent_les_memes_nombres(tableau):
    """Le routeur garde son propre calcul : il doit rester d'accord avec calculer."""
    calcul = chiffres(tableau, "Bet_v_1", 0.3)
    assert (calcul["positifs"], calcul["n"]) == (6, 8)


def test_par_refuse_trop_de_groupes():
    table = pd.DataFrame({"Patient_ID": [f"P{i}" for i in range(11)], "Age": range(11)})
    with pytest.raises(ValueError, match="trop de groupes"):
        calculer.calculer_sur(table, "compter", par="Patient_ID")


def test_par_colonne_inconnue_dit_quoi_faire(tableau):
    with pytest.raises(ValueError, match="chercher_colonne"):
        calculer.calculer_sur(tableau, "compter", par="Sexe")


def test_different_de_n_exclut_que_la_valeur_nommee(tableau):
    """« != » garde les 9 : Sensitization!=1 compte les 0 et le 9, pas seulement les 0."""
    assert calculer.calculer_sur(tableau, "compter", filtre="Sensitization!=1").startswith("4 patients")  # 0, 0, 0 et 9
    assert calculer.calculer_sur(tableau, "compter", filtre="Sensitization=0").startswith("3 patients")
    phrase = calculer.calculer_sur(tableau, "pourcentage", filtre="Sensitization!=1")
    assert phrase.startswith("40 % des patients (4 sur 10")  # le dénominateur garde aussi le 9


def test_le_9_d_une_colonne_codee_n_entre_pas_dans_une_moyenne(tableau):
    """Sensitization vaut 0/1 et 9 = non renseigné : la moyenne n'est faite que sur les 0 et 1."""
    phrase = calculer.calculer_sur(tableau, "moyenne", "Sensitization")
    assert phrase.startswith("Moyenne de Sensitization : 0.6667") and "(calculée sur 9 patients" in phrase
    assert "1 sans valeur" in phrase


def test_manquants_compte_le_9_a_part(tableau):
    phrase = calculer.calculer_sur(tableau, "manquants", "Sensitization")
    assert phrase.startswith("1 patients sans valeur dans Sensitization (dont 1 codés 9)")
    assert calculer.calculer_sur(tableau, "manquants", "Bet_v_1").startswith("2 patients sans valeur dans Bet_v_1,")


def test_un_tres_petit_nombre_n_est_pas_affiche_comme_zero():
    """4,2e-05 rendu « 0 » faisait passer une corrélation non nulle pour nulle."""
    assert calculer.nombre(0.000042) != "0"
    assert calculer.nombre(1.23456) == "1.2346"
    assert calculer.nombre(100.0) == "100"
