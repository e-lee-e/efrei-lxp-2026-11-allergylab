"""Outil `calculer` : une statistique sur le tableau, calculée par pandas, jamais par le modèle.

Un seul outil pour tout (compter, moyenne, médiane, pourcentage, valeurs
manquantes, corrélation), comme le conseille Hugging Face : moins d'outils,
moins d'étapes, moins de jetons. Il rend une phrase qui dit le résultat, sur
combien de patients il porte et combien de valeurs manquantes ont été ignorées.

Il remplace trois outils qu'on avait écrits à côté, mesurés puis fusionnés ici :
- taux par groupe        -> pourcentage, avec `par` = la colonne des groupes ;
- taux par présence      -> pourcentage, avec `par` = « colonne dans 1,2,3,4 » ;
- positifs au-dessus d'un seuil -> pourcentage, avec le filtre « Bet_v_1>=0.3 ».
Les cellules à plusieurs codes (« 1,3 ») et le code 9 sont lus par _filtre.py.

Il applique deux cas de la consigne d'abstention : colonne absente (voir
_filtre.py) et colonne vide pour ces patients. Dans le second cas il rend une
phrase qui commence par « ABSTENTION ». Les cas qui demandent de comprendre la
question (ambiguïté, sans rapport avec les données) restent au modèle.

Pas de seuil de taille de groupe : un petit groupe est une question légitime
du chercheur, qui doit recevoir le chiffre avec le nombre de patients retenus,
et juger lui-même. Refuser limiterait ses questions.

Le filtre vient du modèle : il est lu et appliqué par _filtre.py, sans eval.
"""

import pandas as pd
from smolagents import tool

from equipe.outils._filtre import appliquer, base, colonne_connue, groupes
from equipe.outils._tableau import tableau

OPERATIONS = ("compter", "moyenne", "mediane", "pourcentage", "manquants", "correlation")


def nombre(valeur):
    """33.0 -> « 33 », 1.50500001 -> « 1.505 » : quatre décimales au plus."""
    return format(round(float(valeur), 4), "f").rstrip("0").rstrip(".")


def calculer_sur(tab, operation, colonne="", filtre="", colonne2="", par=""):
    """Le calcul, sur un tableau donné (les tests lui passent la table inventée)."""
    operation = operation.strip().lower()
    if operation not in OPERATIONS:
        raise ValueError(f"Opération inconnue : « {operation} ». Choisis parmi : {', '.join(OPERATIONS)}.")

    # Par groupe : le même calcul, refait sur chaque groupe, une ligne par groupe.
    if par.strip():
        parts = groupes(tab, par)
        ecartes = len(tab) - sum(len(patients) for _, patients in parts)
        lignes = [f"{nom} : {calculer_sur(patients, operation, colonne, filtre, colonne2)}" for nom, patients in parts]
        return f"Par {par.strip()} ({ecartes} patients sans valeur écartés) :\n" + "\n".join(lignes)

    groupe = appliquer(tab, filtre)
    n = len(groupe)
    cadre = f"filtre : {filtre.strip()}" if filtre.strip() else "tous les patients"

    # Trois opérations qui comptent des patients.
    if operation == "compter":
        return f"{n} patients sur {len(tab)} ({cadre})."
    if operation == "pourcentage":
        if not filtre.strip():
            raise ValueError("Le pourcentage demande un filtre : la part des patients qui le vérifient.")
        # Le dénominateur ne compte que les patients dont les colonnes du filtre sont renseignées.
        total = len(base(tab, filtre))
        if total == 0:
            return f"ABSTENTION : aucun patient n'a de valeur dans les colonnes du filtre ({filtre.strip()})."
        ignores = f", {len(tab) - total} sans valeur ignorés" if total < len(tab) else ""
        return f"{nombre(100 * n / total)} % des patients ({n} sur {total}{ignores} ; {cadre})."
    if operation == "manquants":
        vides = int(colonne_connue(groupe, colonne).isna().sum())
        return f"{vides} patients sans valeur dans {colonne}, sur {n} ({cadre})."

    # Trois statistiques : une colonne en nombre (deux pour la corrélation).
    if operation == "correlation" and not colonne2:
        raise ValueError("La corrélation demande colonne et colonne2, deux colonnes en nombre.")
    noms = [colonne] + ([colonne2] if operation == "correlation" else [])
    for nom in noms:
        colonne_connue(tab, nom, numerique=True)
    utiles = groupe[noms].dropna()  # les valeurs manquantes ne comptent pas
    if n == 0:
        return f"ABSTENTION : aucun patient ne vérifie le filtre ({filtre.strip()})."
    if utiles.empty:
        return f"ABSTENTION : {' et '.join(noms)} n'a aucune valeur chez ces {n} patients ({cadre})."

    if operation == "correlation":
        r = utiles[colonne].corr(utiles[colonne2])
        if pd.isna(r):
            return f"ABSTENTION : une des colonnes est constante sur ces patients, la corrélation n'existe pas ({cadre})."
        resultat = f"Corrélation de Pearson entre {colonne} et {colonne2} : {nombre(r)}"
    else:
        valeur = utiles[colonne].mean() if operation == "moyenne" else utiles[colonne].median()
        resultat = f"{'Moyenne' if operation == 'moyenne' else 'Médiane'} de {colonne} : {nombre(valeur)}"
    return f"{resultat} (calculée sur {len(utiles)} patients, {n - len(utiles)} sans valeur ignorés ; {cadre})."


@tool
def calculer(operation: str, colonne: str = "", filtre: str = "", colonne2: str = "", par: str = "") -> str:
    """Calcule une statistique sur les patients du tableau et rend une phrase : le résultat, le nombre de patients retenus et le nombre de valeurs manquantes ignorées.
    Si la phrase commence par « ABSTENTION », ne donne aucun chiffre : réponds par une abstention en reprenant la raison.
    Les noms de colonnes s'écrivent exactement : cherche-les d'abord avec `chercher_colonne`.
    Elle lit seule les cellules à plusieurs codes (« 1,3 ») et écarte le code 9 (sauf avec !=) : ne refais pas ce travail à la main.

    Args:
        operation: « compter » (nombre de patients), « moyenne », « mediane », « pourcentage » (part des patients qui vérifient le filtre, sur tous les patients), « manquants » (patients sans valeur dans la colonne) ou « correlation » (Pearson entre colonne et colonne2).
        colonne: la colonne du calcul, au nom exact. Inutile pour « compter » et « pourcentage ».
        filtre: pour restreindre à un groupe : des conditions « colonne comparaison valeur » reliées par « et », avec = != < <= > >=. Exemples : « Age<18 », « Chip_Type=ALEX et Sensitization=1 ». « dans » prend plusieurs codes : « Treatment_of_rhinitis dans 1,2,3,4 ». Pour un seuil de dosage : « Bet_v_1>=0.3 ». Vide : tous les patients.
        colonne2: la seconde colonne, pour « correlation » seulement.
        par: pour comparer des groupes, le même calcul pour chacun. Une colonne (« Gender » : un groupe par valeur) ou une condition (« Treatment_of_rhinitis dans 1,2,3,4 » : oui contre non). Vide : un seul calcul.
    """
    return calculer_sur(tableau(), operation, colonne, filtre, colonne2, par)
