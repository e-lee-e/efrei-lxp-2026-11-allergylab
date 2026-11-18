"""Cache local de l'agent : le tableau lu une fois, et les réponses déjà obtenues.

Rien n'est écrit dans le dépôt : tout vit dans ~/.allergylab/cache/, à côté de la
clé.

Le cache est un risque de pollution : une réponse fausse du modèle, gardée, est
resservie à 0 $ et passe pour établie. Cinq garde-fous :
- seules les réponses de l'agent complet sont gardées (agent.py consulte le cache
  APRÈS le portier et le routeur, qui calculent sans modèle et ont toujours
  raison sur lui) ;
- une abstention n'est jamais gardée : une abstention à tort se réessaie ;
- la clé suit tout ce qui change la réponse : question (opérateurs compris, voir
  normaliser_pour_cle), consigne, code des outils et de l'agent, variante,
  plafond d'étapes, modèle, fichier de données. Corriger un outil invalide donc
  les anciennes réponses ;
- à la lecture, la réponse est revalidée par le contrat du kit ;
- ALLERGYLAB_SANS_CACHE=1 coupe la lecture ET l'écriture, pour mesurer.

ALLERGYLAB_SANS_CACHE=1 désactive la lecture : la question repart au modèle.
`ALLERGYLAB_SANS_CACHE=1` mais une réponse déjà gardée : elle est ignorée, pas
effacée. Utile avant une passe officielle.
"""

import hashlib
import json
import os
import pickle
import re
import unicodedata
from pathlib import Path

from equipe import reglages
from kit import donnees, modele as modele_du_kit, reponse as contrat
from kit.donnees import FICHIER, charger, colonnes

DOSSIER = Path.home() / ".allergylab" / "cache"


class DonneeIllisible(Exception):
    """Le fichier désigné ne se lit pas comme un tableau de patients.

    Distincte des autres erreurs : c'est la seule qu'on doit dire à l'utilisateur
    en clair, et la seule pour laquelle aucune question ne peut être répondue.
    """
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
    # `kit evaluer --modele officiel` bascule modele.en_cours le temps de la
    # batterie. Lire notre propre réglage ici servait les réponses de Haiku à une
    # passe Sonnet : mesuré sur trois questions à 0 jeton et 0 $.
    return f"codeagent-{getattr(modele_du_kit, 'en_cours', 'developpement')}"


def actif():
    """Faux quand ALLERGYLAB_SANS_CACHE vaut 1, vrai, oui ou true."""
    return os.environ.get("ALLERGYLAB_SANS_CACHE", "").strip().lower() not in ("1", "vrai", "oui", "true")


def _pourquoi_illisible(chemin, souci):
    """La raison en français, jamais le nom d'une exception.

    « UnicodeDecodeError » ne dit rien à qui veut analyser des patients ; « ce
    n'est pas un fichier texte » se comprend et se corrige.
    """
    nom = type(souci).__name__
    if "Unicode" in nom or "decode" in str(souci).lower():
        return f"{chemin.name} n'est pas un fichier texte : ce n'est pas un tableau de patients."
    if "Empty" in nom:
        return f"{chemin.name} ne contient aucune ligne."
    if "Parser" in nom or "Tokeniz" in nom:
        return f"{chemin.name} n'a pas une forme de CSV lisible."
    return f"{chemin.name} ne se lit pas comme un tableau de patients."


