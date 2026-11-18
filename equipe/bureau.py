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

from equipe import cache, historique, interface, reglages


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
        """Ouvre le sélecteur du système : plusieurs fichiers à la fois, le premier devient le fichier lu."""
        choix = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            # Ce que le lecteur sait ouvrir, et rien de plus : la liste précédente
            # annonçait .xlsx et .parquet, qu'aucun lecteur du projet ne sait lire.
            file_types=("Tableaux de patients (*.csv;*.tsv;*.txt)", "Tous les fichiers (*.*)"),
        )
        if not choix:
            return interface.etat()  # dialogue annulé : rien ne change
        chemins = list(choix) if isinstance(choix, (list, tuple)) else [choix]
        return interface.ajouter_fichiers(chemins)

    def activer_fichier(self, chemin):
        """Lit un fichier déjà connu, sans repasser par le sélecteur."""
        return interface.activer_fichier(chemin)

    def choisir_modele(self, nom):
        """Bascule entre Haiku (développement) et Sonnet (officiel, 20× plus cher)."""
        return interface.choisir_modele(nom)

    def enregistrer_cle(self, texte):
        """Range la clé d'API. Elle ne revient jamais vers la page, même en cas d'erreur."""
        return interface.enregistrer_cle(texte)

    def oublier(self):
        """Efface la liste des questions. Les réponses en cache, elles, restent."""
        historique.vider()
        return interface.etat()


def main():
    analyseur = argparse.ArgumentParser(description="Datallergy, en fenêtre native")
    analyseur.add_argument("--debug", action="store_true", help="ouvre l'inspecteur WebKit")
    options = analyseur.parse_args()

    # Ce que la fenêtre avait retenu : le modèle et le fichier restent ceux d'hier.
    retenu = reglages.lire().get("modele")
    if retenu in reglages.MODELES:
        reglages.choisir_modele(retenu, garder=False)
    chemin_retenu = reglages.fichier_retenu()
    if chemin_retenu:
        cache.choisir_fichier(chemin_retenu)
    reglages.ajouter_fichiers([str(cache.fichier())])  # le fichier du kit entre dans la liste connue

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
