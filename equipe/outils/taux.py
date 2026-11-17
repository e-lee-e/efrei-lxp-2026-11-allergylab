"""Le taux d'un code par groupe : « les femmes sont-elles plus souvent X que les hommes ? ».

L'outil ne rend qu'un résumé chiffré, jamais le tableau. Les règles de lecture
du fichier (code 9, valeurs multiples, cases vides) sont dans equipe/outils/champs.py,
appliquées ici une fois pour toutes.

Attention : le code 9 ne vaut que pour les colonnes cliniques codées. Sur Age ou
sur une colonne de dosage, 9 est une valeur comme une autre — cet outil écartait
donc silencieusement les patients de 9 ans.

La fonction publique est un outil de smolagents ; le calcul est dans _taux, qui
prend un tableau en argument et se teste sans réseau ni modèle.
"""

from smolagents import tool

from equipe import cache
from equipe.outils.champs import NON_RENSEIGNE, codes, texte
from kit.donnees import NB_CLINIQUES


def _taux(tableau, colonne_groupe, colonne_cible, code_cherche):
    """Le résumé chiffré : une ligne par groupe, plus le nombre de lignes écartées."""
    for nom in (colonne_groupe, colonne_cible):
        if nom not in tableau.columns:
            cliniques = ", ".join(map(str, tableau.columns[:NB_CLINIQUES]))
            return f"colonne inconnue : {nom!r}. Les colonnes cliniques sont : {cliniques}."

    cherche = str(code_cherche).strip()
    groupes = tableau[colonne_groupe].map(texte)
    cibles = tableau[colonne_cible].map(codes)
    renseignes = groupes.notna() & (groupes != NON_RENSEIGNE) & cibles.map(bool)

    # « porte le code » ne dépend pas du groupe : calculé une fois pour toutes,
    # et non une fois par groupe (sinon on reparcourt la colonne à chaque tour).
    porte = cibles.map(lambda valeurs: cherche in valeurs)

    lignes = []
    for nom in sorted(groupes[renseignes].unique()):
        du_groupe = renseignes & (groupes == nom)
        n = int(du_groupe.sum())
        touches = int((du_groupe & porte).sum())
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

    Ne pas appeler sur Age ni sur une colonne de dosage : le code 9 n'y veut pas
    dire « non renseigné ».

    Args:
        colonne_groupe: colonne clinique codée qui définit les groupes, par exemple "Gender".
        colonne_cible: colonne clinique codée où chercher le code, par exemple "Sensitization".
        code: la valeur cherchée, en texte, par exemple "1".

    Returns:
        Un résumé de quelques lignes : par groupe, l'effectif renseigné, le
        nombre portant le code et le pourcentage. Les non-renseignés (code 9) et
        les cases vides sont exclus du dénominateur.
    """
    return _taux(cache.tableau(), colonne_groupe, colonne_cible, code)
