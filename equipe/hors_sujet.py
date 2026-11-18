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


# Le fichier nomme 241 molécules sans dire à quel aliment elles correspondent :
# « Ara_h_1 » n'y est pas « arachide ». Une question posée en aliments ne peut donc
# pas être répondue honnêtement, et le modèle, lui, croit le savoir — mesuré sur
# D06 : un tableau de scores inventés pour 0,009 $ et 36 s, molécules « anacarde »
# et « arachide » comprises. Sauf si la question nomme une molécule : là, le
# fichier répond.
# Comparés mot entier, jamais en sous-chaîne : « ble » dans « tableau » refusait
# une question légitime (« combien de patients compte le tableau ? »).
ALIMENTS = (
    "arachide", "arachides", "cajou", "anacarde", "noisette", "noisettes", "noix", "amande",
    "lait", "oeuf", "oeufs", "œuf", "œufs", "ble", "soja", "poisson", "crevette", "crevettes",
    "moutarde", "sesame", "kiwi", "alimentaire", "alimentaires", "aliment", "aliments",
)
MOLECULE = ("ara_", "bet_", "act_", "ana_", "ory_", "profiline", "lpt", "pr-10")
# Ce qui trahit une demande de correspondance, et non un simple comptage : le
# fichier du kit nomme des molécules sans dire à quel aliment elles correspondent.
# Mesuré : « combien de patients déclarent une allergie alimentaire ? » était
# refusée sur une table qui contient la colonne — une abstention à tort.
MAPPING = ("molecule", "molécule", "famille", "proteine", "protéine", "allergene", "allergène")


def examiner(question):
    """Une abstention motivée si la question est hors sujet, sinon None."""
    plat = _normaliser(question)
    mots = set(plat.split())
    demande_mapping = any(mot in plat for mot in MAPPING)
    if (demande_mapping and any(mot in mots for mot in ALIMENTS)
            and not any(mot in plat for mot in MOLECULE)):
        return _refus_aliment()
    if _contient(plat, FORT):
        return _refus()
    if _contient(plat, DOMAINE):
        return None
    if not _contient(plat, HORS_SUJET):
        return None
    return _refus()


def _refus_aliment():
    """L'abstention propre aux questions posées en aliments, pas en molécules."""
    return {
        "statut": "abstention",
        "valeur": None,
        "justification": (
            "Le fichier nomme les molécules (Ara_h_1, Bet_v_1…) mais ne dit pas à quel aliment "
            "ou à quelle famille chacune correspond : une question posée en aliments ne peut pas "
            "être tranchée sur ce tableau."
        ),
    }


def _refus():
    return {
        "statut": "abstention",
        "valeur": None,
        "justification": (
            "La question ne porte sur aucune variable du fichier Allergen Chip Challenge, "
            "ni sur un patient, ni sur un dosage. Je ne réponds que sur ce tableau."
        ),
    }
