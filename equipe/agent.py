"""L'agent de l'équipe. Le kit n'en appelle qu'une fonction : repondre(question).

Autour du modèle, trois couches s'essaient d'abord, dans cet ordre : le portier
hors sujet, le routeur (qui calculent sans modèle), puis le cache des réponses de
l'agent complet. Ce qui n'est pas reconnu passe au traducteur (une requête canonique, dix fois moins chère qu'une analyse) et, en
dernier recours, à l'agent complet. Aucun modèle local : le reformulateur a été
mesuré puis retiré, voir plus bas.

Trois variantes de l'agent, pour les comparer sur les mêmes questions (jetons,
coût, durée, justesse) :

    "ouvert"  CodeAgent. Le modèle écrit du code qui voit le tableau et peut
              importer pandas ; les outils ne sont qu'une option pour lui.
    "ferme"   CodeAgent sans accès au tableau : il n'atteint les données que
              par les outils. Ce n'est pas un bac à sable.
    "outils"  ToolCallingAgent : n'exécute aucun code, n'appelle que les outils.

On change de variante par ALLERGYLAB_VARIANTE et de plafond d'étapes par
ALLERGYLAB_ETAPES_MAX : la copie de ce fichier gardée dans traces/etats/ dit
alors laquelle tournait. ALLERGYLAB_RACCOURCIS=0 coupe les couches locales,
pour mesurer l'agent seul.

Ce que les traces ont montré, à relire avant de « simplifier » quoi que ce soit :
- 5 000 jetons d'entrée au premier appel, dont la consigne (mesurée au
  tokenizer) ; chaque étape en coûte ~7 000 de plus, tout le contexte étant
  renvoyé à chaque fois ;
- un outil offert mais non utilisé coûte quand même sa description à chaque
  étape : le modèle réécrit du pandas par réflexe, la consigne doit le router ;
- le cache (equipe/cache.py) ramène à zéro le coût d'une question déjà posée, mais
  une réponse fausse gardée est resservie : il ne garde que les réponses de l'agent
  complet, jamais une abstention, et sa clé suit le code (voir cache.py).

Avant de modifier ce fichier, lis la rubrique « Ce qu'un agent ouvert peut
faire » du README.
"""

import os
import time
from pathlib import Path

from smolagents import CodeAgent, ToolCallingAgent

from kit import modele, reponse

from equipe import reglages, cache, dictionnaire, hors_sujet, routeur, suivi, traducteur
from equipe.outils.calculer import calculer
from equipe.outils.chercher_colonne import chercher_colonne

CONSIGNE = (Path(__file__).parent / "consigne.md").read_text(encoding="utf-8")

# Ajouté à la consigne de l'équipe, sans la modifier : comment se servir des outils.
NOTE_OUTILS = """

Outils : pour tout calcul sur les patients, utilise calculer. Les colonnes cliniques sont nommées dans la consigne : ne cherche pas leur nom. N'appelle chercher_colonne que pour une molécule ou un nom dont tu doutes, dans le même bloc de code que calculer (une étape de moins, ~7 000 jetons). Ne refais pas à la main un calcul que calculer sait faire.
calculer lit seul les cellules à plusieurs codes (« 1,3 ») et écarte le code 9 (sauf avec !=, qui n'exclut que la valeur nommée).
Si calculer répond « ABSTENTION », reprends sa raison dans la justification et rends le statut "abstention" sans valeur."""

VARIANTE = os.environ.get("ALLERGYLAB_VARIANTE", "ouvert")  # "ouvert", "ferme" ou "outils"

# Cinq étapes et non les huit du kit : mesuré, une course à huit étapes coûte
# jusqu'à 0,008 $, et la question de l'âge a consommé quatre étapes pile.
ETAPES_MAX = int(os.environ.get("ALLERGYLAB_ETAPES_MAX", "5"))
# Une question qui n'a pas fini dans ce temps ne sert plus à rien : la médiane
# mesurée est de 8,6 s, et au-delà d'une demi-minute le chercheur est parti.
DELAI_MAX = float(os.environ.get("ALLERGYLAB_DELAI_MAX", "35"))


