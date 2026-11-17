"""Tests des outils de l'équipe, sans réseau, sans clé, sans modèle.

Tout se passe sur la table inventée kit/exemple/mini.csv (12 patients). Les
valeurs attendues viennent des fichiers de questions de equipe/questions/ :
une seule source, pas de chiffre recopié ici.
"""

import re
import tomllib
from pathlib import Path

import pytest

from equipe.outils import calculer, chercher_colonne
from garde_fous import sans_fichier_reel, sans_reseau, sans_vraie_cle  # noqa: F401  (actifs d'office)
from kit.donnees import RACINE, charger

EQUIPE = RACINE / "equipe"


@pytest.fixture(scope="module")
def mini():
    return charger(RACINE / "kit" / "exemple" / "mini.csv")


def attendus():
    """{id: question} pour toutes les questions des lots de equipe/questions/."""
    questions = {}
    for fichier in sorted((EQUIPE / "questions").glob("*.toml")):
        for q in tomllib.loads(fichier.read_text(encoding="utf-8"))["question"]:
            questions[q["id"]] = q
    return questions


def valeur(phrase):
    """Le nombre que la phrase de l'outil donne : en tête (« 3 patients… ») ou après « : »."""
    trouve = re.match(r"-?\d+(?:\.\d+)?", phrase) or re.search(r": (-?\d+(?:\.\d+)?)", phrase)
    return float(trouve.group(trouve.lastindex or 0))


# L'appel de calculer qui répond à chaque question de B qui a un chiffre :
# (operation, colonne, filtre, colonne2).
APPELS = {
    "q01": ("compter", "", "", ""),
    "q02": ("moyenne", "Age", "", ""),
    "q03": ("mediane", "Age", "Chip_Type=ISAC_V1", ""),  # groupe de 4 patients : on répond
    "q04": ("moyenne", "Act_d_1", "Chip_Type=ALEX", ""),
    "q05": ("manquants", "French_Region", "", ""),
    "q06": ("moyenne", "Act_d_8", "", ""),
    "q09": ("compter", "", "Age<18", ""),
    "q10": ("compter", "", "Age<18 et Sensitization=1", ""),
    "q11": ("pourcentage", "", "Sensitization=1", ""),
    "q12": ("moyenne", "Age", "Sensitization=1", ""),
    "q13": ("correlation", "Age", "", "Act_d_1"),
    "q14": ("moyenne", "Act_d_1", "Age<10", ""),  # groupe de 2 patients : on répond aussi
}


@pytest.mark.parametrize("identifiant", sorted(APPELS))
def test_chiffre_attendu(identifiant, mini):
    question = attendus()[identifiant]
    phrase = calculer.calculer_sur(mini, *APPELS[identifiant])
    assert valeur(phrase) == pytest.approx(question["attendu"], abs=question["tolerance"]), phrase


def test_petit_groupe_repond_avec_son_effectif(mini):
    """Pas de seuil : le chercheur reçoit le chiffre, et le nombre de patients retenus pour en juger."""
    phrase = calculer.calculer_sur(mini, "moyenne", "Act_d_1", "Age<10")
    assert not phrase.startswith("ABSTENTION") and "2 patients" in phrase


def test_consigne_signale_les_petits_groupes_sans_les_refuser():
    """Décision d'équipe : sous trente patients on répond quand même, en le disant.

    Le camarade voulait supprimer tout seuil ; la consigne fusionnée garde
    l'avertissement (un taux sur dix patients est instable) mais ne s'abstient pas.
    """
    consigne = " ".join((EQUIPE / "consigne.md").read_text(encoding="utf-8").split())
    assert "instable" in consigne and not hasattr(calculer, "SEUIL")


def test_abstention_colonne_vide(mini):
    """q07 : Act_d_8 n'est mesurée pour aucun patient de la puce ALEX."""
    phrase = calculer.calculer_sur(mini, "moyenne", "Act_d_8", "Chip_Type=ALEX")
    assert phrase.startswith("ABSTENTION") and "aucune valeur" in phrase


def test_abstention_aucun_patient(mini):
    assert calculer.calculer_sur(mini, "moyenne", "Age", "Age>200").startswith("ABSTENTION")


