"""Le dictionnaire d'un jeu de données : les codes d'une colonne, écrits en clair.

Le codebook ne doit pas vivre dans la consigne : chaque utilisateur arrive avec son
propre fichier et ses propres codes. Ce module lit le dictionnaire qu'on lui donne,
et rien d'autre — il ne complète jamais une colonne absente du tableau, et il
n'invente aucun code.

Trois formes acceptées, parce que c'est ce que les gens ont sous la main :

    colonne;code;libelle            CSV long, une ligne par code
    Sexe;0;Féminin
    Type d'habitat;9;Non renseigné

    colonne;0 = non;1 = oui         CSV large, un code par colonne
    Sexe;1 = Masculin;0 = Féminin

    {"Sexe": {"0": "Féminin"}}      JSON, la forme la plus directe

Un quatrième cas, volontairement refusé : un classeur Excel. Il n'y a pas de
lecteur de classeur dans le projet, et en ajouter un pour un fichier que
l'utilisateur peut exporter en CSV serait une dépendance payée pour rien.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

# 30 lignes suffisent : au-delà, le bloc coûte plus en jetons qu'il ne rapporte.
LIGNES_MAX = 30
CODES_MAX = 14

# Les concepts qu'un groupe peut porter : la question nomme le mot, le
# dictionnaire donne les codes dont le libellé le contient. Plus de liste en dur.
CONCEPTS = ("biothérapie", "anti-h1", "corticoïde", "émollient", "dermocorticoïde", "dupilumab")


def _plat(texte):
    return re.sub(r"[^a-z0-9]+", " ", str(texte).lower()).strip()


def _est_code(cellule):
    return bool(re.fullmatch(r"\d{1,3}", str(cellule).strip()))


def lire(chemin):
    """Rend {colonne: {code: libellé}} ; lève ValueError avec la raison sinon."""
    chemin = Path(chemin)
    if not chemin.is_file():
        raise ValueError(f"{chemin.name} est introuvable.")
    if chemin.suffix.lower() in (".xls", ".xlsx", ".ods"):
        raise ValueError(
            f"{chemin.name} est un classeur, pas un dictionnaire lisible : "
            "exporte-le en CSV (colonne;code;libellé) ou en JSON."
        )
    try:
        texte = chemin.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as souci:
        raise ValueError(f"{chemin.name} ne se lit pas en texte ({souci}).") from souci

    if chemin.suffix.lower() == ".json" or texte.lstrip().startswith("{"):
        return _lire_json(texte, chemin)
    return _lire_csv(texte, chemin)


def _lire_json(texte, chemin):
    try:
        charge = json.loads(texte)
    except ValueError as souci:
        raise ValueError(f"{chemin.name} n'est pas un JSON valide ({souci}).") from souci
    if not isinstance(charge, dict):
        raise ValueError(f"{chemin.name} doit être un objet : colonne vers codes.")
    propre = {}
    for colonne, codes in charge.items():
        if isinstance(codes, dict) and codes:
            propre[str(colonne).strip()] = {str(c).strip(): str(v).strip() for c, v in codes.items()}
    if not propre:
        raise ValueError(f"{chemin.name} ne contient aucun code lisible.")
    return propre


def _lire_csv(texte, chemin):
    premiere = texte.splitlines()[0] if texte.splitlines() else ""
    separateur = max((";", ",", "\t", "|"), key=lambda s: premiere.count(s))
    if premiere.count(separateur) == 0:
        raise ValueError(f"{chemin.name} n'a qu'une colonne : on attend colonne;code;libellé.")

    lignes = list(csv.reader(io.StringIO(texte), delimiter=separateur))
    lignes = [ligne for ligne in lignes if any(cellule.strip() for cellule in ligne)]
    if not lignes:
        raise ValueError(f"{chemin.name} est vide.")

    entete = [cellule.strip() for cellule in lignes[0]]
    entete_texte = " ".join(cellule.lower() for cellule in entete)
    # Une ligne d'en-tête qui parle de libellé tranche avant tout : « colonne;code;
    # libelle » n'est pas un format large, même si sa deuxième cellule n'est pas un code.
    if any(mot in entete_texte for mot in ("libell", "label", "signification", "description")):
        return _lire_long(lignes, chemin)
    large = len(entete) > 3 or not _est_code(entete[1] if len(entete) > 1 else "")

    if large:
        return _lire_large(lignes, chemin)
    return _lire_long(lignes, chemin)


def _lire_long(lignes, chemin):
    """colonne ; code ; libellé, avec ou sans ligne d'en-tête."""
    debut = 0
    if lignes and not _est_code(lignes[0][1]) and len(lignes[0]) > 2:
        entete = [c.strip().lower() for c in lignes[0]]
        if any(mot in " ".join(entete) for mot in ("colonne", "variable", "code", "libell")):
            debut = 1
    propre = {}
    for ligne in lignes[debut:]:
        if len(ligne) < 3:
            continue
        colonne, code, libelle = (cellule.strip() for cellule in ligne[:3])
        if not colonne or not code or not libelle:
            continue
        propre.setdefault(colonne, {})[code] = libelle
    if not propre:
        raise ValueError(
            f"{chemin.name} ne donne aucun code : on attend colonne;code;libellé, "
            "ou colonne;0 = libellé;1 = libellé."
        )
    return propre


