"""L'exécuteur du traducteur, testé sans réseau : seule la traduction coûte.

La règle vérifiée ici : une requête invalide ne doit jamais produire de réponse.
Une traduction acceptée à tort coûterait une réponse fausse, dite avec aplomb.
"""

import pandas as pd

from equipe.traducteur import _valider, executer, filtre_en_francais


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
    assert executer(requete, grand_tableau())["valeur"] == "75.0 % contre 50.0 %"


def test_valeur_dominante():
    requete = {"operation": "valeur_dominante", "colonne": "French_Region"}
    assert executer(requete, tableau())["valeur"] == "regionA"


def test_une_colonne_numerique_ne_devient_pas_un_groupe():
    requete = {"operation": "effectif_groupe", "colonne": "Age", "codes": ["18"]}
    assert _valider(requete, tableau()) is None


def test_une_colonne_inconnue_est_refusee():
    requete = {"operation": "repartition", "colonne": "Poids"}
    assert _valider(requete, tableau()) is None


def tableau_a_filtres():
    """Un petit tableau où une cellule porte deux codes, comme dans le vrai fichier."""
    return pd.DataFrame(
        {
            "Gender": [0.0, 0.0, 1.0, 1.0],
            "Age": [10.0, 25.0, 45.0, 70.0],
            "Rural_or_urban_area": [1.0, 1.0, 0.0, 9.0],
            "Treatment_of_rhinitis": ["1", "1,3", "0", "2"],
        }
    )


def test_un_filtre_d_age_reduit_le_tableau():
    requete = {"operation": "compter_lignes", "filtre": "Age>=18 et Age<=30"}
    assert executer(requete, tableau_a_filtres())["valeur"] == 1


def test_un_filtre_compose_de_trois_conditions():
    requete = {
        "operation": "compter_lignes",
        "filtre": "Age>=18 et Gender=0 et Rural_or_urban_area=1",
    }
    assert executer(requete, tableau_a_filtres())["valeur"] == 1


def test_dans_lit_une_cellule_a_deux_codes():
    """« 1,3 » appartient au groupe 1 à 4 : la comparaison numérique l'aurait jetée."""
    requete = {"operation": "compter_lignes", "filtre": "Treatment_of_rhinitis dans 1,2,3,4"}
    assert executer(requete, tableau_a_filtres())["valeur"] == 3


def test_un_filtre_sur_une_colonne_inconnue_est_refuse():
    requete = {"operation": "compter_lignes", "filtre": "Acariens=1"}
    assert _valider(requete, tableau_a_filtres()) is None


def test_un_filtre_avec_une_comparaison_interdite_est_refuse():
    requete = {"operation": "compter_lignes", "filtre": "Gender ~ 1"}
    assert _valider(requete, tableau_a_filtres()) is None


def test_un_filtre_se_dit_en_francais():
    """La justification s'adresse à un chercheur : « Gender=0 » ne lui parle pas."""
    assert (
        filtre_en_francais("Age>=18 et Age<=30 et Gender=0 et Rural_or_urban_area=1")
        == "âgés de 18 à 30 ans, de sexe féminin, résidant en zone urbaine"
    )
    assert filtre_en_francais("Age>60 et Treatment_of_athsma dans 6,7,8") == "de plus de 60 ans, sous biothérapie"
    assert filtre_en_francais("Blood_Month_sample=7") == "prélevés en juillet"
    # Une condition inconnue rend None : mieux vaut le filtre brut qu'un français faux.
    assert filtre_en_francais("Gender=2") is None
    assert filtre_en_francais("Age>=18 et Colonne_Inventee=1") is None


def test_un_groupe_nomme_retrouve_ses_codes():
    """« Biothérapie » vaut 6, 7 et 8 : le modèle avait rendu 6 et 7, soit 25 patients au lieu de 27."""
    from equipe.traducteur import _rappeler_les_groupes

    requete = {"operation": "effectif_groupe", "colonne": "Treatment_of_athsma", "codes": ["6", "7"]}
    corrigee = _rappeler_les_groupes("Combien de patients prennent une biothérapie pour l'asthme ?", requete)
    assert corrigee["codes"] == ["6", "7", "8"]

    # Une question qui ne nomme pas le groupe ne touche à rien.
    autre = {"operation": "effectif_groupe", "colonne": "Treatment_of_athsma", "codes": ["6", "7"]}
    assert _rappeler_les_groupes("Combien de patients sont sous anti-IL5 ?", autre)["codes"] == ["6", "7"]


def test_un_groupe_nomme_se_corrige_aussi_dans_le_filtre():
    """Une moyenne porte le groupe dans son filtre : « dans 6,7 » doit devenir « dans 6,7,8 »."""
    from equipe.traducteur import _rappeler_les_groupes

    requete = {
        "operation": "moyenne",
        "colonne": "Age",
        "filtre": "Treatment_of_athsma dans 6,7",
    }
    corrigee = _rappeler_les_groupes("Quel est l'âge moyen des patients sous biothérapie ?", requete)
    assert corrigee["filtre"] == "Treatment_of_athsma dans 6,7,8"


