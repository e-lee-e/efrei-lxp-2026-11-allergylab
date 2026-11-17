"""Le modèle local : qwen3:8b servi par Ollama, pour itérer sans facture.

Il ne remplace pas Haiku dans les passes qui comptent. Deux différences, écrites
ici pour ne pas les oublier :

- le coût est déclaré à 0 $/M ; le vrai prix, c'est l'électricité et le temps ;
- les jetons sont comptés par le tokenizer de qwen3, pas par celui d'Anthropic :
  ils se comparent aux étapes d'un run Haiku, jamais à ses jetons.

Deux pièges d'Ollama, vérifiés sur cette machine :
- Qwen3 réfléchit avant de répondre, et Ollama range cette réflexion hors du
  champ `content`, qui revient vide. `reasoning_effort="none"` ferme ce canal.
- Le serveur ne démarre pas tout seul : sans lui, l'erreur parle de connexion.
  D'où `disponible()` et le message qui dit quoi lancer.
"""

import json
import os
import urllib.request

from smolagents import LiteLLMModel

from kit import modele

NOM = "qwen3:8b"
URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
REGLAGE = {"identifiant": f"{NOM} (local)", "entree": 0.0, "sortie": 0.0}


def disponible():
    """La version du serveur Ollama, ou None s'il ne répond pas."""
    try:
        with urllib.request.urlopen(f"{URL}/api/version", timeout=2) as reponse:
            return json.loads(reponse.read()).get("version")
    except (OSError, ValueError):
        return None


class ModeleLocal(LiteLLMModel):
    """Le LiteLLMModel de smolagents, branché sur Ollama, avec le journal du kit rempli."""

    def __init__(self, nom=NOM):
        self.reglage = dict(REGLAGE, identifiant=f"{nom} (local)")
        super().__init__(
            model_id=f"ollama/{nom}",
            api_base=URL,
            api_key="local",
            retry=False,
            reasoning_effort="none",  # sans ça, content revient vide
        )

    def generate(self, messages, **options):
        modele.journal["moteur"] = "smolagents"
        reponse = LiteLLMModel.generate(self, messages, **options)
        modele.compter(
            self.reglage,
            reponse.token_usage.input_tokens,
            reponse.token_usage.output_tokens,
        )
        return reponse
