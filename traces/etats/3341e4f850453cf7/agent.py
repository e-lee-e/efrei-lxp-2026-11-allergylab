"""L'agent de l'équipe. Le kit n'en appelle qu'une fonction : repondre(question).

C'est un CodeAgent de smolagents : à chaque étape, le modèle écrit du code
Python, et ce code s'exécute sur ta machine. Avant de modifier ce fichier,
lis la rubrique « Ce qu'un agent ouvert peut faire » du README.

Ce que les traces ont montré, à relire avant de « simplifier » quoi que ce soit :
- 5 000 jetons d'entrée au premier appel, dont 1 249 de consigne (mesuré au
  tokenizer) ; chaque étape en coûte ~7 000 de plus, parce que tout le contexte
  est renvoyé à chaque fois ;
- un outil offert mais non utilisé coûte quand même sa description à chaque
  étape : le modèle réécrit du pandas par réflexe, la consigne doit le router ;
- le cache (equipe/cache.py) ramène à zéro le coût d'une question déjà posée.
"""

from pathlib import Path

from smolagents import CodeAgent

from kit import modele, reponse
from equipe import cache
from equipe.outils.positives import positifs
from equipe.outils.taux import taux_par_groupe

CONSIGNE = (Path(__file__).parent / "consigne.md").read_text(encoding="utf-8")


def repondre(question):
    # Question déjà posée, même consigne, même fichier : la réponse est relue
    # au lieu d'être recalculée. La trace dit d'où elle vient (moteur « cache »).
    gardee = cache.lire(question)
    if gardee is not None:
        modele.journal["moteur"] = "cache"
        modele.journal["modele"] = "cache"
        return gardee

    agent = CodeAgent(
        model=modele.ModeleKit(),  # le modèle de kit/reglages.toml
        tools=[taux_par_groupe, positifs],  # les outils de equipe/outils/, testés par pytest
        instructions=reponse.consigne(CONSIGNE),  # ta consigne, puis le format de réponse du kit
        max_steps=5,  # plafond maison : 8 étapes coûtent jusqu'à 0,008 $ (kit/reglages.toml ne se touche pas)
        max_print_outputs_length=modele.REGLAGES["agent"]["sortie_max"],
        step_callbacks=[modele.noter_etape],  # recopie chaque étape dans la trace
        # Accès aux données : le code écrit par le modèle peut importer pandas.
        additional_authorized_imports=["pandas"],
    )
    sortie = agent.run(
        question,
        # Accès aux données : le code écrit par le modèle reçoit le tableau complet, sous le nom tableau.
        additional_args={"tableau": cache.tableau()},
    )
    # On ne garde qu'une réponse qui respecte le contrat : une réponse
    # illisible doit être reproposée au modèle, pas resservie depuis le cache.
    try:
        validee = reponse.valider(sortie)
    except Exception:
        return sortie
    cache.ecrire(question, validee)
    return validee
