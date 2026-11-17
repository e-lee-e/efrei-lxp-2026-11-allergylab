"""Passer une batterie de questions à l'agent et compter, famille par famille.

    uv run python -m equipe.mesure equipe/questions/lot-gpt.toml

Trois chiffres par famille : combien de questions traitées sans modèle, combien
justes, et ce que la passe a coûté. Le détail est écrit dans equipe/mesures/ pour
être comparé d'une passe à l'autre.

Rien n'est payé sans le dire : le plafond est annoncé en tête de passe, et la
passe s'arrête si le budget est dépassé.
"""

import json
import pathlib
import sys
import time
import tomllib

from kit import modele, traces

from equipe import agent

DOSSIER = pathlib.Path(__file__).parent / "mesures"


def charger_lot(chemin):
    lot = tomllib.loads(pathlib.Path(chemin).read_text(encoding="utf-8"))
    return lot.get("question", lot.get("questions", []))


def tient(reponse, attendu):
    """La réponse respecte-t-elle ce qui était attendu ? Vrai, faux, ou None si on ne sait pas."""
    if not isinstance(reponse, dict):
        return False  # hors contrat, ou maximum d'étapes atteint : ce n'est pas une réponse
    statut = reponse.get("statut")
    if attendu == "abstention":
        return statut == "abstention"
    return statut == "reponse" and reponse.get("valeur") not in (None, "")


def passer(lot, plafond=0.30):
    questions = charger_lot(lot)
    print(f"{len(questions)} questions, plafond {plafond:.2f} $.")
    resultats, depense = [], 0.0
    for question in questions:
        modele.journal_neuf()
        # La trace est écrite par le kit, comme pour `kit agent` : sans elle, une
        # passe lancée depuis Python ne laisse aucune trace de ce qu'elle a coûté.
        with traces.appel(question["texte"], None, None) as trace:
            debut = time.time()
            reponse = None
            for _ in range(2):  # une erreur du modèle est souvent passagère : on retente une fois
                try:
                    reponse = agent.repondre(question["texte"])
                    break
                except Exception as erreur:
                    derniere = erreur
            if reponse is None:
                reponse = {"statut": "erreur", "valeur": str(derniere)[:120], "justification": ""}
            duree = time.time() - debut
            cout = modele.journal.get("cout_estime") or 0.0
            trace.noter(
                moteur=modele.journal.get("moteur"),
                modele=modele.journal.get("modele"),
                reponse=reponse,
                jetons=modele.journal.get("jetons"),
                cout_estime=cout,
                duree_s=round(duree, 2),
            )
        depense += cout
        resultats.append(
            {
                "id": question["id"],
                "famille": question["famille"],
                "attend": question["attend"],
                "texte": question["texte"],
                "statut": reponse.get("statut") if isinstance(reponse, dict) else None,
                "valeur": reponse.get("valeur") if isinstance(reponse, dict) else str(reponse)[:200],
                "justification": reponse.get("justification") if isinstance(reponse, dict) else "réponse hors contrat",
                "moteur": modele.journal.get("moteur"),
                "jetons": modele.journal.get("jetons"),
                "cout": cout,
                "duree": round(duree, 2),
                "juste": tient(reponse, question["attend"]),
            }
        )
        repere = "juste" if resultats[-1]["juste"] else "FAUX"
        print(
            f"  {question['id']:<4} {resultats[-1]['moteur'] or '?':<12} "
            f"{cout:.6f} $ {duree:5.1f} s  {repere}"
        )
        if depense > plafond:
            print(f"Plafond atteint ({depense:.4f} $) : passe arrêtée.")
            break

    DOSSIER.mkdir(exist_ok=True)
    sortie = DOSSIER / (pathlib.Path(lot).stem + f"-{time.strftime('%Y%m%dT%H%M%S')}.json")
    sortie.write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    resume(resultats, depense)
    print(f"Détail : {sortie}")
    return resultats


def resume(resultats, depense):
    familles = sorted({r["famille"] for r in resultats})
    print()
    print(f"{'famille':<8}{'traitées':>9}{'justes':>8}{'gratuit':>9}{'coût':>12}")
    for famille in familles:
        lignes = [r for r in resultats if r["famille"] == famille]
        libres = sum(1 for r in lignes if not r["cout"])
        justes = sum(1 for r in lignes if r["juste"])
        cout = sum(r["cout"] for r in lignes)
        print(f"{famille:<8}{len(lignes):>9}{justes:>8}{libres:>9}{cout:>11.6f} $")
    total = len(resultats)
    justes = sum(1 for r in resultats if r["juste"])
    libres = sum(1 for r in resultats if not r["cout"])
    print(
        f"{'TOTAL':<8}{total:>9}{justes:>8}{libres:>9}{depense:>11.6f} $   "
        f"({100 * justes / total:.0f} % justes, {100 * libres / total:.0f} % gratuites)"
    )


if __name__ == "__main__":
    passer(sys.argv[1] if len(sys.argv) > 1 else "equipe/questions/lot-gpt.toml")
