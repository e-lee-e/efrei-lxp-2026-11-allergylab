"""Datallergy, en fenêtre native : la page de l'interface dans une WebView.

Pas de navigateur à lancer, donc pas de second moteur en mémoire : la fenêtre
WebKit embarquée pèse une fraction de ce qu'un onglet Chrome demande. C'est le
sens de l'application de bureau — l'utilisateur ne doit pas avoir à savoir ce
qu'est une barre d'adresses.

Lancement : `uv run --extra bureau python -m equipe.bureau`
"""

from __future__ import annotations

import argparse

import webview

from equipe import cache, historique, interface


class Api:
    """Ce que la page peut demander à Python.

    Chaque méthode est appelée depuis JavaScript et rend un objet simple : un
    dictionnaire, une liste, rien d'exotique. Elle bloquent la promesse JS, pas
    la fenêtre — pywebview exécute la fonction dans un fil.
    """

    def etat(self):
        return interface.etat()

    def poser(self, question):
        question = str(question or "").strip()
        if not question:
            raise ValueError("question vide")
        return interface.traiter(question)

    def choisir_fichier(self):
        """Ouvre le sélecteur du système et pointe le cache sur le fichier choisi."""
        fenetre = webview.windows[0]
        choix = fenetre.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("Fichiers de données (*.csv;*.xlsx;*.parquet)", "Tous les fichiers (*.*)"),
        )
        if not choix:
            return interface.etat()  # dialogue annulé : rien ne change
        chemin = choix[0] if isinstance(choix, (list, tuple)) else choix
        cache.choisir_fichier(chemin)
        return interface.etat()

    def oublier(self):
        """Efface la liste des questions. Les réponses en cache, elles, restent."""
        historique.vider()
        return interface.etat()


def main():
    analyseur = argparse.ArgumentParser(description="Datallergy, en fenêtre native")
    analyseur.add_argument("--debug", action="store_true", help="ouvre l'inspecteur WebKit")
    options = analyseur.parse_args()

    webview.create_window(
        "Datallergy",
        str(interface.PAGE),
        js_api=Api(),
        width=1120,
        height=760,
        min_size=(880, 560),
        background_color="#ffffff",
    )
    webview.start(debug=options.debug)


if __name__ == "__main__":
    main()
