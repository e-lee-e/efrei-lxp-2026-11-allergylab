"""L'exécuteur du traducteur, testé sans réseau : seule la traduction coûte.

La règle vérifiée ici : une requête invalide ne doit jamais produire de réponse.
Une traduction acceptée à tort coûterait une réponse fausse, dite avec aplomb.
"""

import pandas as pd

from equipe.traducteur import _valider, executer


def tableau():
    return pd.DataFrame(
        {
            "Gender": [0.0, 0.0, 1.0, 1.0, None, 9.0],
            "Sensitization": [1, 0, 1, 1, 1, 1],
            "Age": [10.0, 20.0, 30.0, 40.0, None, 50.0],
            "Chip_Type": ["ISAC_V1", "ALEX", "ALEX", "ISAC_V2", "ISAC_V1", "ALEX"],
            "French_Region": ["regionA", "regionA", "regionB", "regionB", "regionA", "regionA"],
        }
    )


def test_compter_les_lignes():
    assert executer({"operation": "compter_lignes"}, tableau())["valeur"] == 6


def test_effectif_d_un_groupe():
    requete = {"operation": "effectif_groupe", "colonne": "Gender", "codes": ["0"]}
    assert executer(requete, tableau())["valeur"] == 2


def grand_tableau():
    """Quarante patients par groupe : au-dessus du seuil de trente, sinon on escalade."""
    return pd.DataFrame(
        {
            "Gender": [0.0] * 40 + [1.0] * 40,
            "Sensitization": [1] * 30 + [0] * 10 + [1] * 20 + [0] * 20,
        }
    )


def test_taux_d_un_groupe():
    requete = {"operation": "taux_groupe", "colonne": "Gender", "codes": ["1"], "cible": "Sensitization"}
    assert executer(requete, grand_tableau())["valeur"] == 50.0


def test_comparer_deux_groupes():
    requete = {
        "operation": "comparer_groupes",
        "colonne": "Gender",
        "codes": ["0"],
        "colonne_b": "Gender",
        "codes_b": ["1"],
        "cible": "Sensitization",
    }
    assert executer(requete, grand_tableau())["valeur"] == "oui"  # 75 % contre 50 %


def test_valeur_dominante():
    requete = {"operation": "valeur_dominante", "colonne": "French_Region"}
    assert executer(requete, tableau())["valeur"] == "regionA"


def test_une_colonne_numerique_ne_devient_pas_un_groupe():
    requete = {"operation": "effectif_groupe", "colonne": "Age", "codes": ["18"]}
    assert _valider(requete, tableau()) is None


def test_une_colonne_inconnue_est_refusee():
    requete = {"operation": "repartition", "colonne": "Poids"}
    assert _valider(requete, tableau()) is None
