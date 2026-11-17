"""Le traducteur : question en français libre → requête canonique, exécutée localement.

Le routeur reconnaît des formulations ; il échoue sur la syntaxe, pas sur les
mots. Un « combien ya til de patient » n'a aucun mot inconnu et ne correspond à
aucun motif. Ce module confie au modèle un travail minuscule — choisir une
opération et ses paramètres dans une liste fermée — puis exécute le calcul
localement. Le modèle ne calcule jamais et n'écrit jamais de pandas.

Deux raisons pour que ce soit rentable :

- la sortie est courte (une requête JSON, une centaine de jetons) alors qu'une
  analyse complète coûte 5 000 à 25 000 jetons d'entrée et plusieurs étapes ;
- le travail demandé est du classement, pas du raisonnement : c'est ce qu'un
  modèle fait de mieux.

Règle de sûreté : une traduction n'est acceptée que si tout est vérifiable —
colonne existante, codes connus, opération prévue. Sinon on escalade vers
l'agent complet, qui coûte plus cher mais sait se débrouiller.
"""

import json
import re

from equipe.outils.champs import NON_RENSEIGNE, codes as _codes, texte as _texte
from kit import modele

# Les opérations que le moteur local sait exécuter, et rien d'autre.
OPERATIONS = (
    "compter_lignes",
    "effectif_groupe",
    "taux_groupe",
    "comparer_groupes",
    "repartition",
    "mediane",
    "moyenne",
    "valeur_dominante",
    "effectifs_deux",
)

CONSIGNE = """Tu traduis une question en une requête JSON. Tu ne réponds à aucune
question et tu ne calcules rien.

Opérations possibles :
- compter_lignes : le nombre de lignes du tableau.
- effectif_groupe : combien de patients dans un groupe.
- taux_groupe : la part d'un groupe qui porte un code dans une colonne cible.
- comparer_groupes : comparer deux groupes sur cette part.
- repartition : la répartition des patients selon une colonne.
- mediane / moyenne : d'une colonne numérique (Age).
- valeur_dominante : la valeur la plus fréquente d'une colonne (région la plus
  représentée, puce la plus utilisée).
- effectifs_deux : le nombre de patients de deux groupes d'une même colonne
  (combien de femmes et combien d'hommes).

Colonnes utilisables, avec leurs codes :
Gender 0=femme 1=homme | Rural_or_urban_area 0=rural 1=urbain |
Skin_Symptoms 0=non 1=oui | Sensitization 0/1 | Chip_Type ISAC_V1 ISAC_V2 ALEX |
Treatment_of_rhinitis 0 aucun, 1 à 4 traité | Treatment_of_athsma 0 aucun,
1 SABA, 2 ICS faible, 3 ICS/LABA faible, 4 ICS/LABA moyen ou fort,
5 ICS/LABA fort, 6 anti-IL5, 7 anti-IL4/13, 8 non répondeur, 10 LTRA |
General_cofactors cumulables 0 aucun, 1 effort, 2 AINS, 3 alcool, 4 moisissures,
5 acariens, 6 chat, 7 chien, 8 cheval, 10 rongeur, 11 mucoviscidose, 12 IPP |
Age numérique | French_Region texte | Blood_Month_sample 1 à 12.

Réponds par un seul objet JSON, sans texte autour :
{"operation": "...", "colonne": "...", "codes": ["..."], "colonne_b": "...",
 "codes_b": ["..."], "cible": "...", "code_cible": "..."}

Règles : mets les codes sous forme de texte. Si la question ne correspond à
aucune opération, ou si elle contient un filtre que ces opérations ne savent pas
exprimer (tranche d'âge, seuil, croisement), réponds {"operation": "inconnu"}.
"""


def _extraire_json(texte):
    """Le premier objet JSON de la réponse, ou None."""
    trouve = re.search(r"\{.*\}", str(texte), re.S)
    if not trouve:
        return None
    try:
        return json.loads(trouve.group(0))
    except json.JSONDecodeError:
        return None