def _lire_generique(chemin):
    """Lit un fichier de patients quelconque : rien n'est supposé du format.

    charger() applique les règles du fichier publié — séparateur « ; », bloc
    dosage après la quinzième colonne. Sur une table venue d'ailleurs, ces règles
    sont fausses : un CSV à virgules y devenait une seule colonne de texte, et
    les colonnes après la quinzième étaient converties en nombres par-dessus leur
    contenu clinique. Ici le séparateur se devine sur l'en-tête et chaque colonne
    se classe par ce qu'elle contient.
    """
    import pandas as pd

    try:
        with open(chemin, "r", encoding="utf-8-sig", errors="replace") as flux:
            entete = flux.readline()
    except OSError as souci:
        raise DonneeIllisible(f"{chemin.name} ne se lit pas ({souci.strerror})") from souci

    scores = {separateur: entete.count(separateur) for separateur in (";", ",", "\t", "|")}
    separateur = max(scores, key=lambda essai: (scores[essai], essai == ";"))
    if scores[separateur] == 0:
        raise DonneeIllisible(f"{chemin.name} n'a pas d'en-tête reconnaissable : aucune colonne à séparer")

    try:
        tableau = pd.read_csv(
            chemin,
            sep=separateur,
            encoding="utf-8-sig",
            dtype=str,
            keep_default_na=False,
            na_values=[""],
            on_bad_lines="skip",  # une ligne cassée ne doit pas faire perdre le fichier
        )
    except Exception as souci:
        raise DonneeIllisible(_pourquoi_illisible(chemin, souci)) from souci

    tableau.columns = [str(nom).strip() for nom in tableau.columns]
    if tableau.shape[1] < 2:
        raise DonneeIllisible(f"{chemin.name} ne donne qu'une seule colonne : ce n'est pas un tableau de patients")

    for nom in tableau.columns:
        cellules = tableau[nom].str.strip()
        remplies = cellules.dropna()
        if remplies.empty:
            continue
        # Une colonne se lit en nombres si presque toutes ses cellules en sont.
        # Le seuil laisse passer quelques valeurs textuelles parasites sans
        # transformer une colonne clinique en colonne de chiffres.
        nombres = pd.to_numeric(remplies.str.replace(",", ".", regex=False), errors="coerce")
        if nombres.notna().mean() >= 0.95:
            tableau[nom] = pd.to_numeric(cellules.str.replace(",", ".", regex=False), errors="coerce")
    return tableau


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
    empreinte = empreinte_donnees()
    marque = (str(courant), empreinte)
    if _tableau is not None and _tableau_de == marque:
        return _tableau

    copie = DOSSIER / f"tableau-{empreinte[:16]}.pkl"
    try:
        with open(copie, "rb") as flux:
            _tableau = pickle.load(flux)
        _tableau_de = marque
        return _tableau
    except (OSError, pickle.UnpicklingError, ValueError, AttributeError, EOFError):
        pass  # pas de copie, copie d'une autre version de pandas, copie tronquée : on relit le CSV

    # Sans argument, charger() suit kit.donnees.en_cours, que `kit evaluer`
    # bascule le temps d'une batterie : passer un chemin explicite l'ignorerait.
    try:
        # Le fichier publié se lit avec les règles du kit, à la lettre ; tout autre
        # fichier passe par le lecteur générique, qui ne suppose rien.
        if FICHIER_CHOISI is None and Path(courant) == Path(FICHIER):
            _tableau = charger(courant)
        else:
            _tableau = _lire_generique(courant)
    except DonneeIllisible:
        raise
    except Exception as souci:  # CSV illisible, séparateur inattendu, fichier binaire
        raise DonneeIllisible(
            f"{courant.name} ne se lit pas comme un tableau de patients ({type(souci).__name__})"
        ) from souci
    if _tableau is None or len(_tableau) == 0 or len(_tableau.columns) == 0:
        raise DonneeIllisible(f"{courant.name} ne contient aucune ligne exploitable")
    _tableau_de = marque
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
    ancien = FICHIER_CHOISI
    FICHIER_CHOISI = Path(chemin).expanduser().resolve() if chemin else None
    _tableau = None
    _tableau_de = None
    _empreinte = None
    _empreinte_de = None
    _dosages = None
    # On essaie tout de suite : un fichier qui ne se lit pas doit se dire à
    # l'ouverture, pas au milieu d'une question ni par une trace d'exception.
    try:
        if FICHIER_CHOISI is not None:
            tableau()
    except DonneeIllisible:
        FICHIER_CHOISI = ancien
        _tableau = _tableau_de = _empreinte = _empreinte_de = _dosages = None
        raise
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


def _signature(chemin):
    """Ce qui change dès qu'un fichier change : son chemin, sa date, sa taille."""
    try:
        etat = chemin.stat()
    except OSError as souci:
        raise DonneeIllisible(f"{chemin.name} est introuvable ({souci.strerror})") from souci
    if not chemin.is_file():
        raise DonneeIllisible(f"{chemin} n'est pas un fichier")
    if etat.st_size == 0:
        raise DonneeIllisible(f"{chemin.name} est vide")
    return (str(chemin), etat.st_mtime_ns, etat.st_size)


