"""Le taux d'un code par groupe : « les femmes sont-elles plus souvent X que les hommes ? ».

L'outil ne rend qu'un résumé chiffré, jamais le tableau. Les règles de lecture
du fichier (code 9, valeurs multiples, cases vides) sont dans equipe/outils/champs.py,
appliquées ici une fois pour toutes.

La fonction publique est un outil de smolagents ; le calcul est dans _taux, qui
prend un tableau en argument et se teste sans réseau ni modèle.
"""

from smolagents import tool

from equipe import cache
from equipe.outils.champs import NON_RENSEIGNE, codes, texte

COLONNES_CLINIQUES = 15


def _taux(tableau, colonne_groupe, colonne_cible, code_cherche):
    """Le résumé chiffré : une ligne par groupe, plus le nombre de lignes écartées."""
    for nom in (colonne_groupe, colonne_cible):
        if nom not in tableau.columns:
            cliniques = ", ".join(map(str, tableau.columns[:COLONNES_CLINIQUES]))
            return f"colonne inconnue : {nom!r}. Les colonnes cliniques sont : {cliniques}."

    cherche = str(code_cherche).strip()
    groupes = tableau[colonne_groupe].map(texte)
    cibles = tableau[colonne_cible].map(codes)
    renseignes = groupes.notna() & (groupes != NON_RENSEIGNE) & cibles.map(bool)

    lignes = []
    for nom in sorted(groupes[renseignes].unique()):
        du_groupe = renseignes & (groupes == nom)
        n = int(du_groupe.sum())
        touches = int((du_groupe & cibles.map(lambda valeurs: cherche in valeurs)).sum())
        lignes.append(f"{nom} : {touches} sur {n} ({100 * touches / n:.1f} %)")

    ecartees = int(len(tableau) - renseignes.sum())
    entete = (
        f"{colonne_cible} = {cherche!r}, par {colonne_groupe} ; "
        f"{ecartees} ligne(s) sans groupe ou sans valeur, exclues."
    )
    return entete + "\n" + "\n".join(lignes or ["aucun groupe renseigné."])


@tool
def taux_par_groupe(colonne_groupe: str, colonne_cible: str, code: str) -> str:
    """Part des patients portant un code, pour chaque valeur d'une colonne de groupe.

    Args:
        colonne_groupe: colonne clinique qui définit les groupes, par exemple "Gender".
        colonne_cible: colonne clinique où chercher le code, par exemple "Sensitization".
        code: la valeur cherchée, en texte, par exemple "1".

    Returns:
        Un résumé de quelques lignes : par groupe, l'effectif renseigné, le
        nombre portant le code et le pourcentage. Les non-renseignés (code 9) et
        les cases vides sont exclus du dénominateur.
    """
    return _taux(cache.tableau(), colonne_groupe, colonne_cible, code)