def test_les_conditions_qui_jettent_un_age_reel_disparaissent():
    """« Age>0 » est un manquant déguisé ; « Age<9 » et « Age!=9 » seuls sont de vraies questions."""
    from equipe.traducteur import _retirer_conditions_fautives

    assert _retirer_conditions_fautives("Treatment_of_athsma dans 6,7,8 et Age>0") == "Treatment_of_athsma dans 6,7,8"
    assert _retirer_conditions_fautives("Age>=18 et Age<=30") == "Age>=18 et Age<=30"
    # Un « et » orphelin en tête rendait le filtre illisible : la condition doit
    # partir avec son séparateur, des deux côtés.
    assert _retirer_conditions_fautives("Age>0 et Age>=18") == "Age>=18"
    assert _retirer_conditions_fautives("Age>=18 et Age>0") == "Age>=18"
    # Une vraie borne basse n'est pas un manquant : « moins de 9 ans » reste.
    assert _retirer_conditions_fautives("Age<9") == "Age<9"
    # « Age!=9 » seul est une vraie question ; il ne part que si une autre borne
    # écarte déjà 9 ans (sinon la réponse portait sur tout le tableau).
    assert _retirer_conditions_fautives("Age!=9") == "Age!=9"
    assert _retirer_conditions_fautives("Age>=18 et Age!=9") == "Age>=18"
    assert _retirer_conditions_fautives("Age>=18 et Age<9") == "Age>=18"
    assert _retirer_conditions_fautives("Age>0 et Age<9") == "Age<9"


def test_un_code_absent_de_la_colonne_est_refuse():
    """Un code inventé rendrait « 0 patient » avec aplomb : il escalade."""
    assert _valider({"operation": "effectif_groupe", "colonne": "Gender", "codes": ["13"]}, tableau()) is None
    assert _valider({"operation": "effectif_groupe", "colonne": "Gender", "codes": ["0"]}, tableau())


def test_le_code_9_n_est_jamais_un_groupe():
    """`_lignes_du_groupe` écarte le 9 : une requête qui le demande rendrait 0."""
    assert _valider({"operation": "effectif_groupe", "colonne": "Gender", "codes": ["9"]}, tableau()) is None


def test_un_filtre_avec_un_code_absent_est_refuse():
    assert _valider(
        {"operation": "compter_lignes", "filtre": "Treatment_of_rhinitis dans 1,5"}, tableau_a_filtres()
    ) is None
    assert _valider(
        {"operation": "compter_lignes", "filtre": "Treatment_of_rhinitis dans 1,2"}, tableau_a_filtres()
    )


def test_un_filtre_numerique_garde_les_valeurs_absentes():
    """« Age dans 18,19 » est un jeu d'âges : 19 peut n'exister chez personne."""
    table = pd.DataFrame({"Age": [10.0, 18.0, 40.0]})
    assert _valider({"operation": "compter_lignes", "filtre": "Age dans 18,19"}, table)


def test_la_repartition_ecarte_le_non_renseigne():
    table = pd.DataFrame({"Sensitization": ["0", "1", "1", "9", "9"]})
    reponse = executer({"operation": "repartition", "colonne": "Sensitization"}, table)
    assert "9" not in reponse["valeur"]
    assert "2 lignes" in reponse["justification"]


def test_la_valeur_dominante_ecarte_le_non_renseigne():
    """Sans ça, « le traitement le plus fréquent » répond « non renseigné »."""
    table = pd.DataFrame({"Treatment_of_athsma": ["9", "9", "9", "1", "1", "0"]})
    reponse = executer({"operation": "valeur_dominante", "colonne": "Treatment_of_athsma"}, table)
    assert reponse["valeur"] == "1"
    assert "3 lignes" in reponse["justification"]


def test_deux_objets_json_dans_la_reponse_le_premier_gagne():
    from equipe.traducteur import _extraire_json

    assert _extraire_json('Voici {"operation": "compter_lignes"} puis {"note": "fin"}') == {
        "operation": "compter_lignes"
    }
    assert _extraire_json('Réponse : {"operation": "mediane", "colonne": "Age"} et rien')["colonne"] == "Age"


def test_le_traducteur_borne_son_appel():
    """Sans timeout, un appel bloqué côté API n'était borné par rien."""
    from equipe import traducteur

    vus = {}

    class Faux:
        def generate(self, messages, **options):
            vus.update(options)

            class Reponse:
                content = '{"operation": "inconnu"}'

            return Reponse()

    assert traducteur.traduire("une question", modele_local=Faux()) is None
    assert vus["max_tokens"] == 700
    assert vus["timeout"] == traducteur.DELAI_MAX


def test_exclure_une_valeur_garde_les_non_renseignes():
    """« Skin_Symptoms!=1 » doit garder les 2 445 patients au code 9 : ils ne présentent pas le symptôme."""
    import pandas as pd

    from equipe.traducteur import _filtrer

    table = pd.DataFrame({"Skin_Symptoms": ["1", "0", "9", "1,0"]})
    restants = _filtrer(table, "Skin_Symptoms!=1")
    assert sorted(restants["Skin_Symptoms"].tolist()) == ["0", "9"]
