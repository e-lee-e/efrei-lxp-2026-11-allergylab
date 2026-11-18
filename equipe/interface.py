"""L'application locale : une page, une question, une réponse — pour les chercheurs.

Cette page ne calcule rien. Chaque question passe par `equipe.agent.repondre()`,
donc par le cache, le portier hors sujet, le routeur, le traducteur et l'agent
complet, avec ses plafonds de jetons et de temps ; et chaque question laisse une
trace comme un `kit agent`, ce qui garde le cumul de dépense juste.

Deux façons de l'ouvrir, une seule logique :

- `uv run --extra bureau python -m equipe.bureau` ouvre une fenêtre native
  (pywebview, WebKit) : pas de navigateur à lancer, rien d'autre à installer
  pour l'utilisateur ;
- `uv run python -m equipe.interface` sert la même page en HTTP local, ce qui
  reste le repli quand WebKit n'est pas disponible.

Trois choix, pour un public qui ne lit pas de code :

- la réponse occupe la page, et le vocabulaire interne (couche, coût, jetons)
  reste derrière un lien, fermé par défaut ;
- une abstention n'est pas une panne : la page écrit « Pas de réponse » et donne
  la raison en français ;
- une question déjà posée ne coûte rien, et l'écran le dit.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from equipe import agent, cache, historique
from kit import modele, traces

PAGE = Path(__file__).with_name("app.html")

# Ce que la page affiche à la place du nom du module : personne, hors de l'équipe,
# ne sait ce qu'est un « traducteur ».
COUCHES = {
    "cache": "une question déjà posée",
    "hors-sujet": "la question ne porte pas sur le fichier",
    "routeur": "un calcul direct, sans modèle",
    "traducteur": "un calcul direct, sans modèle",
    "smolagents": "le modèle de langage",
    "delai": "délai dépassé",
}

# Le journal du kit est un état de module : deux questions en parallèle
# s'écraseraient et la page afficherait le coût de l'une sur la réponse de l'autre.
VERROU = threading.Lock()
SESSION = {"questions": 0, "cout": 0.0, "duree": 0.0}


def traiter(question: str) -> dict:
    """Répond à une question, l'enregistre dans l'historique et rend ce que la page affiche."""
    modele.journal_neuf()
    debut = time.time()
    with VERROU, traces.appel(question, None, None) as trace:
        try:
            sortie = agent.repondre(question)
        except Exception as erreur:  # une panne ne doit pas casser la page
            sortie = {
                "statut": "erreur",
                "valeur": None,
                "justification": f"Le calcul n'a pas abouti ({type(erreur).__name__}). "
                "Reformulez la question, ou réessayez dans un instant.",
            }
        duree = time.time() - debut
        cout = modele.journal.get("cout_estime") or 0.0
        jetons = modele.journal.get("jetons")
        etapes = len(modele.journal.get("etapes") or [])
        trace.noter(
            moteur=modele.journal.get("moteur"),
            modele=modele.journal.get("modele"),
            reponse=sortie if isinstance(sortie, dict) else str(sortie)[:200],
            jetons=jetons,
            cout_estime=cout,
            duree_s=round(duree, 2),
        )

    if not isinstance(sortie, dict):
        # Le modèle a rendu autre chose que le contrat : la page le dit simplement.
        sortie = {
            "statut": "illisible",
            "valeur": None,
            "justification": "La réponse n'a pas le format attendu. Reformulez la question "
            "en nommant ce que vous cherchez.",
        }

    SESSION["questions"] += 1
    SESSION["cout"] += cout
    SESSION["duree"] += duree

    entree = {
        "question": question,
        "statut": str(sortie.get("statut") or "illisible"),
        "valeur": sortie.get("valeur"),
        "justification": str(sortie.get("justification") or ""),
        "couche": COUCHES.get(modele.journal.get("moteur"), "—"),
        "cout": round(cout, 6),
        "duree": round(duree, 1),
        "jetons": jetons,
        "etapes": etapes,
        "fichier": cache.fichier().name,
        "quand": datetime.now().isoformat(timespec="seconds"),
    }
    historique.enregistrer(entree)
    return entree


def etat() -> dict:
    """Tout ce que la barre latérale et le pied de page affichent."""
    nom = cache.fichier().name
    return {
        "fichier": nom,
        "entrees": historique.du_fichier(nom),
        "session": {"questions": SESSION["questions"], "cout": round(SESSION["cout"], 6)},
    }


class Gestion(BaseHTTPRequestHandler):
    server_version = "Datallergy"

    def log_message(self, *args):  # une démo n'a pas besoin d'un journal d'accès
        pass

    def _envoyer(self, code, corps, type_="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _json(self, code, objet):
        self._envoyer(code, json.dumps(objet, ensure_ascii=False, default=str).encode())

    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin in ("/", "/index.html"):
            self._envoyer(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif chemin == "/api/etat":
            self._json(200, etat())
        else:
            self._json(404, {"erreur": "page inconnue"})

    def do_POST(self):
        chemin = self.path.split("?")[0]
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
            corps = json.loads(self.rfile.read(longueur) or b"{}")
        except (ValueError, json.JSONDecodeError):
            corps = {}

        if chemin == "/api/question":
            question = str(corps.get("question") or "").strip()
            if not question:
                self._json(400, {"erreur": "question vide"})
                return
            self._json(200, traiter(question))
        elif chemin == "/api/fichier":
            chemin_voulu = str(corps.get("chemin") or "").strip()
            if chemin_voulu and not Path(chemin_voulu).is_file():
                self._json(400, {"erreur": "fichier introuvable"})
                return
            cache.choisir_fichier(chemin_voulu or None)
            self._json(200, etat())
        else:
            self._json(404, {"erreur": "page inconnue"})


def main():
    analyseur = argparse.ArgumentParser(description="Datallergy, en HTTP local")
    analyseur.add_argument("--port", type=int, default=8765)
    analyseur.add_argument("--ouvrir", action="store_true", help="ouvre la page dans le navigateur")
    options = analyseur.parse_args()

    serveur = ThreadingHTTPServer(("127.0.0.1", options.port), Gestion)
    adresse = f"http://127.0.0.1:{options.port}/"
    print(f"Interface prête : {adresse}")
    if options.ouvrir:
        threading.Timer(0.6, webbrowser.open, args=(adresse,)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        serveur.server_close()


if __name__ == "__main__":
    main()
