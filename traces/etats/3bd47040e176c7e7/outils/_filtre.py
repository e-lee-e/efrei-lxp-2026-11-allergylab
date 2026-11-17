"""Lire un filtre écrit par le modèle, et vérifier le nom d'une colonne.

Ce n'est pas un outil : le nom commence par « _ » pour que personne ne le
branche sur l'agent. `calculer` s'en sert.

Sécurité : le filtre est un texte venu du modèle. Il est lu par une expression
régulière, puis appliqué par des comparaisons pandas. Jamais d'eval, d'exec
ni de query : ce qui n'a pas la forme « colonne comparaison valeur » est refusé.
"""

import difflib
import operator
import re

import pandas as pd

# Les seules comparaisons permises. « <= » avant « < » : l'ordre compte pour la lecture.
COMPARAISONS = {
    "<=": operator.le, ">=": operator.ge, "!=": operator.ne,
    "<": operator.lt, ">": operator.gt, "=": operator.eq,
}
CONDITION = re.compile(r"^\s*(\w+)\s*(<=|>=|!=|<|>|=)\s*(.+?)\s*$")


def colonne_connue(tab, nom, numerique=False):
    """Rend la colonne, ou lève une erreur qui dit au modèle quoi faire."""
    if nom not in tab.columns:
        proches = difflib.get_close_matches(nom, list(tab.columns), n=3)
        indice = f" Noms proches : {', '.join(proches)}." if proches else ""
        raise ValueError(
            f"La colonne « {nom} » n'existe pas.{indice} Cherche son nom exact avec chercher_colonne ; "
            "si aucune colonne ne convient, la donnée n'existe pas : abstiens-toi."
        )
    if numerique and not pd.api.types.is_numeric_dtype(tab[nom]):
        raise ValueError(f"La colonne « {nom} » est en texte : ce calcul est impossible. Choisis une colonne en nombre, ou abstiens-toi.")
    return tab[nom]


def appliquer(tab, filtre):
    """Les patients qui vérifient toutes les conditions du filtre, séparées par « et »."""
    for condition in filter(None, re.split(r"\s+et\s+", filtre.strip())):
        lue = CONDITION.match(condition)
        if not lue:
            raise ValueError(f"Filtre illisible : « {condition} ». Écris colonne, comparaison, valeur, par exemple « Age<18 ».")
        nom, comparaison, valeur = lue.groups()
        colonne = colonne_connue(tab, nom)
        valeur = valeur.strip("'\"« »")
        if pd.api.types.is_numeric_dtype(colonne):
            try:
                valeur = float(valeur.replace(",", "."))
            except ValueError:
                raise ValueError(f"La colonne « {nom} » est un nombre : « {valeur} » n'en est pas un.") from None
        elif comparaison not in ("=", "!="):
            raise ValueError(f"La colonne « {nom} » est en texte : seuls = et != sont permis.")
        # Les patients sans valeur ne vérifient jamais une condition.
        tab = tab[colonne.notna() & COMPARAISONS[comparaison](colonne, valeur)]
    return tab
