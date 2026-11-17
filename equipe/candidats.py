"""Les questions qui coûtent encore un appel, par fréquence : la file des routes.

Le routeur ne s'étend pas tout seul, exprès : une route qui se trompe répond à
0 $ avec aplomb, et une réponse fausse coûte plus cher qu'un appel à 0,002 $.
Ce script ne route rien et n'appelle personne : il lit les traces, écarte ce que
le routeur traite déjà, et groupe les variantes d'une même question.

Une question qui revient trois fois est une route à écrire ; une question qui
revient une fois n'est qu'une question.

Usage : uv run python -m equipe.candidats [nombre]
"""

import glob
import json
import sys
from collections import Counter

from equipe import cache, routeur


def candidats(nombre=15):
    """Les questions encore payantes : nombre de lancers, coût cumulé, et un exemple lisible."""
    tableau = cache.tableau()
    lancements, couts, exemples = Counter(), Counter(), {}

    for chemin in glob.glob("traces/appels/*/*.json"):
        with open(chemin, encoding="utf-8") as fichier:
            trace = json.load(fichier)
        if trace.get("moteur") == "routeur":
            continue
        question = " ".join(str(trace.get("question", "")).split())
        if routeur.router(question, tableau) is not None:
            continue  # le routeur sait déjà la traiter : plus rien à gagner
        # La clé sans accents ni casse regroupe « quel est l age median » et sa
        # version accentuée, qui sont la même question posée deux fois.
        cle = cache.normaliser(question)
        lancements[cle] += 1
        couts[cle] += trace.get("cout_estime") or 0
        if len(question) > len(exemples.get(cle, "")):
            exemples[cle] = question

    return [
        (exemples[cle], nombre_de_lancers, couts[cle])
        for cle, nombre_de_lancers in lancements.most_common(nombre)
    ]


def main():
    nombre = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    lignes = candidats(nombre)
    if not lignes:
        print("aucune question payante dans les traces.")
        return
    print(f"{'lancers':>7}  {'coût cumulé':>11}  question")
    for question, lancements, cout in lignes:
        print(f"{lancements:>7}  {cout:>11.6f}  {question[:88]}")


if __name__ == "__main__":
    main()
