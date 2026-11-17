"""Lire une cellule clinique : les codes, le non-renseigné, les valeurs multiples.

Le fichier encode trois choses qu'un outil doit traiter de la même façon
partout, sinon deux outils répondent différemment à la même question :
- 9 veut dire « non renseigné », ce n'est jamais une valeur ;
- une cellule peut porter plusieurs codes (« 4, 5, 10 ») ;
- une case vide n'est pas un zéro.
"""

NON_RENSEIGNE = "9"

VIDES = ("", "nan", "none", "na", "<na>")


def texte(valeur):
    """Un code en texte court : 1.0 devient « 1 », 9 reste « 9 », et un manquant devient None.

    Un NaN compte comme un manquant : sans ça, pandas le transforme en la chaîne
    « nan », qui devient un groupe comme un autre et fausse tous les taux.
    """
    if valeur is None:
        return None
    retour = str(valeur).strip()
    if retour.lower() in VIDES:
        return None
    if retour.endswith(".0") and retour[:-2].isdigit():
        return retour[:-2]
    return retour


def codes(valeur):
    """Les codes d'une cellule : « 4, 5, 10 » donne {"4", "5", "10"} ; 9 et le vide ne donnent rien."""
    retour = texte(valeur)
    if retour is None or retour.lower() in VIDES:
        return set()
    morceaux = {morceau.strip() for morceau in retour.replace(";", ",").split(",")}
    return {morceau for morceau in morceaux if morceau and morceau != NON_RENSEIGNE}