# Colonnes numériques : les traiter comme des groupes de codes fabriquerait des
# réponses fausses (« les patients de plus de 18 ans » n'est pas un groupe de codes).
COLONNES_NUMERIQUES = frozenset({"Age", "Blood_Month_sample"})


def _valider(requete, tableau):
    """Vérifie que la requête ne désigne que des choses qui existent. Rend None si non."""
    if not isinstance(requete, dict):
        return None
    operation = requete.get("operation")
    if operation not in OPERATIONS:
        return None

    def colonne_valide(nom):
        return isinstance(nom, str) and nom in tableau.columns

    if operation in ("compter_lignes",):
        return requete
    if operation in ("mediane", "moyenne"):
        return requete if colonne_valide(requete.get("colonne")) else None
    if operation in ("repartition", "valeur_dominante"):
        return requete if colonne_valide(requete.get("colonne")) else None
    if operation == "effectifs_deux":
        if not colonne_valide(requete.get("colonne")) or requete.get("colonne") in COLONNES_NUMERIQUES:
            return None
        if not isinstance(requete.get("codes"), list) or not isinstance(requete.get("codes_b"), list):
            return None
        return requete
    if operation in ("effectif_groupe", "taux_groupe", "comparer_groupes"):
        if not colonne_valide(requete.get("colonne")):
            return None
        if requete.get("colonne") in COLONNES_NUMERIQUES:
            return None  # un seuil sur un âge n'est pas un groupe de codes
        codes_du_groupe = requete.get("codes")
        if not isinstance(codes_du_groupe, list) or not codes_du_groupe:
            return None
        if operation == "comparer_groupes":
            if not colonne_valide(requete.get("colonne_b")):
                return None
            if requete.get("colonne_b") in COLONNES_NUMERIQUES:
                return None
            if not isinstance(requete.get("codes_b"), list) or not requete.get("codes_b"):
                return None
        if operation == "taux_groupe" and not colonne_valide(requete.get("cible")):
            return None
        return requete
    return None


def traduire(question, modele_local=None):
    """La requête canonique, vérifiée, ou None si le modèle n'a pas su la produire."""
    from smolagents.models import ChatMessage

    modele_local = modele_local or modele.ModeleKit()
    reponse = modele_local.generate(
        [
            ChatMessage(role="system", content=CONSIGNE),
            ChatMessage(role="user", content=question),
        ],
        max_tokens=400,  # le raisonnement interne du modèle mange la sortie
    )
    requete = _extraire_json(reponse.content)
    if not requete:
        return None
    return _valider(requete, _tableau())


def _tableau():
    from equipe import cache

    return cache.tableau()


def _lignes_du_groupe(tableau, colonne, codes_du_groupe):
    """Le masque des patients du groupe, non-renseignés exclus."""
    bruts = tableau[colonne].map(_texte)
    porte = tableau[colonne].map(_codes).map(lambda valeurs: bool(valeurs & set(map(str, codes_du_groupe))))
    return bruts.notna() & (bruts != NON_RENSEIGNE) & porte


