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

from equipe.outils._filtre import appliquer, colonne_connue
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
Age numérique | French_Region texte | French_Residence_Department texte (deptA,
deptY…) | Blood_Month_sample 1 à 12.

Champ facultatif « filtre » : des conditions sur des colonnes, reliées par
« et », appliquées AVANT l'opération. Exemple : "Age>=18 et Age<=30 et Gender=0".
Comparaisons permises : <, <=, >, >=, = sur les nombres ; = et != sur les codes ;
« dans 1,2,3 » pour plusieurs codes ("Treatment_of_athsma dans 6,7,8" = biothérapie).

Réponds par un seul objet JSON, sans texte autour :
{"operation": "...", "colonne": "...", "codes": ["..."], "colonne_b": "...",
 "codes_b": ["..."], "cible": "...", "code_cible": "...", "filtre": "..."}
Omets les champs qui ne servent pas : une requête courte est une requête lue.

Règles : mets les codes sous forme de texte. Si la question ne correspond à
aucune opération, ou si elle demande une chose absente du fichier (famille
d'allergènes, seuil de positivité, recommandation, pronostic), réponds
{"operation": "inconnu"}.
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


def _filtrer(tableau, filtre):
    """Les patients qui vérifient le filtre. Aucun eval, aucun query : chaque condition est relue.

    « dans 1,2,3 » se traite ici et non dans _filtre.py, qui appartient à A : la
    condition est découpée en codes et comparée ensemble par ensemble, ce qui lit
    aussi les cellules à deux codes (« 1,3 ») que la comparaison numérique jetait.
    Le reste est passé au parseur d'A, sans le modifier.
    """
    if not filtre or not str(filtre).strip():
        return tableau
    simples = []
    for condition in filter(None, re.split(r"\s+et\s+", str(filtre).strip(), flags=re.IGNORECASE)):
        lue = re.fullmatch(r"\s*(\w+)\s+dans\s+(.+?)\s*", condition, re.IGNORECASE)
        if lue is None:
            simples.append(condition)
            continue
        nom, valeurs = lue.groups()
        colonne = colonne_connue(tableau, nom)
        voulus = {morceau for morceau in re.split(r"[,;/\s]+", valeurs) if morceau}
        porte = colonne.map(_codes).map(lambda portes: bool(portes & voulus))
        tableau = tableau[porte]
    if simples:
        tableau = appliquer(tableau, " et ".join(simples))
    return tableau


def _valider(requete, tableau):
    """Vérifie que la requête ne désigne que des choses qui existent. Rend None si non."""
    if not isinstance(requete, dict):
        return None
    operation = requete.get("operation")
    if operation not in OPERATIONS:
        return None

    # Un filtre se vérifie en l'appliquant : une colonne inconnue ou une
    # comparaison interdite fait escalader, elle ne produit pas une réponse fausse.
    filtre = requete.get("filtre")
    if filtre not in (None, ""):
        try:
            _filtrer(tableau, filtre)
        except (ValueError, TypeError, KeyError):
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
        if not isinstance(requete.get("codes"), list) or not requete["codes"]:
            return None
        if not isinstance(requete.get("codes_b"), list) or not requete["codes_b"]:
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
        # 700 et non 400 : le raisonnement interne du modèle mange la sortie, et à
        # 400 le JSON arrivait coupé, ce qui faisait escalader des questions traduisibles.
        max_tokens=700,
    )
    requete = _extraire_json(reponse.content)
    if not requete:
        return None
    return _valider(requete, _tableau())


def _tableau():
    from equipe import cache

    return cache.tableau()


MOIS = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}

# Un filtre se dit d'abord en français : « de sexe féminin » plutôt que « Gender=0 ».
# Seules les conditions dont la tournure est certaine sont traduites ; une
# condition inconnue fait rendre None, et la justification garde alors le filtre
# brut — du technique exact vaut mieux qu'un français approximatif.
PHRASES = {
    ("Gender", "0"): "de sexe féminin",
    ("Gender", "1"): "de sexe masculin",
    ("Rural_or_urban_area", "0"): "résidant en zone rurale",
    ("Rural_or_urban_area", "1"): "résidant en zone urbaine",
    ("Sensitization", "1"): "sensibilisés",
    ("Sensitization", "0"): "non sensibilisés",
    ("Skin_Symptoms", "1"): "présentant des symptômes cutanés",
    ("Skin_Symptoms", "0"): "sans symptôme cutané",
}

GROUPES = {
    ("Treatment_of_athsma", frozenset({"6", "7", "8"})): "sous biothérapie",
    ("Treatment_of_rhinitis", frozenset({"1", "2", "3", "4"})): "traités pour une rhinite",
}


