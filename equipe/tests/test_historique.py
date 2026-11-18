"""Tests de l'historique : une question, une entrée, et la plus récente en tête."""

from equipe import historique


def test_reposer_la_meme_question_la_remonte_sans_doublon(tmp_path):
    fichier = tmp_path / "questions.json"
    historique.enregistrer({"question": "Quel est l'âge médian ?", "valeur": "16", "statut": "reponse"}, fichier)
    historique.enregistrer({"question": "Combien de patients ?", "valeur": "4271", "statut": "reponse"}, fichier)

    entrees = historique.enregistrer({"question": "quel est l AGE median", "valeur": "16.0", "statut": "reponse"}, fichier)

    assert [e["question"] for e in entrees] == ["quel est l AGE median", "Combien de patients ?"]
    assert entrees[0]["valeur"] == "16.0"  # la réponse récente remplace l'ancienne


def test_l_historique_ne_melange_pas_deux_fichiers(tmp_path):
    fichier = tmp_path / "questions.json"
    historique.enregistrer({"question": "Première ?", "fichier": "jeu-1.csv"}, fichier)
    historique.enregistrer({"question": "Seconde ?", "fichier": "jeu-2.csv"}, fichier)

    assert [e["question"] for e in historique.du_fichier("jeu-2.csv", fichier)] == ["Seconde ?"]
    assert [e["question"] for e in historique.du_fichier("jeu-1.csv", fichier)] == ["Première ?"]


def test_un_fichier_abime_ne_casse_rien(tmp_path):
    fichier = tmp_path / "questions.json"
    fichier.write_text("{ ceci n'est pas du json", encoding="utf-8")

    assert historique.charger(fichier) == []
    assert len(historique.enregistrer({"question": "Une question ?"}, fichier)) == 1


def test_le_nombre_d_entrees_est_borne(tmp_path, monkeypatch):
    monkeypatch.setattr(historique, "GARDEES", 2)
    fichier = tmp_path / "questions.json"
    for numero in range(4):
        historique.enregistrer({"question": f"question {numero} ?"}, fichier)

    assert [e["question"] for e in historique.charger(fichier)] == ["question 3 ?", "question 2 ?"]


def test_vider_efface_l_historique(tmp_path):
    fichier = tmp_path / "questions.json"
    historique.enregistrer({"question": "Une question ?"}, fichier)

    assert historique.vider(fichier) == []
    assert historique.charger(fichier) == []
