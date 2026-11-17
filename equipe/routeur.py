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

from equipe import cache, langage
from equipe.outils.champs import NON_RENSEIGNE, codes as _codes, texte as _texte
from equipe.outils.positives import chiffres

# Mots tolérés après le motif de comptage : ils ne changent pas la question.
# Les tirets sont acceptés comme séparateurs (« y a-t-il »), et la politesse est
# retirée avant le match par _sans_politesse.
FIN = r"(?:[\s-]+(?:y|a|t|il|on|ont|est|sont|compte|contient|dans|le|la|les|un|une|des|ce|cet|tableau|fichier|jeu|au|total|en|tout|du|patients|patientes|cohorte|donnees|dataset))*\s*\??"


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
    motif = r"(?:quel(?:le)? (?:est )?|quelle (?:est )?)?(?:l'? ?)?age median(?:e)?(?: des patients| de la cohorte| du tableau)?" + FIN
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
    motif = r"(?:quel(?:le)? (?:est )?|quelle (?:est )?)?(?:l'? ?)?age moyen(?: des patients| de la cohorte| du tableau)?" + FIN
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


# Les groupes nommés en français, et la colonne qui les porte. Un nom absent de
# cette table fait escalader la question : le routeur ne devine jamais un groupe.
LEXIQUE = (
    (("femmes", "femme", "patientes", "patiente"), "Gender", {"0"}),
    (("hommes", "homme", "patients masculins"), "Gender", {"1"}),
    (("zones rurales", "zone rurale", "ruraux", "rurales", "rural", "campagne"), "Rural_or_urban_area", {"0"}),
    (("villes", "ville", "zones urbaines", "urbains", "urbaines", "urbain"), "Rural_or_urban_area", {"1"}),
    (("symptomes cutanes", "symptome cutane", "cutanes", "cutane", "urticaire"), "Skin_Symptoms", {"1"}),
    (
        ("traites pour une rhinite", "traitees pour une rhinite", "rhinite traitee", "traitement de la rhinite", "traites pour rhinite"),
        "Treatment_of_rhinitis",
        {"1", "2", "3", "4"},
    ),
    (("sous biotherapie", "biotherapie", "biologiques", "traitement biologique"), "Treatment_of_athsma", {"6", "7", "8"}),
)

PREFIXES = (
    "patients des ", "patientes des ", "patients ", "patientes ", "sujets ", "personnes ",
    "ceux des ", "celles des ", "ceux ", "celles ", "ayant des ", "ayant ", "avec des ", "avec ",
    "les ", "le ", "la ",
)


def _nettoyer(nom):
    """« les patients ayant des symptômes cutanés » devient « symptomes cutanes »."""
    retour = _plat(nom)
    for prefixe in PREFIXES:  # du plus long au plus court : l'ordre de la table compte
        while retour.startswith(prefixe):
            retour = retour[len(prefixe):].strip()
    return retour


def _groupe(nom):
    """(colonne, codes) du groupe nommé, ou None."""
    for noms, colonne, codes_du_groupe in LEXIQUE:
        if nom in noms:
            return colonne, codes_du_groupe
    return None


def _taux_codes(tableau, colonne, codes_du_groupe, cible="Sensitization", code_cible="1"):
    """(touches, n) chez les patients qui portent un des codes ; None sous trente patients."""
    if colonne not in tableau.columns or cible not in tableau.columns:
        return None
    bruts = tableau[colonne].map(_texte)
    cibles = tableau[cible].map(_codes)
    porte = tableau[colonne].map(_codes).map(lambda valeurs: bool(valeurs & set(codes_du_groupe)))
    renseignes = bruts.notna() & (bruts != NON_RENSEIGNE) & cibles.map(bool)
    du_groupe = renseignes & porte
    n = int(du_groupe.sum())
    if n < 30:
        return None
    return int((du_groupe & cibles.map(lambda valeurs: code_cible in valeurs)).sum()), n


