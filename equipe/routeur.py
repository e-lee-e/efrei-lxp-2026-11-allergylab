"""Le routeur : répondre sans appeler le modèle, quand la question est reconnaissable.

Une réponse routée coûte zéro jeton. Une erreur de routage coûte une réponse
fausse, dite avec aplomb. D'où deux règles, sans exception :

1. le motif couvre la question entière. « Combien de patients ? » route,
   « combien de patients ont plus de 60 ans ? » ne route pas ;
2. chaque paramètre est retrouvé tel quel : un nom de colonne exact, un seuil
   écrit dans la question. Un paramètre manquant n'est jamais deviné.

Sinon `router` rend None, et l'agent prend la question comme avant. Ajouter une
route, c'est ajouter une fonction à ROUTES et deux tests : une question qui doit
passer, une qui doit escalader.
"""

import re
import unicodedata

import pandas as pd

from equipe import cache
from equipe.outils.champs import NON_RENSEIGNE, codes as _codes, texte as _texte
from equipe.outils.positives import chiffres

# Mots tolérés après le motif de comptage : ils ne changent pas la question.
# Les tirets sont acceptés comme séparateurs (« y a-t-il »), et la politesse est
# retirée avant le match par _sans_politesse.
FIN = r"(?:[\s-]+(?:y|a|t|il|compte|contient|dans|le|ce|cet|tableau|fichier|jeu|au|total|en|tout|du))*\s*\??"


def _plat(texte):
    """Minuscules, sans accents, blancs ramenés à un seul. La ponctuation reste."""
    decompose = unicodedata.normalize("NFKD", texte.lower())
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    return " ".join(sans_accent.split())


POLITESSE = r"(?:merci beaucoup|merci d avance|merci|svp|stp|s il te plait|s il vous plait|please)"


def _sans_politesse(question):
    """Retire les formules de politesse finales : elles ne changent pas la question."""
    retour = question
    while True:
        court = re.sub(r"[\s,.!]*" + POLITESSE + r"[\s?!.,;]*$", "", retour).strip()
        if court == retour:
            return retour
        retour = court


def _reponse(valeur, justification):
    return {"statut": "reponse", "valeur": valeur, "justification": justification}


def _lignes(question, tableau):
    """« Combien de lignes compte le tableau ? »"""
    if not re.fullmatch(
        r"(?:il y a )?combien(?: de| d)? (?:lignes?|patients?|patientes?|individus?|cas)" + FIN,
        question,
    ):
        return None
    total = len(tableau)
    return _reponse(total, f"Le tableau compte {total} lignes au total, sans filtrage.")


def _age_median(question, tableau):
    """« Quel est l'âge médian des patients ? »"""
    motif = r"(?:quel(?:le)? est |quelle est )?(?:l'? ?)?age median(?:e)?(?: des patients| de la cohorte| du tableau)?" + FIN
    if not re.fullmatch(motif, question):
        return None
    ages = pd.to_numeric(tableau["Age"], errors="coerce")
    n = int(ages.notna().sum())
    mediane = float(ages.median())
    return _reponse(
        mediane,
        f"L'âge médian est de {mediane:g} ans sur {n} patients dont l'âge est renseigné. "
        f"Les {len(tableau) - n} lignes sans âge sont exclues.",
    )


def _positifs(question, tableau):
    """« Combien de patients sont positifs à Bet_v_1 au-dessus de 0,3 ? »"""
    if "positif" not in question:
        return None
    if re.search(r"\b(femmes?|filles?|hommes?|garcons?)\b", question):
        return None  # demander un sous-groupe change la réponse : l'agent s'en charge

    molecules = [
        colonne
        for colonne in cache.dosages()
        if colonne in tableau.columns
        and re.search(rf"(?<!\w){re.escape(colonne.lower())}(?!\w)", question)
    ]
    if len(molecules) != 1:
        return None

    seuil = re.search(r"seuil (?:de )?(\d+(?:[.,]\d+)?)", question)
    if seuil is None:
        return None  # sans seuil écrit, la réponse serait un choix que la question ne fait pas

    valeur = float(seuil.group(1).replace(",", "."))
    calcul = chiffres(tableau, molecules[0], valeur)
    if calcul is None or calcul["n"] == 0:
        return None
    return _reponse(
        calcul["positifs"],
        f"{calcul['positifs']} patients sur {calcul['n']} mesurés dépassent {valeur:g} pour "
        f"{molecules[0]}, soit {calcul['taux']:.1f} %. Les cases vides ne sont pas des zéros : "
        "elles sont hors du dénominateur.",
    )


