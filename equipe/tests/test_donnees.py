"""Rien ne doit jamais être servi d'un autre fichier, ni d'une version révolue.

Ces tests portent sur le seul point qui produit une réponse fausse sans erreur
visible : le cache et le tableau lu. Une erreur, elle, se voit.
"""

import pandas as pd
import pytest

from equipe import cache, routeur


@pytest.fixture(autouse=True)
def isole(tmp_path, monkeypatch):
    """Chaque test a son dossier de cache et repart du fichier du kit."""
    monkeypatch.setattr(cache, "DOSSIER", tmp_path / "cache")
    cache.choisir_fichier(None)
    yield
    cache.choisir_fichier(None)


def ecrire(chemin, lignes, colonnes=("id", "age", "sex")):
    chemin.write_text(
        "\n".join([",".join(colonnes)] + [",".join(str(v) for v in ligne) for ligne in lignes]) + "\n",
        encoding="utf-8",
    )
    return chemin


def test_un_fichier_etranger_se_lit_malgre_ses_autres_regles(tmp_path):
    """Virgule comme séparateur, sexe en lettres : le lecteur du kit ne sait pas le faire."""
    chemin = ecrire(tmp_path / "ailleurs.csv", [(1, 30, "M"), (2, 40, "F"), (3, 50, "F")])
    cache.choisir_fichier(chemin)
    tableau = cache.tableau()
    assert tableau.shape == (3, 3)
    assert list(tableau["age"]) == [30, 40, 50]
    assert list(tableau["sex"]) == ["M", "F", "F"]


def test_changer_de_fichier_change_la_reponse(tmp_path):
    """La même question, deux fichiers, deux réponses — sans cache croisé."""
    petit = ecrire(tmp_path / "petit.csv", [(1, 30, "M")])
    grand = ecrire(tmp_path / "grand.csv", [(i, 30, "M") for i in range(1, 8)])

    cache.choisir_fichier(petit)
    assert routeur.router("Combien de patients ?")["valeur"] == 1
    cache.choisir_fichier(grand)
    assert routeur.router("Combien de patients ?")["valeur"] == 7
    cache.choisir_fichier(petit)
    assert routeur.router("Combien de patients ?")["valeur"] == 1  # et non 7


def test_modifier_le_fichier_sur_place_force_le_recalcul(tmp_path):
    """Même chemin, contenu différent : la réponse doit suivre le contenu."""
    chemin = ecrire(tmp_path / "vivant.csv", [(i, 30, "M") for i in range(1, 5)])
    cache.choisir_fichier(chemin)
    assert routeur.router("Combien de patients ?")["valeur"] == 4

    ecrire(chemin, [(i, 30, "M") for i in range(1, 10)])  # cinq lignes de plus
    assert routeur.router("Combien de patients ?")["valeur"] == 9


def test_la_cle_de_cache_depend_du_contenu(tmp_path):
    """Deux fichiers différents ne doivent jamais partager une entrée de cache."""
    a = ecrire(tmp_path / "a.csv", [(1, 30, "M")])
    b = ecrire(tmp_path / "b.csv", [(1, 31, "M")])
    cache.choisir_fichier(a)
    cle_a = cache.cle("Combien de patients ?")
    cache.choisir_fichier(b)
    assert cache.cle("Combien de patients ?") != cle_a


def test_le_cache_d_un_fichier_ne_sert_pas_a_l_autre(tmp_path):
    a = ecrire(tmp_path / "a.csv", [(1, 30, "M")])
    b = ecrire(tmp_path / "b.csv", [(i, 30, "M") for i in range(1, 4)])
    cache.choisir_fichier(a)
    cache.ecrire("Combien de patients ?", {"statut": "reponse", "valeur": 1, "justification": "Une ligne."})
    cache.choisir_fichier(b)
    assert cache.lire("Combien de patients ?") is None


def test_un_fichier_vide_se_refuse_en_clair(tmp_path):
    vide = tmp_path / "vide.csv"
    vide.write_text("", encoding="utf-8")
    with pytest.raises(cache.DonneeIllisible) as refus:
        cache.choisir_fichier(vide)
    assert "vide" in str(refus.value)
    assert cache.fichier().name != "vide.csv"  # on est resté sur le fichier précédent


def test_un_fichier_binaire_se_refuse_sans_planter(tmp_path):
    binaire = tmp_path / "photo.csv"
    binaire.write_bytes(bytes(range(256)) * 40)
    with pytest.raises(cache.DonneeIllisible):
        cache.choisir_fichier(binaire)


def test_une_seule_colonne_n_est_pas_un_tableau(tmp_path):
    une = tmp_path / "liste.csv"
    une.write_text("patient\nA\nB\nC\n", encoding="utf-8")
    with pytest.raises(cache.DonneeIllisible):
        cache.choisir_fichier(une)


def test_le_fichier_du_kit_garde_les_regles_du_kit():
    """Le fichier publié se lit toujours avec charger(), pas avec le lecteur générique."""
    cache.choisir_fichier(None)
    tableau = cache.tableau()
    assert tableau.shape == (4271, 256)
    assert "Bet_v_1" in tableau.columns


def test_une_question_sur_un_fichier_absent_s_abstient(tmp_path):
    from equipe import agent

    fantome = tmp_path / "disparu.csv"
    ecrire(fantome, [(1, 30, "M")])
    cache.choisir_fichier(fantome)
    fantome.unlink()
    sortie = agent.repondre("Combien de patients ?")
    assert sortie["statut"] == "abstention"
    assert "ne se lit pas" in sortie["justification"]