def _phrase_age(conditions):
    """« âgés de 18 à 30 ans », « de plus de 60 ans », « âgés de 25 ans »."""
    basses = [(o, n) for o, n in conditions if o in (">=", ">")]
    hautes = [(o, n) for o, n in conditions if o in ("<=", "<")]
    exactes = [n for o, n in conditions if o == "="]
    if basses and hautes:
        (ob, nb), (oh, nh) = basses[0], hautes[0]
        debut = nb if ob == ">=" else nb + 1
        fin = nh if oh == "<=" else nh - 1
        return f"âgés de {debut} à {fin} ans"
    if basses:
        operateur, nombre = basses[0]
        return f"de plus de {nombre} ans" if operateur == ">" else f"âgés de {nombre} ans ou plus"
    if hautes:
        operateur, nombre = hautes[0]
        return f"de moins de {nombre} ans" if operateur == "<" else f"âgés de {nombre} ans ou moins"
    if exactes:
        return f"âgés de {exactes[0]} ans"
    return None


def filtre_en_francais(filtre):
    """Le filtre dit en français, ou None si une condition n'a pas de tournure connue."""
    conditions = [c.strip() for c in re.split(r"\s+et\s+", str(filtre or "").strip(), flags=re.IGNORECASE) if c.strip()]
    if not conditions:
        return None

    ages, autres = [], []
    for condition in conditions:
        dans = re.fullmatch(r"([A-Za-z_]+)\s+dans\s+([\d,\s]+)", condition, re.IGNORECASE)
        if dans:
            colonne = dans.group(1)
            codes = frozenset(c.strip() for c in dans.group(2).split(",") if c.strip())
            phrase = GROUPES.get((colonne, codes))
            if phrase is None:
                return None
            autres.append(phrase)
            continue

        simple = re.fullmatch(r"([A-Za-z_]+)\s*(>=|<=|!=|>|<|=)\s*([\w]+)", condition)
        if not simple:
            return None
        colonne, operateur, valeur = simple.group(1), simple.group(2), simple.group(3)

        if colonne == "Age" and operateur != "!=":
            try:
                ages.append((operateur, int(float(valeur))))
            except ValueError:
                return None
        elif colonne == "Blood_Month_sample" and operateur == "=":
            try:
                mois = MOIS.get(int(float(valeur)))
            except ValueError:
                return None
            if mois is None:
                return None
            autres.append(f"prélevés en {mois}")
        elif colonne == "Chip_Type" and operateur == "=":
            autres.append(f"sur la puce {valeur}")
        else:
            phrase = PHRASES.get((colonne, valeur)) if operateur in ("=", "==") else None
            if phrase is None:
                return None
            autres.append(phrase)

    if ages:
        phrase = _phrase_age(ages)
        if phrase is None:
            return None
        autres.insert(0, phrase)
    return ", ".join(autres) or None


def _lignes_du_groupe(tableau, colonne, codes_du_groupe):
    """Le masque des patients du groupe, non-renseignés exclus."""
    bruts = tableau[colonne].map(_texte)
    porte = tableau[colonne].map(_codes).map(lambda valeurs: bool(valeurs & set(map(str, codes_du_groupe))))
    return bruts.notna() & (bruts != NON_RENSEIGNE) & porte


def executer(requete, tableau):
    """La réponse à partir de la requête vérifiée. Aucun appel au modèle ici."""
    if requete.get("filtre"):
        tableau = _filtrer(tableau, requete["filtre"])
    operation = requete["operation"]

    if operation == "compter_lignes":
        total = len(tableau)
        if requete.get("filtre"):
            en_clair = filtre_en_francais(requete["filtre"])
            if en_clair:
                return _reponse(total, f"{total} patients réunissent ces conditions : {en_clair}.")
            return _reponse(total, f"{total} patients vérifient le filtre « {requete['filtre']} ».")
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
        gardees = compte.head(12)
        texte = " ; ".join(f"{nom} : {int(nombre)}" for nom, nombre in gardees.items())
        if len(compte) > len(gardees):
            texte += f" ; et {len(compte) - len(gardees)} autres valeurs"
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
        if n == 0:
            return None  # aucun patient renseigné : il n'y a pas de taux à calculer
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
        f"{part_a:.1f} % contre {part_b:.1f} %",
        f"Premier groupe : {premier[0]} sur {premier[1]} ({part_a:.1f} %) ; second groupe : "
        f"{second[0]} sur {second[1]} ({part_b:.1f} %). La définition de {cible} n'est pas donnée.",
    )


def _reponse(valeur, justification):
    return {"statut": "reponse", "valeur": valeur, "justification": justification}
