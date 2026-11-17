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


def _presence(tableau, colonne, liste_codes, colonne_cible, code_cible):
    """Le taux de la cible chez ceux qui portent un des codes, contre ceux qui n'en portent aucun.

    Sert au cas que _taux ne sait pas exprimer : un groupe défini par plusieurs
    codes à la fois (« traité » = 1 à 8) comparé à ceux qui n'en portent aucun.
    Sans cet outil, le modèle réécrit le parsing à la main, soit ~700 jetons de
    sortie par question — mesuré sur la question de la rhinite.
    """
    for nom in (colonne, colonne_cible):
        if nom not in tableau.columns:
            return f"colonne inconnue : {nom!r}."

    cherches = {str(code).strip() for code in liste_codes if str(code).strip()}
    bruts = tableau[colonne].map(texte)
    cibles = tableau[colonne_cible].map(codes)
    porte = tableau[colonne].map(codes).map(lambda valeurs: bool(valeurs & cherches))
    oui = cibles.map(lambda valeurs: str(code_cible).strip() in valeurs)
    # Une cellule qui ne porte que du 9 est non renseignée, pas « ne porte rien ».
    renseignes = bruts.notna() & (bruts != NON_RENSEIGNE) & cibles.map(bool)

    lignes = []
    for nom, masque in (
        ("porte " + "/".join(sorted(cherches)), porte),
        ("aucun de ces codes", ~porte),
    ):
        du_groupe = renseignes & masque
        n = int(du_groupe.sum())
        if n:
            touches = int((du_groupe & oui).sum())
            lignes.append(f"{nom} : {touches} sur {n} ({100 * touches / n:.1f} %)")

    ecartees = int(len(tableau) - renseignes.sum())
    entete = (
        f"{colonne_cible} = {code_cible!r} selon {colonne} ; "
        f"{ecartees} ligne(s) sans valeur, exclues."
    )
    return entete + "\n" + "\n".join(lignes or ["aucun groupe renseigné."])


@tool
def taux_par_presence(
    colonne: str, codes_cherches: str, colonne_cible: str = "Sensitization", code_cible: str = "1"
) -> str:
    """Taux de la cible chez les patients portant au moins un des codes, contre les autres.

    À utiliser dès qu'un groupe se définit par plusieurs codes possibles, par
    exemple « traité pour rhinite » = 1, 2, 3 ou 4, comparé aux non-traités (0).

    Args:
        colonne: colonne clinique codée, par exemple "Treatment_of_rhinitis".
        codes_cherches: les codes du groupe, séparés par des virgules, par exemple "1,2,3,4".
        colonne_cible: colonne clinique codée qui porte le résultat, "Sensitization" par défaut.
        code_cible: le code qui vaut « oui » dans la cible, "1" par défaut.

    Returns:
        Deux lignes : ceux qui portent un des codes, puis ceux qui n'en portent
        aucun, avec effectif, nombre et pourcentage. Le code 9 et le vide sont exclus.
    """
    liste = str(codes_cherches).replace(";", ",").split(",")
    return _presence(cache.tableau(), colonne, liste, colonne_cible, code_cible)


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
