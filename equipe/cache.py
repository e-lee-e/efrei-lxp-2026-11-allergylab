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
import pickle
import unicodedata
from pathlib import Path

from kit.donnees import FICHIER, charger, colonnes

DOSSIER = Path.home() / ".allergylab" / "cache"
CONSIGNE = Path(__file__).parent / "consigne.md"

_tableau = None
_empreinte = None
_consigne = None
_dosages = None

# Le moteur qui a produit la réponse entre dans la clé : sans ça, une réponse
# obtenue avec Haiku serait resservie à un run local, et inversement.
def moteur():
    """Le moteur en cours, tel qu'il entre dans la clé de cache."""
    local = os.environ.get("ALLERGYLAB_MODELE", "").strip().lower() == "local"
    return "codeagent-local" if local else "codeagent-anthropic"


def actif():
    """Faux quand ALLERGYLAB_SANS_CACHE vaut 1, vrai, oui ou true."""
    return os.environ.get("ALLERGYLAB_SANS_CACHE", "").strip().lower() not in ("1", "vrai", "oui", "true")


def tableau():
    """Le tableau du kit, lu une fois par processus.

    Le fichier est relu à chaque `uv run kit agent`, puisque chaque question est
    un processus neuf. On garde donc une copie pickle dans le dossier de cache,
    nommée par l'empreinte du CSV : tant que le fichier n'a pas changé, la copie
    est relue (0,03 s au lieu de 0,66 s) ; dès qu'il change, le nom change et
    elle est refaite. Ce n'est pas de l'argent, c'est de la seconde.
    """
    global _tableau
    if _tableau is not None:
        return _tableau

    copie = DOSSIER / f"tableau-{empreinte_donnees()[:16]}.pkl"
    try:
        with open(copie, "rb") as fichier:
            _tableau = pickle.load(fichier)
        return _tableau
    except (OSError, pickle.UnpicklingError, ValueError, AttributeError, EOFError):
        pass  # pas de copie, copie d'une autre version de pandas, copie tronquée : on relit le CSV

    _tableau = charger()
    try:
        DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
        provisoire = copie.with_name(f".{copie.name}.{os.getpid()}")
        with open(provisoire, "wb") as fichier:
            pickle.dump(_tableau, fichier, protocol=5)
        os.chmod(provisoire, 0o600)
        provisoire.replace(copie)
    except OSError:
        pass  # écrire la copie est un confort, jamais une condition
    return _tableau


def dosages():
    """Les colonnes de dosage, lues dans le dictionnaire du kit (kit/colonnes.csv).

    Source unique : compter sur la position des colonnes ne vaut que pour le
    fichier livré, et casse dès qu'on passe une table inventée.
    """
    global _dosages
    if _dosages is None:
        dico = colonnes()
        _dosages = set(dico.loc[dico["bloc"] == "dosage", "colonne"])
    return _dosages


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
    texte = "\n".join((normaliser(question), consigne(), moteur(), empreinte_donnees()))
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
