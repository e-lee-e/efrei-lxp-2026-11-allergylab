"""Lire un filtre écrit par le modèle, former des groupes, vérifier le nom d'une colonne.

Ce n'est pas un outil : le nom commence par « _ » pour que personne ne le
branche sur l'agent. `calculer` s'en sert.

Trois règles de lecture du fichier sont appliquées ici, une fois pour toutes
(sinon le modèle les réécrit à la main, et se trompe) :
- une cellule peut porter plusieurs codes (« 1,3 ») : elle vaut les deux, et
  « 1 » ne se trouve pas dans « 10 » ;
- dans les colonnes cliniques codées, 9 veut dire non renseigné ; ailleurs
  (Age, mois, dosages) 9 est une valeur ;
- une case vide ne vérifie jamais une condition, ni son contraire.

Sécurité : le filtre est un texte venu du modèle. Il est lu par une expression
régulière, puis appliqué par des comparaisons pandas. Jamais d'eval, d'exec
ni de query : ce qui n'a pas la forme « colonne comparaison valeur » ou
« colonne dans valeur,valeur » est refusé.
"""

import difflib
import operator
import re

import pandas as pd

from equipe.outils.champs import NON_RENSEIGNE, texte

# Les seules comparaisons permises. « <= » avant « < » : l'ordre compte pour la lecture.
COMPARAISONS = {
    "<=": operator.le, ">=": operator.ge, "!=": operator.ne,
    "<": operator.lt, ">": operator.gt, "=": operator.eq,
}
CONDITION = re.compile(r"^\s*(\w+)\s*(<=|>=|!=|<|>|=)\s*(.+?)\s*$")
DANS = re.compile(r"^\s*(\w+)\s+dans\s+(.+?)\s*$", re.IGNORECASE)

# Les colonnes où 9 veut dire « non renseigné » (voir consigne.md).
CODEES = {
    "Gender", "Rural_or_urban_area", "Sensitization", "Treatment_of_rhinitis", "Treatment_of_athsma",
    "Age_of_onsets", "Skin_Symptoms", "General_cofactors", "Treatment_of_atopic_dematitis",
}
MAX_GROUPES = 10  # au-delà, la réponse coûterait plus de jetons qu'elle n'en vaut


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


def codes_de(cellule):
    """Les codes d'une cellule : « 1, 3 » donne {"1", "3"} ; une case vide ne donne rien."""
    brut = texte(cellule)
    if brut is None:
        return set()
    return {morceau.strip().casefold() for morceau in brut.replace(";", ",").split(",") if morceau.strip()}


def renseignes(tab, nom):
    """Qui a une vraie valeur dans cette colonne : ni vide, ni 9 dans une colonne codée."""
    colonne = colonne_connue(tab, nom)
    if pd.api.types.is_numeric_dtype(colonne):
        return colonne.notna() & (colonne != 9) if nom in CODEES else colonne.notna()
    return colonne.map(lambda cellule: codes_de(cellule) not in (set(), {NON_RENSEIGNE}))


def analyser(condition):
    """(colonne, comparaison, valeurs) d'une condition ; « dans » est la comparaison à plusieurs valeurs."""
    dans = DANS.match(condition)
    if dans:
        valeurs = [v.strip("'\"« »").strip() for v in dans.group(2).replace(";", ",").split(",")]
        return dans.group(1), "dans", [v for v in valeurs if v]
    lue = CONDITION.match(condition)
    if not lue:
        raise ValueError(
            f"Filtre illisible : « {condition} ». Écris colonne, comparaison, valeur (« Age<18 »), "
            "ou colonne dans valeur,valeur (« Treatment_of_rhinitis dans 1,2,3 »)."
        )
    nom, comparaison, valeur = lue.groups()
    return nom, comparaison, [valeur.strip("'\"« »")]


def masque(tab, condition):
    """Qui vérifie une condition. Une case vide, ou un 9 codé, ne la vérifie jamais."""
    nom, comparaison, valeurs = analyser(condition)
    colonne = colonne_connue(tab, nom)
    if pd.api.types.is_numeric_dtype(colonne):
        try:
            nombres = [float(v.replace(",", ".")) for v in valeurs]
        except ValueError:
            raise ValueError(f"La colonne « {nom} » est un nombre : « {', '.join(valeurs)} » n'en est pas un.") from None
        vrai = colonne.isin(nombres) if comparaison == "dans" else COMPARAISONS[comparaison](colonne, nombres[0])
    else:
        if comparaison not in ("=", "!=", "dans"):
            raise ValueError(f"La colonne « {nom} » est en texte : seuls =, != et dans sont permis.")
        cherches = {v.casefold() for v in valeurs}
        porte = colonne.map(lambda cellule: bool(codes_de(cellule) & cherches))  # le code exact, dans une cellule à plusieurs codes
        vrai = ~porte if comparaison == "!=" else porte
    return renseignes(tab, nom) & vrai


def conditions(filtre):
    """Les conditions d'un filtre, séparées par « et »."""
    return [c for c in re.split(r"\s+et\s+", filtre.strip()) if c]


def appliquer(tab, filtre):
    """Les patients qui vérifient toutes les conditions du filtre."""
    for condition in conditions(filtre):
        tab = tab[masque(tab, condition)]
    return tab


def base(tab, filtre):
    """Les patients dont les colonnes du filtre sont toutes renseignées : le dénominateur d'un pourcentage."""
    for condition in conditions(filtre):
        tab = tab[renseignes(tab, analyser(condition)[0])]
    return tab


def groupes(tab, par):
    """[(étiquette, patients)] : une condition donne « oui » et « non », une colonne un groupe par valeur."""
    par = par.strip()
    if DANS.match(par) or CONDITION.match(par):
        vrai = masque(tab, par)
        return [("oui", tab[vrai]), ("non", tab[renseignes(tab, analyser(par)[0]) & ~vrai])]
    ok = renseignes(tab, par)
    etiquettes = tab[par].map(texte)
    noms = sorted(etiquettes[ok].unique())
    if len(noms) > MAX_GROUPES:
        raise ValueError(
            f"« {par} » a {len(noms)} valeurs : trop de groupes (au plus {MAX_GROUPES}). "
            "Regroupe avec une condition (« Age<18 ») ou choisis une autre colonne."
        )
    return [(nom, tab[ok & (etiquettes == nom)]) for nom in noms]
