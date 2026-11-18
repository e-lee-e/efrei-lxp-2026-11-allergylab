"""Outil `chercher_colonne` : retrouver le nom exact d'une colonne à partir d'un mot.

Pourquoi il existe : un agent fermé ne voit pas le tableau, donc il ne connaît
pas les noms des colonnes. Sans cet outil, il les devinerait, et se tromperait.
Il rend aussi le bloc (clinique ou dosage) et la lecture (nombre ou texte) de
chaque colonne, deux faits déjà donnés par kit/colonnes.csv.
"""

import unicodedata

from smolagents import tool

from equipe.outils._tableau import tableau
from kit.donnees import NB_CLINIQUES, lecture

MAX_RESULTATS = 15  # au-delà, la liste coûterait des jetons pour rien


def sans_accent(texte):
    """« Région » -> « region », pour que la recherche ignore accents et majuscules."""
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c)).lower()


def chercher_dans(tab, mot):
    """La recherche, sur un tableau donné (les tests lui passent la table inventée)."""
    mot = sans_accent(mot.strip())
    if not mot:
        raise ValueError("Le mot est vide. Donne un mot du nom de la colonne, par exemple « age ».")
    trouvees = [nom for nom in tab.columns if mot in sans_accent(nom)]
    if not trouvees:
        # Pas de colonne : c'est une information, pas une erreur. L'agent peut s'abstenir.
        return f"Aucune colonne ne contient « {mot} » dans son nom."
    lignes = []
    for nom in trouvees[:MAX_RESULTATS]:
        bloc = "clinique" if list(tab.columns).index(nom) < NB_CLINIQUES else "dosage"
        lignes.append(f"{nom} ({bloc}, {lecture(tab[nom])})")
    reste = len(trouvees) - MAX_RESULTATS
    suite = f" ... et {reste} autres : précise le mot." if reste > 0 else ""
    return f"{len(trouvees)} colonne(s) : " + " ; ".join(lignes) + suite


@tool
def chercher_colonne(mot: str) -> str:
    """Cherche les colonnes du tableau dont le nom contient un mot, sans tenir compte des accents ni des majuscules.
    Rend leur nom exact, leur bloc (clinique ou dosage) et leur lecture (nombre ou texte).
    À utiliser avant `calculer`, dont les colonnes doivent être écrites exactement.

    Args:
        mot: un mot ou un morceau de nom de colonne, en anglais de préférence, par exemple « age » ou « region ».
    """
    return chercher_dans(tableau(), mot)