def _abstention(message, cause=None):
    """Une abstention motivée, avec sa cause notée à part.

    La cause ne peut pas voyager dans la réponse : le contrat du kit veut
    exactement trois champs, et un quatrième fait rejeter la réponse. Elle va donc
    dans le journal, que la fenêtre lit pour proposer l'action juste — enregistrer
    la clé, choisir un autre fichier, ou relancer.
    """
    if cause:
        modele.journal["cause"] = cause
    return {"statut": "abstention", "valeur": None, "justification": message}

# Deux outils, pas cinq : chaque description est repayée à chaque étape (1 127
# caractères pour cinq outils). Les taux par groupe, par présence de codes et les
# positifs au-dessus d'un seuil sont des cas de `calculer` (voir outils/calculer.py).
OUTILS = [calculer, chercher_colonne]

def raccourcis():
    """Les couches gratuites peuvent être coupées, pour mesurer l'agent seul."""
    return os.environ.get("ALLERGYLAB_RACCOURCIS", "1") != "0"


SORTIE_MAX = int(os.environ.get("ALLERGYLAB_SORTIE_MAX", "2000"))


class DelaiDepasse(RuntimeError):
    """La question n'a pas abouti dans DELAI_MAX secondes."""


def modele_du_jour():
    """Haiku 5.5, avec un plafond de sortie dur par étape.

    Sans ce plafond, une question de recommandation a fait boucler le modèle
    jusqu'à 128 000 jetons de sortie en UNE étape : 0,064 $ et six minutes
    d'attente pour rien. Le plafond borne le pire cas d'une étape à 2 000
    jetons, soit 0,001 $, et cinq étapes à 0,005 $.

    La classe est créée ici, et non au niveau du module, pour qu'un test qui
    remplace modele.ModeleKit remplace aussi la classe de base.
    """

    # On ne touche pas à modele.en_cours ici : `kit evaluer --modele officiel` le
    # bascule pour toute la batterie, et le réécrire ferait tourner la passe
    # officielle sur le modèle de développement.
    base = modele.ModeleKit()
    generate = base.generate
    debut = time.monotonic()

    def bride(messages, **options):
        # Le temps se compte par question, pas par étape : cinq étapes de 7 s
        # doivent s'arrêter à 35 s comme une seule de 35 s.
        reste = DELAI_MAX - (time.monotonic() - debut)
        if reste <= 0.5:
            raise DelaiDepasse(f"plus de {DELAI_MAX:.0f} s")
        voulu = options.get("max_tokens") or SORTIE_MAX
        options["max_tokens"] = min(int(voulu), SORTIE_MAX)
        # Passé à l'appel : une requête bloquée côté API ne peut pas manger le budget.
        options["timeout"] = min(float(options.get("timeout") or reste), max(reste, 1.0))
        return generate(messages, **options)

    base.generate = bride  # l'instance, pas la classe : un test peut remplacer ModeleKit par un faux
    return base


def noter_appels(etape):
    """Pour le ToolCallingAgent, qui n'écrit pas de code : recopie l'outil appelé et son résultat."""
    appels = ", ".join(f"{appel.name}({appel.arguments})" for appel in etape.tool_calls or [])
    resultat = f"Erreur : {etape.error}" if etape.error is not None else etape.observations
    modele.ajouter_etape(appels, resultat)


def construire(variante):
    """L'agent de la variante demandée, prêt à répondre."""
    options = dict(
        model=modele_du_jour(),  # Haiku 5.5, le modèle de développement du kit
        tools=OUTILS,
        instructions=reponse.consigne(CONSIGNE + _dictionnaire()[1] + NOTE_OUTILS),
        max_steps=ETAPES_MAX,
    )
    if variante == "outils":
        return ToolCallingAgent(step_callbacks=[noter_appels], **options)
    options.update(
        max_print_outputs_length=modele.REGLAGES["agent"]["sortie_max"],
        step_callbacks=[modele.noter_etape],  # recopie chaque étape dans la trace
    )
    if variante == "ouvert":
        # Accès aux données (1/2) : le code écrit par le modèle peut importer pandas.
        options["additional_authorized_imports"] = ["pandas"]
    return CodeAgent(**options)


