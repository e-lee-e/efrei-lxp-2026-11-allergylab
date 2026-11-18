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

from equipe import reglages
from kit import donnees
from kit.donnees import FICHIER, charger, colonnes

DOSSIER = Path.home() / ".allergylab" / "cache"
CONSIGNE = Path(__file__).parent / "consigne.md"

_tableau = None
_tableau_de = None
_empreinte = None
_empreinte_de = None
# Fichier choisi dans l'interface de bureau ; None = le fichier livré avec le kit.
FICHIER_CHOISI = None
_consigne = None
_dosages = None

# Le moteur qui a produit la réponse entre dans la clé : sans ça, une réponse
# obtenue avec Haiku serait resservie à un run local, et inversement.
def moteur():
    """Le moteur en cours, tel qu'il entre dans la clé de cache.

    Le modèle choisi en fait partie : une réponse de Haiku resservie à un appel
    Sonnet serait présentée au mauvais tarif, et l'inverse ferait payer Haiku
    pour un raisonnement qu'il n'a pas fait.
    """
    return f"codeagent-{reglages.modele()}"


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
    global _tableau, _tableau_de
    courant = fichier()
    if _tableau is not None and _tableau_de == courant:
        return _tableau

    copie = DOSSIER / f"tableau-{empreinte_donnees()[:16]}.pkl"
    try:
        with open(copie, "rb") as flux:
            _tableau = pickle.load(flux)
        _tableau_de = courant
        return _tableau
    except (OSError, pickle.UnpicklingError, ValueError, AttributeError, EOFError):
        pass  # pas de copie, copie d'une autre version de pandas, copie tronquée : on relit le CSV

    # Sans argument, charger() suit kit.donnees.en_cours, que `kit evaluer`
    # bascule le temps d'une batterie : passer un chemin explicite l'ignorerait.
    _tableau = charger(courant)
    _tableau_de = courant
    try:
        DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
        provisoire = copie.with_name(f".{copie.name}.{os.getpid()}")
        with open(provisoire, "wb") as flux:
            pickle.dump(_tableau, flux, protocol=5)
        os.chmod(provisoire, 0o600)
        provisoire.replace(copie)
    except OSError:
        pass  # écrire la copie est un confort, jamais une condition
    return _tableau


def fichier():
    """Le fichier lu en ce moment.

    Trois cas, dans cet ordre : celui choisi dans la fenêtre, sinon celui que le
    kit désigne (`donnees.en_cours`, qu'une évaluation remplace par sa table),
    sinon le fichier publié.
    """
    if FICHIER_CHOISI is not None:
        return FICHIER_CHOISI
    return Path(getattr(donnees, "en_cours", FICHIER))


def choisir_fichier(chemin=None):
    """Lit un autre fichier que celui du kit ; None remet le fichier livré.

    L'empreinte du fichier entre dans la clé de cache : changer de fichier
    invalide de fait les réponses de l'ancien, sans rien effacer à la main.
    """
    global FICHIER_CHOISI, _tableau, _tableau_de, _empreinte, _empreinte_de, _dosages
    FICHIER_CHOISI = Path(chemin).expanduser().resolve() if chemin else None
    _tableau = None
    _tableau_de = None
    _empreinte = None
    _empreinte_de = None
    _dosages = None
    return fichier()


def dosages():
    """Les colonnes de dosage, lues dans le dictionnaire du kit (kit/colonnes.csv).

    Source unique : compter sur la position des colonnes ne vaut que pour le
    fichier livré, et casse dès qu'on passe une table inventée.
    """
    global _dosages
    if _dosages is None:
        if FICHIER_CHOISI is None:
            dico = colonnes()
            _dosages = set(dico.loc[dico["bloc"] == "dosage", "colonne"])
        else:
            # Le dictionnaire du kit décrit le fichier du kit : sur un autre fichier,
            # on se rabat sur la forme des noms de colonnes de dosage.
            _dosages = {c for c in tableau().columns if c.lower().startswith(("act_d", "bet_v"))}
    return _dosages


def empreinte_donnees():
    """Le SHA-256 du fichier de données, calculé une fois par fichier."""
    global _empreinte, _empreinte_de
    if _empreinte is None or _empreinte_de != fichier():
        h = hashlib.sha256()
        with open(fichier(), "rb") as flux:
            for bloc in iter(lambda: flux.read(1 << 20), b""):
                h.update(bloc)
        _empreinte = h.hexdigest()
        _empreinte_de = fichier()
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
