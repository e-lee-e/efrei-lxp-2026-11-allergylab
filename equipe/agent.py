"""L'agent de l'équipe. Le kit n'en appelle qu'une fonction : repondre(question).

Trois variantes, pour les comparer sur les mêmes questions (jetons, coût,
durée, justesse). On change de variante en modifiant VARIANTE ci-dessous :
la copie de ce fichier gardée dans traces/etats/ dit alors laquelle tournait.

    "ouvert"  CodeAgent. Le modèle écrit du code qui voit le tableau et peut
              importer pandas ; les outils ne sont qu'une option pour lui.
    "ferme"   CodeAgent sans accès au tableau : il n'atteint les données que
              par les outils. Ce n'est pas un bac à sable.
    "outils"  ToolCallingAgent : n'exécute aucun code, n'appelle que les outils.

Avant de modifier ce fichier, lis la rubrique « Ce qu'un agent ouvert peut
faire » du README.
"""

from pathlib import Path

from smolagents import CodeAgent, ToolCallingAgent

from equipe.outils.calculer import calculer
from equipe.outils.chercher_colonne import chercher_colonne
from kit import modele, reponse
from kit.donnees import charger

VARIANTE = "ouvert"  # "ouvert", "ferme" ou "outils"

# Les outils de l'équipe. Vide ([]) : l'agent tel que le kit le livrait, pour
# mesurer ce que les outils apportent.
OUTILS = [calculer, chercher_colonne]

CONSIGNE = (Path(__file__).parent / "consigne.md").read_text(encoding="utf-8")

# Ajouté à la consigne de B, sans la modifier : comment se servir des outils.
NOTE_OUTILS = """

Outils : pour tout calcul sur les patients, cherche le nom exact de la colonne avec chercher_colonne, puis calcule avec calculer. Ne refais pas à la main un calcul que calculer sait faire.
Si calculer répond « ABSTENTION », reprends sa raison dans la justification et rends le statut "abstention" sans valeur."""


def noter_appels(etape):
    """Pour le ToolCallingAgent, qui n'écrit pas de code : recopie dans la trace l'outil appelé et son résultat."""
    appels = ", ".join(f"{appel.name}({appel.arguments})" for appel in etape.tool_calls or [])
    resultat = f"Erreur : {etape.error}" if etape.error is not None else etape.observations
    modele.ajouter_etape(appels, resultat)


def construire(variante):
    """L'agent de la variante demandée, prêt à répondre."""
    options = dict(
        model=modele.ModeleKit(),  # le modèle de kit/reglages.toml
        tools=OUTILS,
        instructions=reponse.consigne(CONSIGNE + NOTE_OUTILS),  # la consigne de B, puis le format de réponse du kit
        max_steps=modele.REGLAGES["agent"]["etapes_max"],
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
        raise ValueError(f'VARIANTE vaut « {VARIANTE} » ; elle doit valoir "ouvert", "ferme" ou "outils" (equipe/agent.py).')
    arguments = {}
    if VARIANTE == "ouvert":
        # Accès aux données (2/2) : le code écrit par le modèle reçoit le tableau complet, sous le nom tableau.
        arguments["tableau"] = charger()
    return construire(VARIANTE).run(question, additional_args=arguments or None)
