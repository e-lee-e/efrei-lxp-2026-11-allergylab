"""Une question de suivi (« et de femmes ? ») redevient une question entière.

Un agent interrogé une question à la fois ne comprend pas l'ellipse : « et de
femmes ? » arrive seul, sans l'homme dont il vient d'être question, et le modèle
répond à côté. Deux issues, et la mauvaise est la plus tentante : envoyer toute la
conversation au modèle, ce qui fait payer la mémoire à chaque étape.

Ici, la résolution est locale et gratuite. La question précédente est reprise telle
quelle, et seul le groupe nommé est remplacé — avec la préposition qui va bien.
Quand le remplacement n'est pas sûr, on ne devine pas : on rend None, et l'agent
le dit à l'utilisateur au lieu de répondre à une question qu'il a inventée.
"""

from __future__ import annotations

import re

from equipe.routeur import LEXIQUE

# Ce qu'une question de suivi peut remplacer : des groupes de population nommés
# dans le lexique du routeur. « patients » n'y est pas, exprès : il désigne tout
# le tableau, et le remplacer n'aurait pas de sens.
SUJETS = {nom for noms, _, _ in LEXIQUE for nom in noms}

AMORCES = ("et ", "idem", "pareil", "même chose", "meme chose", "et alors", "et pour", "et de", "et des")


def _plat(texte):
    return re.sub(r"[^a-z0-9']+", " ", str(texte).lower()).strip()


def est_suivi(question):
    """Une question courte qui commence par « et » ne se tient pas seule."""
    plat = _plat(question)
    if not plat:
        return False
    if len(plat.split()) > 6:
        return False
    return plat.startswith("et ") or any(plat.startswith(amorce) for amorce in AMORCES[1:])


def _sujet(question):
    """Le groupe nommé par la question de suivi, ou None."""
    plat = _plat(question)
    plat = re.sub(r"^(et\s+)?(pour\s+|de\s+|d'\s*|des\s+|du\s+|les\s+|la\s+|le\s+|l'\s*)?", "", plat)
    plat = plat.replace("?", " ").strip()
    mots = plat.split()
    if not mots:
        return None
    for longueur in (3, 2, 1):  # « zones rurales » avant « rurales » avant « rural »
        essai = " ".join(mots[:longueur])
        if essai in SUJETS:
            return essai
    return None


def _accord(precedente, sujet):
    """Remplace le groupe de la question précédente par le nouveau, accordé.

    La question d'origine est reprise telle quelle, accents et majuscules compris :
    la normaliser pour la reconstruire donnait « quel est l' ge m dian des hommes ».
    """
    for ancien in sorted(SUJETS, key=len, reverse=True):
        motif = re.compile(rf"\b{re.escape(ancien)}\b", re.IGNORECASE)
        trouve = motif.search(precedente)
        if not trouve:
            continue
        avant, apres = precedente[: trouve.start()], precedente[trouve.end() :]
        # « d'hommes » ne devient pas « d'femmes » : la préposition suit l'initiale.
        if re.search(r"(d['’]|de)\s*$", avant, re.IGNORECASE):
            avant = re.sub(
                r"(d['’]|de)\s*$",
                "d'" if sujet[0] in "aeiouéèêh" else "de ",
                avant,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", avant + sujet + apres).strip()
    return None


def resoudre(question, precedente):
    """La question entière, ou None quand rien ne permet de la reconstruire."""
    if not precedente or not est_suivi(question):
        return None
    sujet = _sujet(question)
    if not sujet:
        return None
    reconstruite = _accord(precedente, sujet)
    if not reconstruite or reconstruite == _plat(precedente):
        return None
    # La ponctuation d'origine est perdue au passage : une question se termine par
    # un point d'interrogation, sinon le routeur la reconnaît moins bien.
    return reconstruite.rstrip(" .!?") + " ?"