def _lire_large(lignes, chemin):
    """colonne ; « code = libellé » ; « code = libellé » …"""
    propre = {}
    for ligne in lignes:
        colonne = ligne[0].strip()
        if not colonne:
            continue
        for cellule in ligne[1:]:
            cellule = cellule.strip()
            if not cellule or "=" not in cellule:
                continue
            code, libelle = (morceau.strip() for morceau in cellule.split("=", 1))
            if not code or not libelle:
                continue
            propre.setdefault(colonne, {})[code] = libelle
    if not propre:
        raise ValueError(
            f"{chemin.name} ne donne aucun code : chaque cellule doit s'écrire « code = libellé »."
        )
    return propre


def colonnes_utiles(dico, colonnes):
    """Les entrées du dictionnaire qui portent sur une colonne du tableau.

    La correspondance ignore la casse et les accents : un dictionnaire écrit
    « traitement_athsma » vaut pour la colonne `Treatment_of_athsma`. Une colonne
    du dictionnaire absente du tableau est écartée — nommer un code d'une colonne
    qui n'existe pas ferait chercher le modèle au mauvais endroit.
    """
    if not dico or colonnes is None:
        return {}
    rang = {_plat(nom): nom for nom in colonnes}
    return {
        rang[_plat(colonne)]: codes
        for colonne, codes in dico.items()
        if _plat(colonne) in rang
    }


def bloc(dico, colonnes=None, lignes_max=LIGNES_MAX, codes_max=CODES_MAX):
    """Le dictionnaire prêt pour le prompt, limité aux colonnes du tableau."""
    utiles = colonnes_utiles(dico, colonnes)
    if not utiles:
        return ""
    morceaux = []
    for colonne, codes in list(utiles.items())[:lignes_max]:
        paires = " · ".join(f"{code} = {libelle}" for code, libelle in list(codes.items())[:codes_max])
        reste = len(codes) - codes_max
        morceaux.append(f"- {colonne} : {paires}" + (f" (+{reste} autres)" if reste > 0 else ""))
    if not morceaux:
        return ""
    return (
        "\n\nDictionnaire fourni avec ce fichier (il fait foi sur les codes) :\n"
        + "\n".join(morceaux)
        + "\nUn code absent de cette liste n'a pas de sens connu : ne le devine pas.\n"
    )


def groupes(dico, concepts=CONCEPTS):
    """Les groupes déduits des libellés : {concept: (colonne, [codes])}.

    « biothérapie » n'est plus une constante du traducteur : c'est le dictionnaire
    qui dit quels codes portent le mot. Un dictionnaire sans ce mot ne crée pas de
    groupe — mieux vaut escalader que corriger avec une liste inventée.
    """
    trouves = {}
    for colonne, codes in (dico or {}).items():
        for concept in concepts:
            mot = _plat(concept)
            choisis = [code for code, libelle in codes.items() if mot in _plat(libelle)]
            if choisis:
                trouves.setdefault(concept, (colonne, choisis))
    return trouves
