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

import os
from pathlib import Path

from smolagents import CodeAgent

from kit import modele, reponse
from equipe import cache, hors_sujet, routeur
from equipe.outils.positives import positifs
from equipe.outils.taux import taux_par_groupe, taux_par_presence

CONSIGNE = (Path(__file__).parent / "consigne.md").read_text(encoding="utf-8")


def modele_du_jour():
    """Haiku 5.5 par défaut ; qwen3:8b sur Ollama si ALLERGYLAB_MODELE=local, pour itérer à 0 $."""
    if os.environ.get("ALLERGYLAB_MODELE", "").strip().lower() != "local":
        return modele.ModeleKit()

    from equipe.modele_local import ModeleLocal, disponible

    if disponible() is None:
        raise modele.ErreurModele(
            "le serveur Ollama ne répond pas sur 127.0.0.1:11434.",
            "lance ~/cally/Ai/outils/ollama/bin/ollama serve, ou retire ALLERGYLAB_MODELE pour repasser sur Haiku.",
        )
    return ModeleLocal()


def repondre(question):
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

    agent = CodeAgent(
        model=modele_du_jour(),  # Haiku, ou qwen3:8b local avec ALLERGYLAB_MODELE=local
        tools=[taux_par_groupe, taux_par_presence, positifs],  # les outils de equipe/outils/, testés par pytest
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
