"""Tests des réglages : le modèle choisi dans la fenêtre ne doit pas fuir hors du processus."""

import pytest

from equipe import cache, reglages


@pytest.fixture(autouse=True)
def fichier_neuf(tmp_path, monkeypatch):
    monkeypatch.setattr(reglages, "CHEMIN", tmp_path / "reglages.json")
    monkeypatch.setattr(reglages, "MODELE_EN_COURS", None)


def test_le_modele_par_defaut_est_celui_du_kit():
    assert reglages.modele() == "developpement"
    assert reglages.libelle() == "Haiku 5.5"


def test_choisir_un_modele_change_aussi_la_cle_de_cache():
    """Une réponse de Haiku resservie à Sonnet serait présentée au mauvais tarif."""
    avant = cache.moteur()
    reglages.choisir_modele("officiel")

    assert reglages.modele() == "officiel"
    assert cache.moteur() != avant
    assert cache.moteur().endswith("officiel")


def test_le_choix_est_retenu_pour_la_prochaine_fois(monkeypatch):
    reglages.choisir_modele("officiel")

    assert reglages.lire()["modele"] == "officiel"
    # Un processus neuf (un `uv run kit agent`, par exemple) repart sur Haiku :
    # le choix de la fenêtre ne doit pas changer la note d'électricité du terminal.
    monkeypatch.setattr(reglages, "MODELE_EN_COURS", None)
    assert reglages.modele() == "developpement"


def test_un_modele_inconnu_est_refuse():
    with pytest.raises(ValueError):
        reglages.choisir_modele("gpt-imaginaire")


def test_les_fichiers_connus_sans_doublon_ni_fantome(tmp_path):
    vrai = tmp_path / "jeu.csv"
    vrai.write_text("a;b\n1;2\n", encoding="utf-8")
    absent = tmp_path / "disparu.csv"

    reglages.ajouter_fichiers([str(vrai), str(absent), str(vrai)])

    assert reglages.fichiers() == [str(vrai.resolve())]


def test_le_fichier_retenu_doit_exister(tmp_path):
    vrai = tmp_path / "jeu.csv"
    vrai.write_text("a;b\n1;2\n", encoding="utf-8")

    reglages.retenir_fichier(str(vrai))
    assert reglages.fichier_retenu() == str(vrai.resolve())

    vrai.unlink()
    assert reglages.fichier_retenu() is None
