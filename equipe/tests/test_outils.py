"""Les outils, testés sur une table inventée. Aucun réseau, aucun modèle, aucun jeton.

La table est fausse exprès : elle contient un 9 (non renseigné), une cellule à
valeurs multiples, une case vide et un sexe inconnu, pour vérifier que les
denominateurs sont justes.
"""

import pandas as pd
import pytest

from equipe.outils.champs import codes, texte
from equipe.outils.positives import _positifs
from equipe.outils.taux import _presence, _taux


@pytest.fixture
def tableau():
    return pd.DataFrame(
        {
            "Gender": [1.0, 0.0, 1.0, 0.0, None, 9.0, 1.0, 0.0, 1.0, 0.0],
            "Sensitization": [1, 1, 0, 1, 1, 1, 9, 0, 1, 0],
            "General_cofactors": ["1, 10", "9", "4, 5", "0", "", "1", "10", "2", "9", "4"],
            "Bet_v_1": [0.5, 2.0, None, 0.3, 1.0, 0.0, 5.0, None, 0.29, 1.5],
        }
    )


def test_texte_ramene_les_flottants_entiers():
    assert texte(1.0) == "1"
    assert texte("9") == "9"
    assert texte(None) is None


def test_codes_separe_les_valeurs_multiples_et_ecarte_le_9():
    assert codes("4, 5, 10") == {"4", "5", "10"}
    assert codes("9") == set()
    assert codes("") == set()
    assert codes(None) == set()


def test_taux_exclut_les_non_renseignes_et_les_vides(tableau):
    resume = _taux(tableau, "Gender", "Sensitization", "1")
    assert "1 : 2 sur 3 (66.7 %)" in resume
    assert "0 : 2 sur 4 (50.0 %)" in resume
    # 1 sexe vide, 1 sexe à 9, 1 sensibilisation à 9 : trois lignes hors dénominateur.
    assert "3 ligne(s) sans groupe ou sans valeur, exclues." in resume


def test_taux_ne_confond_pas_1_et_10(tableau):
    resume = _taux(tableau, "Gender", "General_cofactors", "1")
    # Groupe 1 : « 1, 10 » porte le code, « 4, 5 » et « 10 » ne le portent pas.
    assert "1 : 1 sur 3 (33.3 %)" in resume
    assert "0 : 0 sur 3 (0.0 %)" in resume


def test_taux_signale_une_colonne_inconnue(tableau):
    assert "colonne inconnue" in _taux(tableau, "Sexe", "Sensitization", "1")


def test_positifs_ecarte_les_cases_vides_du_denominateur(tableau):
    resume = _positifs(tableau, "Bet_v_1", 0.3)
    assert "6 positifs sur 8 mesurés (75.0 %)" in resume


def test_positifs_ventile_par_groupe(tableau):
    resume = _positifs(tableau, "Bet_v_1", 0.3, "Gender")
    assert "1 : 2 sur 3 (66.7 %)" in resume
    assert "0 : 3 sur 3 (100.0 %)" in resume


def test_positifs_signale_une_molecule_inconnue(tableau):
    assert "colonne inconnue" in _positifs(tableau, "Bet_v_9", 0.3)


def test_presence_regroupe_plusieurs_codes():
    """Un groupe défini par plusieurs codes (traité = 1 à 4) contre ceux qui n'en portent aucun."""
    table = pd.DataFrame(
        {
            "Treatment_of_rhinitis": ["0", "1", "3", "9", "1,3", "1", None],
            "Sensitization": ["1", "1", "1", "1", "0", "0", "1"],
        }
    )
    resume = _presence(table, "Treatment_of_rhinitis", ["1", "2", "3", "4"], "Sensitization", "1")
    assert "porte 1/2/3/4 : 2 sur 4 (50.0 %)" in resume
    assert "aucun de ces codes : 1 sur 1 (100.0 %)" in resume
    assert "2 ligne(s) sans valeur, exclues" in resume