def executer(requete, tableau):
    """La réponse à partir de la requête vérifiée. Aucun appel au modèle ici."""
    operation = requete["operation"]

    if operation == "compter_lignes":
        total = len(tableau)
        return _reponse(total, f"Le tableau compte {total} lignes au total, sans filtrage.")

    if operation in ("mediane", "moyenne"):
        import pandas as pd

        colonne = requete["colonne"]
        valeurs = pd.to_numeric(tableau[colonne], errors="coerce").dropna()
        if valeurs.empty:
            return None
        resultat = float(valeurs.median() if operation == "mediane" else valeurs.mean())
        nom = "médian" if operation == "mediane" else "moyen"
        return _reponse(
            resultat,
            f"La valeur {nom}e de {colonne} est {resultat:.2f}, calculée sur {len(valeurs)} lignes "
            f"renseignées ; {len(tableau) - len(valeurs)} lignes sans valeur sont exclues.",
        )

    if operation == "repartition":
        colonne = requete["colonne"]
        valeurs = tableau[colonne].map(_texte).dropna()
        if valeurs.empty:
            return None
        compte = valeurs.value_counts()
        texte = " ; ".join(f"{nom} : {int(nombre)}" for nom, nombre in compte.items())
        return _reponse(
            texte,
            f"Sur {len(valeurs)} lignes renseignées : {texte}. "
            f"{len(tableau) - len(valeurs)} lignes sans valeur sont exclues.",
        )

    if operation == "valeur_dominante":
        colonne = requete["colonne"]
        valeurs = tableau[colonne].map(_texte).dropna()
        if valeurs.empty:
            return None
        compte = valeurs.value_counts()
        nom, nombre = str(compte.index[0]), int(compte.iloc[0])
        return _reponse(
            nom,
            f"{nom} est la valeur la plus fréquente de {colonne}, avec {nombre} patients sur "
            f"{len(valeurs)} renseignés. Les {len(tableau) - len(valeurs)} lignes sans valeur sont exclues.",
        )

    if operation == "effectifs_deux":
        colonne = requete["colonne"]
        morceaux = []
        for codes_du_groupe in (requete["codes"], requete["codes_b"]):
            n = int(_lignes_du_groupe(tableau, colonne, codes_du_groupe).sum())
            morceaux.append(f"{n} ({'/'.join(map(str, codes_du_groupe))})")
        return _reponse(
            " ; ".join(morceaux),
            f"Sur {len(tableau)} lignes : " + ", ".join(morceaux) + ". Les lignes sans groupe renseigné sont exclues.",
        )

    if operation == "effectif_groupe":
        masque = _lignes_du_groupe(tableau, requete["colonne"], requete["codes"])
        n = int(masque.sum())
        return _reponse(
            n,
            f"{n} patients portent les codes {'/'.join(map(str, requete['codes']))} de "
            f"{requete['colonne']}. {len(tableau) - n} lignes sont hors du groupe ou non renseignées.",
        )

    if operation == "taux_groupe":
        return _taux(requete, tableau, avec_comparaison=False)

    if operation == "comparer_groupes":
        return _taux(requete, tableau, avec_comparaison=True)

    return None


def _taux(requete, tableau, avec_comparaison):
    colonne = requete["colonne"]
    cible = requete.get("cible", "Sensitization")
    code_cible = str(requete.get("code_cible", "1"))

    def resume(codes_du_groupe):
        masque = _lignes_du_groupe(tableau, colonne, codes_du_groupe)
        renseignes = masque & tableau[cible].map(_codes).map(bool)
        n = int(renseignes.sum())
        if n < 30:
            return None
        touches = int((renseignes & tableau[cible].map(_codes).map(lambda v: code_cible in v)).sum())
        return touches, n

    premier = resume(requete["codes"])
    if premier is None:
        return None
    if not avec_comparaison:
        taux = 100 * premier[0] / premier[1]
        return _reponse(
            round(taux, 1),
            f"{premier[0]} sur {premier[1]} portent {cible} = {code_cible}, soit {taux:.1f} %. "
            "Les lignes sans groupe ou sans valeur sont exclues.",
        )

    second = resume(requete.get("codes_b") or [])
    if second is None:
        return None
    part_a, part_b = 100 * premier[0] / premier[1], 100 * second[0] / second[1]
    return _reponse(
        "oui" if part_a > part_b else "non",
        f"Premier groupe : {premier[0]} sur {premier[1]} ({part_a:.1f} %) ; second groupe : "
        f"{second[0]} sur {second[1]} ({part_b:.1f} %). La définition de {cible} n'est pas donnée.",
    )


def _reponse(valeur, justification):
    return {"statut": "reponse", "valeur": valeur, "justification": justification}