def test_valeurs_manquantes_comptees(mini):
    """q06 : 8 patients mesurés sur 12, et la phrase dit combien ont été ignorés."""
    phrase = calculer.calculer_sur(mini, "moyenne", "Act_d_8")
    assert "8 patients" in phrase and "4 sans valeur" in phrase


@pytest.mark.parametrize("appel, morceau", [
    (("moyenne", "Poids", ""), "n'existe pas"),  # colonne absente
    (("moyenne", "French_Region", ""), "en texte"),  # moyenne d'un texte
    (("racine", "Age", ""), "Opération inconnue"),
    (("moyenne", "Age", "Age>"), "Filtre illisible"),
    (("moyenne", "Age", "Age>vieux"), "n'en est pas un"),
    (("pourcentage", "", ""), "demande un filtre"),
    (("correlation", "Age", ""), "colonne2"),
])
def test_erreur_qui_dit_quoi_faire(appel, morceau, mini):
    with pytest.raises(ValueError, match=morceau):
        calculer.calculer_sur(mini, *appel)


@pytest.mark.parametrize("filtre", [
    "__import__('os').system('echo mal')",
    "Age<18; Age>0",
    "Age<18 et Age==__import__",
    "Chip_Type.str.contains('A')",
])
def test_filtre_malveillant_refuse(filtre, mini):
    """Le filtre vient du modèle : ce qui n'est pas « colonne comparaison valeur » est refusé."""
    with pytest.raises(ValueError):
        calculer.calculer_sur(mini, "compter", "", filtre)


def test_aucun_eval_exec_query():
    """Règle de CLAUDE.md : un outil ne passe jamais un texte du modèle à eval, exec ou query."""
    for fichier in (EQUIPE / "outils").glob("*.py"):
        assert not re.search(r"\b(eval|exec)\(|\.query\(", fichier.read_text(encoding="utf-8")), fichier.name


def test_outil_rend_un_texte_court(mini):
    """Règle de CLAUDE.md : un outil rend une valeur simple, jamais le tableau."""
    for appel in APPELS.values():
        assert isinstance(calculer.calculer_sur(mini, *appel), str)
        assert len(calculer.calculer_sur(mini, *appel)) < 300


def test_calculer_branche_sur_le_tableau_de_l_outil(mini, monkeypatch):
    """L'outil décoré lit le tableau par _tableau.tableau() : ici remplacé par la table inventée."""
    monkeypatch.setattr(calculer, "tableau", lambda: mini)
    assert calculer.calculer(operation="compter") == "12 patients sur 12 (tous les patients)."


def test_chercher_colonne(mini):
    assert "French_Region (clinique, texte)" in chercher_colonne.chercher_dans(mini, "région")
    assert "Age (clinique, nombre)" in chercher_colonne.chercher_dans(mini, "AGE")
    assert "Act_d_1 (dosage, nombre)" in chercher_colonne.chercher_dans(mini, "act_d_1")


def test_chercher_colonne_absente(mini):
    """q08 et q16 : aucune colonne de poids ni d'IgE, l'outil le dit simplement."""
    assert chercher_colonne.chercher_dans(mini, "poids").startswith("Aucune colonne")
    assert chercher_colonne.chercher_dans(mini, "IgE").startswith("Aucune colonne")


def test_chercher_colonne_limite_les_resultats(mini, monkeypatch):
    monkeypatch.setattr(chercher_colonne, "MAX_RESULTATS", 2)
    phrase = chercher_colonne.chercher_dans(mini, "e")  # presque toutes les colonnes
    assert phrase.count(" ; ") == 1 and "autres" in phrase


def test_chercher_colonne_mot_vide(mini):
    with pytest.raises(ValueError, match="vide"):
        chercher_colonne.chercher_dans(mini, "  ")


@pytest.mark.parametrize("filtre, morceau", [
    ("Chip_Type>ALEX", "seuls ="),  # un ordre n'a pas de sens sur un texte
    ("Age dans", "illisible"),
    ("Age dans vieux,jeune", "n'en est pas un"),
])
def test_filtre_dans_et_texte_dit_quoi_faire(filtre, morceau, mini):
    with pytest.raises(ValueError, match=morceau):
        calculer.calculer_sur(mini, "compter", "", filtre)


def test_dans_sur_un_nombre(mini):
    assert calculer.calculer_sur(mini, "compter", "", "Age dans 8,34").startswith("2 patients")
