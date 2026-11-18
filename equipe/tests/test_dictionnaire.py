"""Le dictionnaire vient de l'utilisateur : il se lit, ou il le dit."""

import json
from pathlib import Path

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


def test_un_classeur_abime_dit_quoi_faire(tmp_path):
    """Un classeur n'est plus refusé d'emblée : il se convertit, ou il dit pourquoi."""
    fichier = tmp_path / "dico.xlsx"
    fichier.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    with pytest.raises(ValueError) as refus:
        dictionnaire.lire(fichier)
    message = str(refus.value)
    assert "CSV" in message
    assert "converti" in message or "classeur" in message


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


def test_une_mosaique_de_panneaux_est_lue(tmp_path):
    """Le dictionnaire du kit n'est pas un tableau : c'est un mur de panneaux."""
    fichier = tmp_path / "mosaique.csv"
    fichier.write_text(
        ",,,\n"
        "Sexe,Abrégé,Anonyme,\n"
        "Masculin,M,1,\n"
        "Féminin,F,0,\n"
        ",,,\n"
        "Type d'habitat,Anonyme,,\n"
        "9 - Non renseigné,9,,\n"
        "0 - Rural,0,,\n"
        "Traitement rhinite,Anonyme,,\n"
        "0 - Aucun,0,,\n"
        "1 - Anti-H1 local,1,,\n",
        encoding="utf-8",
    )
    codes = dictionnaire.lire(fichier)
    assert codes["Sexe"] == {"1": "Masculin", "0": "Féminin"}
    assert codes["Type d'habitat"] == {"9": "9 - Non renseigné", "0": "0 - Rural"}
    assert codes["Traitement rhinite"]["1"] == "1 - Anti-H1 local"


def test_un_classeur_se_lit_quand_libreoffice_est_la(tmp_path):
    """Le classeur du kit se convertit tout seul, sans dépendance Python."""
    import pytest

    if not dictionnaire._soffice():
        pytest.skip("LibreOffice absent : la conversion ne peut pas être essayée")
    source = Path(__file__).resolve().parents[2] / "donnees" / "acc-dictionnaire-final.xls"
    if not source.is_file():
        pytest.skip("dictionnaire du kit absent")
    codes = dictionnaire.lire(source)
    assert codes["Sexe"] == {"1": "Masculin", "0": "Féminin"}
    assert len(codes) >= 20