def _comparaison(question, tableau):
    """« Les femmes sont-elles plus souvent sensibilisées que les hommes ? »

    Deux formes, deux calculs : deux groupes nommés se comparent entre eux ;
    un seul groupe nommé se compare au reste du tableau.
    """
    cible = r"plus souvent sensibilise\w*"

    deux = re.fullmatch(r"les (?P<a>.+?) sont[- ](?:elles|ils) " + cible + r" que (?P<b>.+?)" + FIN, question)
    if deux:
        nom_a, nom_b = _nettoyer(deux.group("a")), _nettoyer(deux.group("b"))
        groupe_a, groupe_b = _groupe(nom_a), _groupe(nom_b)
        taux_a = _taux_codes(tableau, groupe_a[0], groupe_a[1]) if groupe_a else None
        taux_b = (
            _taux_codes(tableau, groupe_b[0], groupe_b[1])
            if groupe_b and groupe_a and groupe_b[0] == groupe_a[0]
            else None
        )
        if taux_a and taux_b:
            part_a, part_b = 100 * taux_a[0] / taux_a[1], 100 * taux_b[0] / taux_b[1]
            return _reponse(
                "oui" if part_a > part_b else "non",
                f"{nom_a} : {taux_a[0]} sur {taux_a[1]} ({part_a:.1f} %), contre "
                f"{taux_b[0]} sur {taux_b[1]} ({part_b:.1f} %) pour {nom_b}. "
                f"{len(tableau) - taux_a[1] - taux_b[1]} lignes hors de ces deux groupes ou sans valeur "
                "sont exclues ; la définition de Sensitization n'est pas donnée.",
            )
        # Groupe inconnu ou deux colonnes différentes : la forme à un groupe tente
        # sa chance juste après (« que les autres patients » arrive ici).

    un = re.fullmatch(
        r"les (?P<a>.+?) sont[- ](?:elles|ils) " + cible +        r"(?: que (?:les autres|le reste)(?: (?:patients|patientes|du tableau))?)?" + FIN,
        question,
    )
    if not un:
        return None
    nom_a = _nettoyer(un.group("a"))
    groupe_a = _groupe(nom_a)
    if not groupe_a:
        return None
    taux_a = _taux_codes(tableau, groupe_a[0], groupe_a[1])
    if not taux_a:
        return None
    total = _taux_codes(tableau, groupe_a[0], set(groupe_a[1]) | set(_code_miroir(groupe_a)))
    if not total:
        return None
    # Le reste : le complément du groupe, dans les patients renseignés sur la cible.
    bruts = tableau[groupe_a[0]].map(_texte)
    cibles = tableau["Sensitization"].map(_codes)
    renseignes = bruts.notna() & (bruts != NON_RENSEIGNE) & cibles.map(bool)
    n_total = int(renseignes.sum())
    touches_total = int((renseignes & cibles.map(lambda valeurs: "1" in valeurs)).sum())
    n_reste, touches_reste = n_total - taux_a[1], touches_total - taux_a[0]
    if n_reste < 30:
        return None
    part_a, part_reste = 100 * taux_a[0] / taux_a[1], 100 * touches_reste / n_reste
    return _reponse(
        "oui" if part_a > part_reste else "non",
        f"{nom_a} : {taux_a[0]} sur {taux_a[1]} ({part_a:.1f} %), contre "
        f"{touches_reste} sur {n_reste} ({part_reste:.1f} %) chez les autres patients. "
        f"{len(tableau) - n_total} lignes sans groupe ou sans valeur sont exclues ; "
        "la définition de Sensitization n'est pas donnée.",
    )


def _code_miroir(groupe):
    """Les codes de l'autre groupe de la même colonne : sert à reconstruire le total renseigné."""
    colonne, codes_du_groupe = groupe
    autres = set()
    for _noms, colonne_autre, codes_autre in LEXIQUE:
        if colonne_autre == colonne:
            autres |= set(codes_autre)
    return autres - set(codes_du_groupe)


# Mots qui ne portent aucun sens pour le calcul : ils peuvent apparaître dans
# n'importe quel ordre, ou manquer, sans changer la réponse.
BRUIT = frozenset(
    """le la les l un une des de du d au aux a et ou que qui quoi quel quelle quels quelles
    est sont son se ce cet cette ces dans en pour par sur avec sans y il elle ils elles
    t donc alors aussi svp stp merci beaucoup plus moins souvent davantage environ
    combien nombre total tout tous toute toutes leur leurs chez parmi entre""".split()
)

# Ce qui explique une comparaison, une fois les groupes et la cible retirés.
VIDES_COMPARAISON = frozenset({"autres", "reste", "comparaison", "compare", "ecart", "difference"})

# Contexte : ces mots désignent le fichier sans le paramétrer.
BRUIT = BRUIT | frozenset(
    {"dataset", "donnees", "fichier", "tableau", "jeu", "se", "sa", "tous", "zone", "zones",
     "patient", "patients", "patiente", "patientes", "sujet", "sujets", "personne", "personnes",
     "on", "ont"}
)


def _groupes_dans(mots):
    """Les groupes nommés présents, les noms de deux mots essayés d'abord (« zones rurales »)."""
    trouves, i = [], 0
    while i < len(mots):
        if i + 1 < len(mots):
            deux_mots = mots[i] + " " + mots[i + 1]
            groupe = _groupe(deux_mots)
            if groupe:
                trouves.append((deux_mots, groupe))
                i += 2
                continue
        groupe = _groupe(mots[i])
        if groupe:
            trouves.append((mots[i], groupe))
        i += 1
    return trouves


def _reste_explique(mots, consommes, tolere):
    """Vrai si tous les mots porteurs sont expliqués par les groupes, la cible ou une tolérance."""
    return all(
        mot in consommes or mot in tolere for mot in mots
    )


def _sac_comparaison(question, tableau):
    """La comparaison, tolérée aux fautes et à l'ordre : « feme son sensibiler dent le datset »."""
    mots = [mot for mot in question.split() if mot not in BRUIT]
    if not any(mot.startswith("sensibilis") for mot in mots):
        return None
    groupes = _groupes_dans(mots)
    if not groupes:
        return None
    noms = {mot for nom, _groupe_trouve in groupes for mot in nom.split()}
    consommes = noms | {mot for mot in mots if mot.startswith("sensibilis")}
    if not _reste_explique(mots, consommes, VIDES_COMPARAISON):
        return None  # un mot non expliqué : il change peut-être la question, on escalade
    if len(groupes) >= 2 and groupes[0][1][0] == groupes[1][1][0]:
        return _comparaison_deux(mots, groupes, tableau)
    if len(groupes) == 1:
        return _comparaison_reste(groupes[0], tableau)
    return None