def _relire(sortie):
    """Retrouve le dictionnaire du contrat dans une réponse qui l'a habillé.

    Rend None si la réponse ne contient aucun dictionnaire valide : dans ce cas
    seule la vérité brute du modèle est rendue, et elle reste illisible — on ne
    fabrique pas une abstention pour faire passer une réponse hors contrat.
    """
    if isinstance(sortie, dict):
        return None  # déjà un dictionnaire : s'il est refusé, c'est pour une autre raison
    texte = sortie if isinstance(sortie, str) else str(sortie)
    morceau = _essayer(traducteur._extraire_json, texte)
    if not isinstance(morceau, dict):
        return None
    essai = _essayer(reponse.valider, morceau)
    return essai if isinstance(essai, dict) else None


def _essayer(fonction, *arguments):
    """Un raccourci qui échoue se tait : la question continue vers le modèle.

    Une erreur dans le portier, le routeur ou le traducteur ne doit pas faire
    tomber la question — le modèle, lui, voit le tableau et saura quoi dire.
    DonneeIllisible remonte, elle : là, il n'y a rien à demander à personne.
    """
    try:
        return fonction(*arguments)
    except cache.DonneeIllisible:
        raise
    except Exception:
        return None


_DICO = {"lu": None, "de": None, "bloc": ""}


def _dictionnaire():
    """Le dictionnaire du fichier actif, lu une fois par processus.

    Rien n'est codé en dur : c'est le fichier de l'utilisateur qui fait foi, et un
    dictionnaire absent rend un dictionnaire vide, pas une erreur.
    """
    chemin = reglages.dictionnaire()
    if not chemin:
        return {}, ""
    if _DICO["de"] != chemin:
        try:
            table = dictionnaire.lire(chemin)
        except ValueError:
            table = {}
        colonnes = list(cache.tableau().columns)
        _DICO.update(lu=table, de=chemin, bloc=dictionnaire.bloc(table, colonnes))
    return _DICO["lu"], _DICO["bloc"]


def repondre(question, precedente=None):
    """La réponse, ou une abstention motivée. Ne lève jamais pour une question.

    `precedente` sert aux questions de suivi (« et de femmes ? ») : la question est
    reconstruite localement, gratuitement, à partir de la précédente. Sans elle, un
    suivi ne se tient pas debout et le modèle répond à côté — mesuré.
    """
    if VARIANTE not in ("ouvert", "ferme", "outils"):
        raise ValueError(
            f'VARIANTE vaut « {VARIANTE} » ; elle doit valoir "ouvert", "ferme" ou "outils" (equipe/agent.py).'
        )
    question = str(question or "").strip()
    if suivi.est_suivi(question):
        entiere = suivi.resoudre(question, precedente)
        if not entiere:
            return _abstention(
                "Cette question de suivi ne se comprend pas seule : écris-la en entier, "
                "par exemple « combien de femmes compte le tableau ? ».",
                cause="suivi",
            )
        modele.journal["question_resolue"] = entiere
        question = entiere
    try:
        return _repondre(question)
    except cache.DonneeIllisible as souci:
        modele.journal["moteur"] = "donnees-illisibles"
        return _abstention(
            f"Le fichier de données ne se lit pas : {souci}. Aucun chiffre n'est donné plutôt qu'un chiffre faux.",
            cause="donnees",
        )
    except Exception as souci:  # panne d'API, colonne inattendue, outil cassé
        nom = type(souci).__name__
        if nom in ("CleAbsente", "CleRefusee"):
            modele.journal["moteur"] = "cle"
            return _abstention(
                "Aucune clé d'API utilisable : enregistre-la pour que le modèle puisse répondre. "
                "Rien n'a été facturé.",
                cause="cle",
            )
        modele.journal["moteur"] = "erreur"
        return _abstention(
            f"Le calcul a échoué ({nom} : {str(souci)[:140]}). "
            "Aucun chiffre n'est donné plutôt qu'un chiffre faux.",
            cause="panne",
        )


