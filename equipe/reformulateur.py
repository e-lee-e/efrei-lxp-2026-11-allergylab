"""Le reformulateur local : réécrire la question en français simple, sans réseau ni facture.

L'idée : le routeur sait reconnaître une dizaine de formulations propres. Plutôt
que d'en écrire une de plus chaque fois qu'une question arrive autrement, un
petit modèle tourne sur la machine et réécrit la question dans une des formes
que le routeur connaît déjà. Ce qui reste incompréhensible escalade.

Trois propriétés, dans cet ordre d'importance :

1. **Gratuit et local** : Ollama sur 127.0.0.1, aucun appel facturé. Le modèle
   tourne sur le CPU de la machine ; un 1,7 milliard de paramètres suffit parce
   que la tâche est de la réécriture, pas de l'analyse.
2. **Ne jamais changer le sens** : la réécriture n'est acceptée que si elle a
   exactement les mêmes nombres que la question d'origine. Une question sans
   seuil qui revient avec un seuil est jetée. C'est le garde-fou principal,
   parce qu'une réécriture fautive produirait une réponse fausse, calculée
   proprement, et rien ne nous alerterait.
3. **Ne jamais bloquer** : si le serveur ne répond pas, si le modèle délire ou
   si la réécriture ne route pas, on rend None et l'agent continue comme avant.
   Ce module ne peut donc pas casser une réponse ; il peut seulement la rendre
   gratuite.

Le modèle se change sans toucher au code : ALLERGYLAB_REFORMULATEUR=qwen3:8b.
"""

import json
import os
import re
import unicodedata
import urllib.error
import urllib.request

URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
NOM = os.environ.get("ALLERGYLAB_REFORMULATEUR", "qwen3:1.7b")

CONSIGNE = """Réécris la question en français simple, sans rien ajouter ni retirer.
Formes acceptées, choisis la plus proche :
- Combien de lignes compte le tableau ?
- Quel est l'âge médian des patients ?
- Quel est l'âge moyen des patients ?
- Quelle est la répartition des puces ?
- Quelle est la région la plus représentée ?
- Combien de patients ont plus de N ans ?
- Combien de patients sont des femmes ?
- Les femmes sont-elles plus souvent sensibilisées que les hommes ?
- Combien de patients ont eu une puce ISAC_V1 ? (idem ISAC_V2 ou ALEX)
Ne recopie jamais les exemples entre chevrons : ils ne sont pas des questions.
Si aucune forme ne convient, réponds exactement : INCONNU
Réponds par la question réécrite seule, sans explication ni guillemets."""


def disponible():
    """La version du serveur Ollama, ou None s'il ne tourne pas."""
    try:
        with urllib.request.urlopen(f"{URL}/api/version", timeout=2) as reponse:
            return json.loads(reponse.read()).get("version")
    except (OSError, ValueError):
        return None


# Mots qui portent le sens de la question. Si l'un d'eux disparaît dans la
# réécriture, le sens a changé : « combien de patientes » ne devient jamais
# « combien de patients », même si les deux phrases se ressemblent.
CONCEPTS = (
    (("femme", "femmes", "patiente", "patientes", "feminin", "femmes"), "feminin"),
    (("homme", "hommes", "masculin", "masculins"), "masculin"),
    (("rural", "rurale", "rurales", "ruraux", "campagne"), "rural"),
    (("ville", "villes", "urbain", "urbaine", "urbains", "urbaines"), "urbain"),
    (("cutane", "cutanes", "urticaire"), "cutane"),
    (("rhinite", "rhinites"), "rhinite"),
    (("biotherapie", "biologique", "biologiques"), "biotherapie"),
    (("puce", "puces", "isac", "alex"), "puce"),
    (("plus",), "plus"),  # « plus de 60 ans » ne devient jamais « moins de 60 ans »
    (("moins",), "moins"),
    (("median", "mediane"), "median"),
    (("moyen", "moyenne"), "moyen"),
)


def _plat(texte):
    """Minuscules, sans accents, mots séparés : sert aux comparaisons de sens."""
    decompose = unicodedata.normalize("NFKD", str(texte).lower())
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    return " " + " ".join("".join(c if c.isalnum() else " " for c in sans_accent).split()) + " "


def _sens(texte):
    """Les concepts présents dans une question : « patientes » et « femmes » en sont un seul."""
    plat = _plat(texte)
    return {
        concept
        for mots, concept in CONCEPTS
        if any(f" {mot} " in plat for mot in mots)
    }


def _nombres(texte):
    """Les nombres d'une question : un seuil qui apparaît ou disparaît change le sens."""
    return set(re.findall(r"\d+(?:[.,]\d+)?", str(texte)))


def reformuler(question, delai=60):
    """La question réécrite par le modèle local, ou None si la réécriture n'est pas sûre."""
    corps = {
        "model": NOM,
        "messages": [
            {"role": "system", "content": CONSIGNE},
            {"role": "user", "content": question},
        ],
        "stream": False,
        "think": False,  # sans ça, Qwen3 met sa réponse dans le champ de réflexion
        "options": {"temperature": 0, "num_predict": 60},
    }
    requete = urllib.request.Request(
        f"{URL}/api/chat",
        data=json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            contenu = json.loads(reponse.read()).get("message", {}).get("content", "")
    except (OSError, ValueError):
        return None

    reecrite = " ".join(str(contenu).strip().strip('"').split())
    if not reecrite or "inconnu" in reecrite.lower():
        return None
    if _nombres(reecrite) != _nombres(question):
        return None  # un nombre est apparu ou a disparu : on ne fait pas confiance
    if _sens(question) - _sens(reecrite):
        return None  # un mot porteur de sens a disparu : la question a changé
    return reecrite