def _comparaison_deux(mots, groupes, tableau):
    (nom_a, groupe_a), (nom_b, groupe_b) = groupes[0], groupes[1]
    taux_a = _taux_codes(tableau, groupe_a[0], groupe_a[1])
    taux_b = _taux_codes(tableau, groupe_b[0], groupe_b[1])
    if not taux_a or not taux_b:
        return None
    part_a, part_b = 100 * taux_a[0] / taux_a[1], 100 * taux_b[0] / taux_b[1]
    return _reponse(
        "oui" if part_a > part_b else "non",
        f"{nom_a} : {taux_a[0]} sur {taux_a[1]} ({part_a:.1f} %), contre "
        f"{taux_b[0]} sur {taux_b[1]} ({part_b:.1f} %) pour {nom_b}. "
        f"{len(tableau) - taux_a[1] - taux_b[1]} lignes hors de ces deux groupes ou sans valeur "
        "sont exclues ; la définition de Sensitization n'est pas donnée.",
    )


def _comparaison_reste(groupe, tableau):
    nom_a, (colonne, codes_du_groupe) = groupe
    taux_a = _taux_codes(tableau, colonne, codes_du_groupe)
    if not taux_a:
        return None
    bruts = tableau[colonne].map(_texte)
    cibles = tableau["Sensitization"].map(_codes)
    renseignes = bruts.notna() & (bruts != NON_RENSEIGNE) & cibles.map(bool)
    n_total = int(renseignes.sum())
    touches_total = int((renseignes & cibles.map(lambda valeurs: "1" in valeurs)).sum())
    n_reste, touches_reste = n_total - taux_a[1], touches_total - taux_a[0]
    if n_reste < 30:
        return None
    part_a, part_reste = 100 * taux_a[0] / taux_a[1], 100 * touches_reste / n_reste
    return _reponse(
        "oui" if part_a > part_reste else "non",
        f"{nom_a} : {taux_a[0]} sur {taux_a[1]} ({part_a:.1f} %), contre "
        f"{touches_reste} sur {n_reste} ({part_reste:.1f} %) chez les autres patients. "
        f"{len(tableau) - n_total} lignes sans groupe ou sans valeur sont exclues ; "
        "la définition de Sensitization n'est pas donnée.",
    )


def _sac_compte(question, tableau):
    """« Combien de femmes sont sensibilisées, dans ce dataset ? » — sans ordre imposé."""
    mots = [mot for mot in question.split() if mot not in BRUIT]
    if not any(mot.startswith("combien") or mot == "nombre" for mot in question.split()):
        return None
    if not any(mot.startswith("sensibilis") for mot in mots):
        return None
    groupes = _groupes_dans(mots)
    if len(groupes) != 1:
        return None
    nom, (colonne, codes_du_groupe) = groupes[0]
    consommes = set(nom.split()) | {mot for mot in mots if mot.startswith("sensibilis")}
    if not _reste_explique(mots, consommes, frozenset()):
        return None
    taux = _taux_codes(tableau, colonne, codes_du_groupe)
    if not taux:
        return None
    return _reponse(
        taux[0],
        f"{taux[0]} patients sur {taux[1]} ({nom}) sont sensibilisés, soit "
        f"{100 * taux[0] / taux[1]:.1f} %. Les autres lignes sont hors du groupe ou sans valeur.",
    )


INTENTIONS = (_sac_comparaison, _sac_compte)


ROUTES = (
    _lignes,
    _age_median,
    _age_moyen,
    _repartition_puces,
    _plus_moins_de_ans,
    _taux_jeunes,
    _region_dominante,
    _comparaison,
    _positifs,
)


def router(question, tableau=None):
    """La réponse locale, ou None si aucune route ne reconnaît la question."""
    plat = _sans_politesse(_plat(question))
    # Un « ? » isolé après un mot est un jeton à part : il ne doit pas compter
    # comme un mot porteur, sinon tout le repli tolérant échoue pour un point
    # d'interrogation.
    plat = " ".join(mot for mot in plat.split() if mot.strip("?!.,;:"))
    tableau = cache.tableau() if tableau is None else tableau
    for route in ROUTES:
        reponse = route(plat, tableau)
        if reponse is not None:
            return reponse

    # Repli tolérant : même intention, ordre libre et fautes corrigées. Une route
    # stricte n'est qu'un chemin propre ; celui-ci accepte les chemins de traverse.
    corrigee = langage.corriger(plat)
    for texte in (plat, corrigee):
        for route in ROUTES:  # un motif strict peut se déclencher après correction
            reponse = route(texte, tableau)
            if reponse is not None:
                return reponse
        for intention in INTENTIONS:
            reponse = intention(texte, tableau)
            if reponse is not None:
                return reponse
    return None
