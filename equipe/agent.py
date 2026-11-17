"""L'agent de l'équipe. Le kit n'en appelle qu'une fonction : repondre(question).

Autour du modèle, trois couches gratuites s'essaient d'abord, dans cet ordre :
le cache, le portier hors sujet, puis le routeur. Ce qui n'est pas reconnu passe
au traducteur (une requête canonique, dix fois moins chère qu'une analyse) et, en
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
- le cache (equipe/cache.py) ramène à zéro le coût d'une question déjà posée.

Avant de modifier ce fichier, lis la rubrique « Ce qu'un agent ouvert peut
faire » du README.
"""

import os
import time
from pathlib import Path

from smolagents import CodeAgent, ToolCallingAgent

from kit import modele, reponse
from kit.donnees import charger

from equipe import cache, hors_sujet, routeur, traducteur
from equipe.outils.calculer import calculer
from equipe.outils.chercher_colonne import chercher_colonne
from equipe.outils.positives import positifs
from equipe.outils.taux import taux_par_groupe, taux_par_presence

CONSIGNE = (Path(__file__).parent / "consigne.md").read_text(encoding="utf-8")

# Ajouté à la consigne de l'équipe, sans la modifier : comment se servir des outils.
NOTE_OUTILS = """

Outils : pour tout calcul sur les patients, cherche le nom exact de la colonne avec chercher_colonne, puis calcule avec calculer. Ne refais pas à la main un calcul que calculer sait faire.
Si calculer répond « ABSTENTION », reprends sa raison dans la justification et rends le statut "abstention" sans valeur."""

VARIANTE = os.environ.get("ALLERGYLAB_VARIANTE", "ouvert")  # "ouvert", "ferme" ou "outils"

# Cinq étapes et non les huit du kit : mesuré, une course à huit étapes coûte
# jusqu'à 0,008 $, et la question de l'âge a consommé quatre étapes pile.
ETAPES_MAX = int(os.environ.get("ALLERGYLAB_ETAPES_MAX", "5"))
# Une question qui n'a pas fini dans ce temps ne sert plus à rien : la médiane
# mesurée est de 8,6 s, et au-delà d'une demi-minute le chercheur est parti.
DELAI_MAX = float(os.environ.get("ALLERGYLAB_DELAI_MAX", "35"))

# Les outils de l'équipe : ceux du camarade (calculer, chercher_colonne) et les nôtres.
OUTILS = [calculer, chercher_colonne, taux_par_groupe, taux_par_presence, positifs]

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
        model=modele_du_jour(),  # Haiku, ou qwen3:8b local avec ALLERGYLAB_MODELE=local
        tools=OUTILS,
        instructions=reponse.consigne(CONSIGNE + NOTE_OUTILS),  # la consigne, puis le format du kit
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


def repondre(question):
    if VARIANTE not in ("ouvert", "ferme", "outils"):
        raise ValueError(
            f'VARIANTE vaut « {VARIANTE} » ; elle doit valoir "ouvert", "ferme" ou "outils" (equipe/agent.py).'
        )

    if raccourcis():
        # Question déjà posée, même consigne, même fichier : la réponse est relue
        # au lieu d'être recalculée. La trace dit d'où elle vient (moteur « cache »).
        gardee = cache.lire(question)
        if gardee is not None:
            modele.journal["moteur"] = "cache"
            modele.journal["modele"] = "cache"
            return gardee

        # Question hors sujet : aucune variable du fichier n'y figure, un autre sujet
        # y est nommé. Abstention locale, zéro jeton, et la question n'entre pas dans
        # le cache (elle ne dépend d'aucune donnée).
        refus = hors_sujet.examiner(question)
        if refus is not None:
            modele.journal["moteur"] = "hors-sujet"
            modele.journal["modele"] = "local"
            return refus

        # Question reconnaissable : la réponse est calculée ici, sans modèle, zéro jeton.
        locale = routeur.router(question)
        if locale is not None:
            modele.journal["moteur"] = "routeur"
            modele.journal["modele"] = "local"
            return locale

        # Il y avait ici un reformulateur local (qwen3:0.6b, 522 Mo) : un petit modèle
        # réécrivait la question dans une forme connue du routeur. Mesuré sur la
        # batterie extérieure de quarante questions, il n'en a fait router aucune de
        # plus que le normaliseur seul (0 sur 40), pour 522 Mo, douze secondes de
        # délai au pire et une dépendance à Ollama. Retiré. equipe/reformulateur.py
        # reste, avec sa mesure, pour qui voudra refaire l'essai sur d'autres questions.

        # Traduction en requête canonique : le modèle ne calcule rien, il choisit une
        # opération et ses paramètres dans une liste fermée ; le code exécute. Dix fois
        # moins cher qu'une analyse complète, et le calcul est déterministe.
        requete = traducteur.traduire(question)
        if requete is not None:
            calculee = traducteur.executer(requete, cache.tableau())
            if calculee is not None:
                modele.journal["moteur"] = "traducteur"
                return calculee

    arguments = {}
    if VARIANTE == "ouvert":
        # Accès aux données (2/2) : le code écrit par le modèle reçoit le tableau complet, sous le nom tableau.
        arguments["tableau"] = charger()
    try:
        sortie = construire(VARIANTE).run(question, additional_args=arguments or None)
    except DelaiDepasse:
        modele.journal["moteur"] = "delai"
        return {
            "statut": "abstention",
            "valeur": None,
            "justification": f"Le calcul n'a pas abouti dans le délai de {DELAI_MAX:.0f} secondes.",
        }
    # On ne garde qu'une réponse qui respecte le contrat : une réponse
    # illisible doit être reproposée au modèle, pas resservie depuis le cache.
    try:
        validee = reponse.valider(sortie)
    except Exception:
        return sortie
    cache.ecrire(question, validee)
    return validee
