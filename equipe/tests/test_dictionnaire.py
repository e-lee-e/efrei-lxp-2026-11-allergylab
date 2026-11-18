"""Le dictionnaire vient de l'utilisateur : il se lit, ou il le dit."""

import json

import pytest

from equipe import dictionnaire


def test_un_csv_long_donne_les_codes(tmp_path):
    fichier = tmp_path / "dico.csv"
    fichier.write_text(
        "colonne;code;libelle\n"
        "Sexe;0;Féminin\n"
        "Sexe;1;Masculin\n"
        "Treatment_of_athsma;6;anti-IL5 (biothérapie)\n"
        "Treatment_of_athsma;0;aucun\n",
        encoding="utf-8",
    )
    codes = dictionnaire.lire(fichier)
    assert codes["Sexe"] == {"0": "Féminin", "1": "Masculin"}
    assert codes["Treatment_of_athsma"]["6"] == "anti-IL5 (biothérapie)"


def test_un_csv_large_donne_les_memes_codes(tmp_path):
    """Le format de la feuille Excel d'origine : « code = libellé » par cellule."""
    fichier = tmp_path / "dico.csv"
    fichier.write_text(
        "colonne;0;1;9\n"
        "Type d'habitat;0 = Rural;1 = Urbain;9 = Non renseigné\n",
        encoding="utf-8",
    )
    codes = dictionnaire.lire(fichier)
    assert codes["Type d'habitat"] == {"0": "Rural", "1": "Urbain", "9": "Non renseigné"}


def test_un_json_est_accepte_tel_quel(tmp_path):
    fichier = tmp_path / "dico.json"
    fichier.write_text(json.dumps({"Gender": {"0": "féminin", "1": "masculin"}}), encoding="utf-8")
    assert dictionnaire.lire(fichier)["Gender"]["0"] == "féminin"


def test_un_classeur_est_refuse_en_le_nommant(tmp_path):
    fichier = tmp_path / "dico.xlsx"
    fichier.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises(ValueError) as refus:
        dictionnaire.lire(fichier)
    assert "classeur" in str(refus.value) and "CSV" in str(refus.value)


def test_un_fichier_vide_est_refuse(tmp_path):
    fichier = tmp_path / "vide.csv"
    fichier.write_text("colonne;code;libelle\n", encoding="utf-8")
    with pytest.raises(ValueError):
        dictionnaire.lire(fichier)


def test_le_bloc_ne_nomme_que_les_colonnes_du_tableau():
    """Nommer un code d'une colonne absente ferait chercher le modèle au mauvais endroit."""
    codes = {
        "Sexe": {"0": "Féminin", "1": "Masculin"},
        "Conjonctivite": {"1": "oui"},
        "treatment_of_athsma": {"6": "anti-IL5 (biothérapie)"},
    }
    bloc = dictionnaire.bloc(codes, ["Gender", "Treatment_of_athsma"])
    assert "Sexe" not in bloc  # pas de correspondance avec Gender
    assert "Treatment_of_athsma : 6 = anti-IL5" in bloc
    assert "Conjonctivite" not in bloc  # colonne absente du tableau
    assert "ne le devine pas" in bloc


def test_les_groupes_viennent_des_libelles_du_dictionnaire():
    """« biothérapie » n'est plus une constante : c'est le dictionnaire qui le dit."""
    codes = {"Treatment_of_athsma": {"6": "anti-IL5 (biothérapie)", "7": "anti-IL4/13 (biothérapie)",
                                     "0": "aucun", "1": "SABA à la demande"}}
    groupes = dictionnaire.groupes(codes)
    assert groupes["biothérapie"] == ("Treatment_of_athsma", ["6", "7"])
    # Un dictionnaire qui ne nomme pas le concept ne crée pas de groupe.
    assert "biothérapie" not in dictionnaire.groupes({"Sexe": {"0": "F", "1": "M"}})
