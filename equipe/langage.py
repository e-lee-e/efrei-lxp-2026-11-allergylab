"""Corriger une question mal tapée avant de la router.

Les routes reconnaissent des formulations ; un mot écorché les fait toutes
échouer. Plutôt que d'écrire une variante de motif par faute de frappe — ce qui
ne finit jamais — on corrige les mots contre un vocabulaire fermé, puis on
route la phrase corrigée.

Trois garde-fous, parce qu'une correction fautive coûte une réponse fausse :

- le vocabulaire est fermé : un mot absent n'est corrigé que vers un mot connu,
  jamais inventé ;
- la ressemblance doit être forte (0,75 et au moins quatre lettres communes) ;
  en dessous, le mot reste tel quel et la question escalade ;
- les mots très courts passent intacts, sauf s'ils ressemblent à un mot du
  vocabulaire : « son » devient « sont », mais « de » ne devient rien.

Aucune dépendance : difflib est dans la bibliothèque standard, et ce module ne
parle ni au modèle ni au réseau.
"""

import difflib

# Tout ce dont les routes ont besoin pour comprendre une phrase. Volontairement
# plat et sans accents : la question est déjà passée par routeur._plat.
VOCABULAIRE = (
    # Mots de liaison et de question
    "de", "des", "du", "le", "la", "les", "un", "une", "dans", "ce", "cet", "cette",
    "sont", "est", "elles", "ils", "elle", "il", "que", "qui", "quel", "quelle",    "quels", "quelles", "combien", "y", "a", "t", "plus", "moins", "souvent", "autres",
    "reste", "tous", "tout", "leur", "chez", "parmi", "avec", "sans", "pour", "par",
    "en", "au", "aux", "et", "ou", "mon", "ton", "beaucoup", "aucun",
    # Le tableau et ses variables
    "patient", "patients", "patiente", "patientes", "femme", "femmes", "homme", "hommes",
    "rural", "rurale", "rurales", "ruraux", "ville", "villes", "urbain", "urbaine",
    "urbains", "urbaines", "campagne", "age", "ans", "median", "mediane", "moyen",
    "moyenne", "ligne", "lignes", "tableau", "fichier", "dataset", "jeu", "donnees",
    "repartition", "puce", "puces", "test", "isac", "alex", "seuil", "positif",
    "positifs", "positive", "positives", "molecule", "molecules", "sensibilise",
    "sensibilisee", "sensibilisees", "sensibilises", "sensibilisation", "taux",
    "proportion", "pourcentage", "part", "region", "francaise", "representee",
    "represente", "traitement", "traite", "traites", "traitee", "traitees", "rhinite",
    "biotherapie", "cutane", "cutanes", "symptome", "symptomes", "urticaire", "asthme",
    "cofacteur", "cofacteurs", "frequent", "frequente", "effectif", "nombre", "groupe",
    "groupes", "different", "difference", "ecart", "persiste", "tranche", "sexe",
)


# Les fautes de frappe courantes ne se devinent pas par ressemblance (« dent »
# n'est pas proche de « dans »). Une petite table phonétique les couvre, bornée
# volontairement aux mots outils : on ne corrige jamais un nom de variable.
TYPO = {
    "dent": "dans", "ds": "dans", "dnas": "dans", "dan": "dans", "dens": "dans",
    "ke": "que", "kes": "que", "kel": "quel", "kelle": "quelle", "koi": "quoi", "ki": "qui",
    "bcp": "beaucoup", "pcq": "parce", "pck": "parce", "ske": "ce", "chui": "je", "jsuis": "je",
    "ya": "y a", "commen": "combien", "kombien": "combien", "comb1": "combien",
}


def _proche(mot):
    """Le mot du vocabulaire qui ressemble le plus, ou None si rien ne ressemble assez."""
    if len(mot) < 3:
        return None
    candidats = difflib.get_close_matches(mot, VOCABULAIRE, n=1, cutoff=0.75)
    if not candidats:
        return None
    candidat = candidats[0]
    # Quatre lettres communes au moins : sans ça, « ans » et « as » se confondent.
    communs = sum(1 for lettre in set(mot) if lettre in candidat)
    return candidat if communs >= 4 or len(mot) <= 4 else None


def corriger(question):
    """La question avec ses mots mal tapés ramenés vers le vocabulaire du domaine."""
    corriges = []
    for mot in question.split():
        mot = TYPO.get(mot, mot)
        if mot in VOCABULAIRE:  # un mot correct ne se « corrige » pas vers un voisin
            corriges.append(mot)
        else:
            corriges.append(_proche(mot) or mot)
    return " ".join(corriges)