def _age_moyen(question, tableau):
    """« Quel est l'âge moyen des patients ? »"""
    motif = r"(?:quel(?:le)? est |quelle est )?(?:l'? ?)?age moyen(?: des patients| de la cohorte| du tableau)?" + FIN
    if not re.fullmatch(motif, question):
        return None
    ages = pd.to_numeric(tableau["Age"], errors="coerce")
    n = int(ages.notna().sum())
    moyenne = float(ages.mean())
    return _reponse(
        moyenne,
        f"L'âge moyen est de {moyenne:.2f} ans sur {n} patients dont l'âge est renseigné. "
        f"Les {len(tableau) - n} lignes sans âge sont exclues.",
    )


def _repartition_puces(question, tableau):
    """« Quelle est la répartition des puces ? »"""
    motif = (
        r"(?:quel(?:le)? est |quelle est )?(?:la )?repartition des (?:trois |3 )?"
        r"(?:puces?(?: de test)?|types? de puce)" + FIN
    )
    if not re.fullmatch(motif, question) or "Chip_Type" not in tableau.columns:
        return None
    comptes = tableau["Chip_Type"].value_counts()
    texte = " ; ".join(f"{nom} : {int(nombre)}" for nom, nombre in comptes.items())
    return _reponse(
        texte,
        f"Les {len(tableau)} patients se répartissent ainsi : {texte}. "
        "Aucune ligne n'est exclue, la puce est renseignée pour tous.",
    )


def _plus_moins_de_ans(question, tableau):
    """« Combien de patients ont plus de 60 ans ? »"""
    trouve = re.fullmatch(r"combien de patients? ont (plus|moins) de (\d+) ans" + FIN, question)
    if trouve is None:
        return None
    sens, seuil = trouve.group(1), int(trouve.group(2))
    ages = pd.to_numeric(tableau["Age"], errors="coerce")
    n = int(ages.notna().sum())
    compte = int((ages > seuil).sum() if sens == "plus" else (ages < seuil).sum())
    compare = "plus" if sens == "plus" else "moins"
    return _reponse(
        compte,
        f"{compte} patients sur {n} dont l'âge est renseigné ont {compare} de {seuil} ans. "
        f"Les {len(tableau) - n} lignes sans âge sont exclues.",
    )


def _taux_jeunes(question, tableau):
    """« Quelle proportion des patients de moins de 18 ans est sensibilisée ? »"""
    trouve = re.fullmatch(
        r"(?:quelle est la |quelle )?(?:proportion|part|taux) de(?:s)? patients de moins de (\d+) ans"
        r"(?: est| sont| qui sont)? sensibilise\w*" + FIN,
        question,
    )
    if trouve is None or "Sensitization" not in tableau.columns:
        return None
    seuil = int(trouve.group(1))
    ages = pd.to_numeric(tableau["Age"], errors="coerce")
    bruts = tableau["Sensitization"].map(_texte)
    sensibilise = tableau["Sensitization"].map(_codes).map(lambda valeurs: "1" in valeurs)
    # Une cellule vide ou à 9 est non renseignée : elle sort du dénominateur,
    # elle ne compte pas comme « non sensibilisée ».
    renseignes = ages.notna() & bruts.notna() & (bruts != NON_RENSEIGNE)
    du_groupe = renseignes & (ages < seuil)
    n = int(du_groupe.sum())
    if n < 30:  # la règle des trente patients vaut ici aussi : on escalade
        return None
    touches = int((du_groupe & sensibilise).sum())
    taux = 100 * touches / n
    return _reponse(
        round(taux, 1),
        f"Chez les patients de moins de {seuil} ans, {touches} sur {n} sont sensibilisés, "
        f"soit {taux:.1f} %. Les {len(tableau) - n} lignes sans âge ou sans valeur sont exclues.",
    )


def _region_dominante(question, tableau):
    """« Quelle est la région française la plus représentée ? »"""
    motif = (
        r"(?:quel(?:le)? est )?la region(?: francaise)? la plus representee"
        r"(?: dans (?:le|cet|ce) tableau)?" + FIN
    )
    if not re.fullmatch(motif, question) or "French_Region" not in tableau.columns:
        return None
    valeurs = tableau["French_Region"].map(_texte).dropna()
    if valeurs.empty:
        return None
    compte = valeurs.value_counts()
    nom, nombre = str(compte.index[0]), int(compte.iloc[0])
    return _reponse(
        nom,
        f"{nom} est la région la plus représentée, avec {nombre} patients sur {len(valeurs)} "
        f"renseignés. Les {len(tableau) - len(valeurs)} lignes sans région sont exclues.",
    )


ROUTES = (
    _lignes,
    _age_median,
    _age_moyen,
    _repartition_puces,
    _plus_moins_de_ans,
    _taux_jeunes,
    _region_dominante,
    _positifs,
)


def router(question, tableau=None):
    """La réponse locale, ou None si aucune route ne reconnaît la question."""
    plat = _sans_politesse(_plat(question))
    tableau = cache.tableau() if tableau is None else tableau
    for route in ROUTES:
        reponse = route(plat, tableau)
        if reponse is not None:
            return reponse
    return None
