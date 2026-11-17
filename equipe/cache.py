"""Cache local de l'agent : le tableau lu une fois, et les réponses déjà obtenues.

Rien n'est écrit dans le dépôt : tout vit dans ~/.allergylab/cache/, à côté de la
clé. Une réponse n'est gardée que si elle respecte le contrat du kit, et la clé
de cache dépend de la question, du texte de la consigne et du fichier de
données : modifier la consigne ou changer de fichier invalide le cache de fait.

ALLERGYLAB_SANS_CACHE=1 désactive la lecture : la question repart au modèle.
`ALLERGYLAB_SANS_CACHE=1` mais une réponse déjà gardée : elle est ignorée, pas
effacée. Utile avant une passe officielle.
"""

import hashlib
import json
import os
import unicodedata
from pathlib import Path

from kit.donnees import FICHIER, charger

DOSSIER = Path.home() / ".allergylab" / "cache"
CONSIGNE = Path(__file__).parent / "consigne.md"

_tableau = None
_empreinte = None
_consigne = None

# Le moteur qui a produit la réponse entre dans la clé : sans ça, une réponse
# obtenue avec le CodeAgent serait resservie après un basculement vers
# kit.boucle_maison, qui raisonne autrement. À changer si le moteur change.
MOTEUR = "codeagent"


def actif():
    """Faux quand ALLERGYLAB_SANS_CACHE vaut 1, vrai, oui ou true."""
    return os.environ.get("ALLERGYLAB_SANS_CACHE", "").strip().lower() not in ("1", "vrai", "oui", "true")


def tableau():
    """Le tableau du kit, lu une seule fois par processus : une seconde gagnée par question."""
    global _tableau
    if _tableau is None:
        _tableau = charger()
    return _tableau


def empreinte_donnees():
    """Le SHA-256 du fichier de données, calculé une fois par processus."""
    global _empreinte
    if _empreinte is None:
        h = hashlib.sha256()
        with open(FICHIER, "rb") as fichier:
            for bloc in iter(lambda: fichier.read(1 << 20), b""):
                h.update(bloc)
        _empreinte = h.hexdigest()
    return _empreinte


def cle(question):
    """L'empreinte de (question, consigne, données, moteur) : deux formulations différentes donnent deux clés."""
    texte = "\n".join((normaliser(question), consigne(), MOTEUR, empreinte_donnees()))
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def consigne():
    """Le texte de la consigne, lu une fois par processus : il entre dans la clé de cache."""
    global _consigne
    if _consigne is None:
        try:
            _consigne = CONSIGNE.read_text(encoding="utf-8")
        except OSError:
            _consigne = ""
    return _consigne


def normaliser(question):
    """La question ramenée à sa forme comparable : sans accent, sans casse, sans blanc superflu.

    « Quel est l'âge médian ? » et « quel est l age median ? » tombent ainsi sur
    la même entrée. Une reformulation réelle reste une autre question.
    """
    decompose = unicodedata.normalize("NFKD", question.lower())
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    sans_ponctuation = "".join(c if c.isalnum() else " " for c in sans_accent)
    return " ".join(sans_ponctuation.split())


def lire(question):
    """La réponse déjà gardée pour cette question, ou None."""
    if not actif():
        return None
    chemin = DOSSIER / f"{cle(question)}.json"
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))["reponse"]
    except (OSError, ValueError, KeyError):
        return None


def ecrire(question, reponse):
    """Garde une réponse déjà validée par le contrat du kit. Rend le chemin écrit."""
    if not actif():
        return None
    DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
    chemin = DOSSIER / f"{cle(question)}.json"
    provisoire = chemin.with_name(f".{chemin.name}.{os.getpid()}")
    texte = json.dumps({"question": question, "reponse": reponse}, ensure_ascii=False, indent=2) + "\n"
    provisoire.write_text(texte, encoding="utf-8")
    os.chmod(provisoire, 0o600)
    provisoire.replace(chemin)
    return chemin
