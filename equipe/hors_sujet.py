"""Le portier : une question qui ne parle pas du fichier s'arrête ici, à zéro dollar.

Deux conditions, cumulatives, pour ne jamais bloquer une vraie question :

1. la question ne contient aucun mot du domaine (patient, allergène, taux, âge,
   colonne, région, puce, seuil, dosage, rhinite, asthme, …) ;
2. elle contient un mot qui trahit un autre sujet (sport, people, météo, bourse,
   cuisine, code, culture générale, question sur l'agent lui-même).

La seconde condition évite le pire des deux défauts. Une question courte mais
légitime (« combien de patients ? ») contient un mot du domaine : elle passe. Une
question hors sujet mais sans mot étranger connu escalade vers le modèle, qui
saura s'abstenir — elle coûte 0,002 $, ce qui est le prix d'une incertitude, pas
d'une erreur.

Ce que ce portier ne fait jamais : juger du fond. Il ne dit pas qu'une question
est absurde, seulement qu'elle ne parle d'aucune des variables du fichier.
"""

import unicodedata

# Radicaux du domaine. Volontairement larges : mieux vaut laisser passer une
# question hors sujet que refuser une question d'analyse.
DOMAINE = (
    "tableau",
    "patient",
    "patiente",
    "allerg",
    "sensibilis",
    "ige",
    "dosage",
    "molecul",
    "molécul",
    "colonne",
    "ligne",
    "taux",
    "proportion",
    "pourcentage",
    "part des",
    "age",
    "âge",
    "annee",
    "année",
    "sexe",
    "gender",
    "femme",
    "homme",
    "region",
    "région",
    "puce",
    "isac",
    "alex",
    "seuil",
    "positif",
    "rhinite",
    "asthme",
    "dermatite",
    "traitement",
    "cofacteur",
    "anaphylaxie",
    "acarien",
    "pollen",
    "venin",
    "aliment",
    "effectif",
    "mediane",
    "médiane",
    "moyen",
    "repartition",
    "répartition",
    "correlation",
    "corrélation",
    "fichier",
    "jeu de donnees",
    "jeu de données",
    "variable",
    "chip",
    "ecart",
    "écart",
    "groupe",
    "cohorte",
)

# Ce qui trahit un autre sujet. Un seul suffit, à condition qu'aucun mot du
# domaine ne soit présent.
HORS_SUJET = (
    "lebron",
    "messi",
    "ronaldo",
    "mbappe",
    "mbappé",
    "football",
    "basket",
    "tennis",
    "rugby",
    "match",
    "championnat",
    "ballon",
    "meteo",
    "météo",
    "quel temps",
    "temps qu il fait",
    "il fait beau",
    "pleut",
    "temperature qu il fait",
    "president",
    "président",
    "election",
    "élection",
    "guerre",
    "capitale",
    "recette",
    "cuisine",
    "ingredient",
    "ingrédient",
    "python",
    "javascript",
    "serveur",
    "bitcoin",
    "bourse",
    "action en bourse",
    "film",
    "serie televisee",
    "série télévisée",
    "acteur",
    "chanson",
    "rappeur",
    "celebre",
    "célèbre",
    "qui est",
    "que peux tu faire",
    "que sais tu",
    "sais tu faire",
    "tes capacite",
    "ta capacite",
    "tes fonctionnalites",
    "comment tu fonctionnes",
    "tu fonctionnes",
    "tu sers",
    "tu fais quoi",
    "quoi tu fais",
    "ton role",
    "qui es tu",
    "ton nom",
    "algorithme",
    "complexite",
    "tri fusion",
    "ordinateur",
    "gaming",
    "planete",
    "systeme solaire",
    "tcp",
    "protocole",
    "reseau informatique",
    "carte graphique",
    "gpu",
    "processeur",
    "calorie",
    "riz",
    "joueur",
    "coupe du monde",
    "japon",
    "guilty gear",
    "pokemon",
    "pokémon",
    "franchise",
    "anime",
    "manga",
    "science fiction",
    "proteine",
    "protéine",
    "musculaire",
    "masse corporelle",
    "intelligence artificielle",
    "generation d images",
)

# Signaux forts : un seul suffit, même si un mot du domaine est présent. « Le
# meilleur traitement pour une carte graphique » contient « traitement », mais
# parle de matériel : deux conditions ne suffisent pas, il faut une exception.
FORT = (
    "carte graphique",
    "gpu",
    "ordinateur portable",
    "processeur",
    "tri fusion",
    "systeme solaire",
    "coupe du monde",
)


def _contient(question, mots):
    return any(mot in question for mot in mots)


def _normaliser(question):
    """Minuscules, sans accents, sans ponctuation : « peux-tu » devient « peux tu »."""
    decompose = unicodedata.normalize("NFKD", str(question).lower())
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    sans_ponctuation = "".join(c if c.isalnum() else " " for c in sans_accent)
    return " ".join(sans_ponctuation.split())


def examiner(question):
    """Une abstention motivée si la question est hors sujet, sinon None."""
    plat = _normaliser(question)
    if _contient(plat, FORT):
        return _refus()
    if _contient(plat, DOMAINE):
        return None
    if not _contient(plat, HORS_SUJET):
        return None
    return _refus()


def _refus():
    return {
        "statut": "abstention",
        "valeur": None,
        "justification": (
            "La question ne porte sur aucune variable du fichier Allergen Chip Challenge, "
            "ni sur un patient, ni sur un dosage. Je ne réponds que sur ce tableau."
        ),
    }