def _contexte():
    """Ce qui change la réponse de l'agent complet sans changer la question : entre dans la clé du cache."""
    return f"{VARIANTE}|{ETAPES_MAX}|{SORTIE_MAX}"


def _repondre(question):
    if raccourcis():
        # Question hors sujet : aucune variable du fichier n'y figure, un autre sujet
        # y est nommé. Abstention locale, zéro jeton, et la question n'entre pas dans
        # le cache (elle ne dépend d'aucune donnée).
        refus = _essayer(hors_sujet.examiner, question)
        if refus is not None:
            modele.journal["moteur"] = "hors-sujet"
            modele.journal["modele"] = "local"
            return refus

        # Question reconnaissable : la réponse est calculée ici, sans modèle, zéro jeton.
        locale = _essayer(routeur.router, question)
        if locale is not None:
            modele.journal["moteur"] = "routeur"
            modele.journal["modele"] = "local"
            return locale

        # Le cache vient APRÈS les deux couches qui calculent sans modèle : une
        # réponse du modèle gardée par le passé ne doit jamais l'emporter sur elles.
        # Il ne garde que les réponses de l'agent complet (voir equipe/cache.py), et
        # sa clé suit le code, la variante et le plafond d'étapes, pas seulement la
        # question. Une réponse relue est donc une réponse que ce code aurait pu donner.
        gardee = cache.lire(question, _contexte())
        if gardee is not None:
            modele.journal["moteur"] = "cache"
            modele.journal["modele"] = "cache"
            return gardee

        # Un reformulateur local (qwen3:0.6b) a été essayé ici puis retiré : 0 question
        # gagnée sur 40, pour 522 Mo et 12 s de délai (voir equipe/NOTES.md).

        # Traduction en requête canonique : le modèle ne calcule rien, il choisit une
        # opération et ses paramètres dans une liste fermée ; le code exécute. Dix fois
        # moins cher qu'une analyse complète, et le calcul est déterministe.
        requete = _essayer(traducteur.traduire, question, None, _dictionnaire()[0])
        if requete is not None:
            calculee = _essayer(traducteur.executer, requete, cache.tableau())
            if calculee is not None:
                modele.journal["moteur"] = "traducteur"
                return calculee

    arguments = {}
    if VARIANTE == "ouvert":
        # Accès aux données (2/2) : le code écrit par le modèle reçoit le tableau,
        # et c'est celui de cache.tableau() — pas charger() seul, qui ignore le
        # fichier choisi dans la fenêtre. Une COPIE : le tableau du cache vit aussi longtemps que la
        # fenêtre, et un code du modèle qui le modifie en place (drop, colonne ajoutée) fausserait
        # toutes les questions suivantes, outils compris. Mesuré : sur une table inventée sans la
        # colonne Sensitization, l'agent répondait 80,9 %, les chiffres du vrai
        # fichier, sans que rien ne le signale.
        arguments["tableau"] = cache.tableau().copy()
    try:
        sortie = construire(VARIANTE).run(question, additional_args=arguments or None)
    except DelaiDepasse:
        modele.journal["moteur"] = "delai"
        return _abstention(
            f"Le calcul n'a pas abouti dans le délai de {DELAI_MAX:.0f} secondes.",
            cause="delai",
        )
    # On ne garde qu'une réponse qui respecte le contrat : une réponse
    # illisible doit être reproposée au modèle, pas resservie depuis le cache.
    try:
        validee = reponse.valider(sortie)
    except Exception:
        # Le modèle écrit parfois son dictionnaire entouré de prose, ou une liste.
        # On retente l'extraction avant de déclarer la réponse illisible — c'est
        # gratuit, puisque la réponse est déjà là. Mesuré : D06 rendait un tableau
        # en markdown pour 0,009 $ et 36 s, et comptait comme illisible.
        validee = _relire(sortie)
        if validee is None:
            return sortie
    cache.ecrire(question, validee, _contexte())
    return validee
