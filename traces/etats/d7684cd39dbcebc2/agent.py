"""L'agent de l'équipe. Le kit n'en appelle qu'une fonction : repondre(question).

C'est un CodeAgent de smolagents : à chaque étape, le modèle écrit du code
Python, et ce code s'exécute sur ta machine. Avant de modifier ce fichier,
lis la rubrique « Ce qu'un agent ouvert peut faire » du README.
"""

from pathlib import Path

from smolagents import CodeAgent

from kit import modele, reponse
from kit.donnees import charger

CONSIGNE = (Path(__file__).parent / "consigne.md").read_text(encoding="utf-8")


def repondre(question):
    agent = CodeAgent(
        model=modele.ModeleKit(),  # le modèle de kit/reglages.toml
        tools=[],  # les outils de equipe/outils/, une fois écrits et testés
        instructions=reponse.consigne(CONSIGNE),  # ta consigne, puis le format de réponse du kit
        max_steps=modele.REGLAGES["agent"]["etapes_max"],
        max_print_outputs_length=modele.REGLAGES["agent"]["sortie_max"],
        step_callbacks=[modele.noter_etape],  # recopie chaque étape dans la trace
        # Accès aux données : le code écrit par le modèle peut importer pandas.
        additional_authorized_imports=["pandas"],
    )
    return agent.run(
        question,
        # Accès aux données : le code écrit par le modèle reçoit le tableau complet, sous le nom tableau.
        additional_args={"tableau": charger()},
    )