def empreinte_donnees():
    """Le SHA-256 du fichier de données.

    La signature (chemin, date, taille) est vérifiée à chaque appel : un fichier
    réécrit sur place — même nom, nouveau contenu — change donc d'empreinte, et
    tout ce qui en dépend (clé de cache, copie pickle) repart de zéro. Sans ça,
    un tableau modifié pendant que la fenêtre tourne continuait de répondre avec
    l'ancien contenu.
    """
    global _empreinte, _empreinte_de
    chemin = fichier()
    signature = _signature(chemin)
    if _empreinte is None or _empreinte_de != signature:
        h = hashlib.sha256()
        try:
            with open(chemin, "rb") as flux:
                for bloc in iter(lambda: flux.read(1 << 20), b""):
                    h.update(bloc)
        except OSError as souci:
            raise DonneeIllisible(f"{chemin.name} ne se lit pas ({souci.strerror})") from souci
        _empreinte = h.hexdigest()
        _empreinte_de = signature
    return _empreinte


_code = None


def code():
    """L'empreinte du code qui fabrique une réponse : agent, outils, format du kit.

    Lue une fois par processus. Sans elle, corriger un outil laissait servir les
    anciennes réponses, calculées avec le défaut qu'on venait de corriger.
    """
    global _code
    if _code is None:
        equipe = Path(__file__).parent
        fichiers = [equipe / "agent.py", *sorted((equipe / "outils").glob("*.py")), Path(contrat.__file__)]
        h = hashlib.sha256()
        for fichier_code in fichiers:
            try:
                # Fins de ligne ramenées à LF : la même empreinte sous Windows et ailleurs.
                h.update(fichier_code.read_bytes().replace(b"\r\n", b"\n"))
            except OSError:
                h.update(b"?")
        _code = h.hexdigest()
    return _code


def cle(question, contexte=""):
    """L'empreinte de tout ce qui détermine la réponse : deux questions différentes ne partagent jamais une entrée.

    `contexte` est ce que l'appelant sait et que le cache ignore (la variante et
    le plafond d'étapes de l'agent).
    """
    texte = "\n".join((normaliser_pour_cle(question), consigne(), code(), contexte, moteur(), empreinte_donnees()))
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


def normaliser_pour_cle(question):
    """Comme `normaliser`, mais sans perdre ce qui change le sens : < > = % + -.

    `normaliser` efface la ponctuation, donc « Age<18 » et « Age>18 » donnaient la
    même clé : le cache aurait répondu à l'une avec la réponse de l'autre. Pour une
    clé de cache, deux questions confondues sont pires que deux questions séparées
    à tort (le pire cas d'une séparation est un appel de plus).
    """
    decompose = unicodedata.normalize("NFKD", question.lower())
    texte = "".join(c for c in decompose if not unicodedata.combining(c))
    texte = re.sub(r"(?<=\d),(?=\d)", ".", texte)  # 0,3 et 0.3 : même nombre
    texte = re.sub(r"[^\w<>=%+\-.]", " ", texte)  # on garde les opérateurs
    texte = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", texte)  # un point n'est utile qu'entre deux chiffres
    return " ".join(texte.split())


def lire(question, contexte=""):
    """La réponse déjà gardée pour cette question, ou None. Elle est revalidée à la lecture."""
    if not actif():
        return None
    chemin = DOSSIER / f"{cle(question, contexte)}.json"
    try:
        gardee = json.loads(chemin.read_text(encoding="utf-8"))["reponse"]
        return contrat.valider(gardee)  # un fichier abîmé ou édité à la main ne passe pas
    except Exception:
        return None


def ecrire(question, reponse, contexte=""):
    """Garde une réponse validée par le contrat du kit. Rend le chemin écrit, ou None si rien n'est gardé.

    Une abstention n'est pas gardée : si elle était fausse, la resservir la
    rendrait définitive.
    """
    if not actif() or reponse.get("statut") != "reponse":
        return None
    DOSSIER.mkdir(mode=0o700, parents=True, exist_ok=True)
    chemin = DOSSIER / f"{cle(question, contexte)}.json"
    provisoire = chemin.with_name(f".{chemin.name}.{os.getpid()}")
    texte = json.dumps({"question": question, "reponse": reponse, "moteur": moteur()}, ensure_ascii=False, indent=2) + "\n"
    provisoire.write_text(texte, encoding="utf-8")
    os.chmod(provisoire, 0o600)
    provisoire.replace(chemin)
    return chemin
