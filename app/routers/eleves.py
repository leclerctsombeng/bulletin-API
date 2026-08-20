# app/routers/eleves.py
# Endpoints liés aux élèves : import en masse par l'administrateur
# (section 5.2 du document d'analyse) et consultation par classe.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/eleves", tags=["Élèves"])


@router.post("/import-lot", response_model=List[schemas.ElevePublic])
def importer_eleves(
    eleves: List[schemas.EleveCreation],
    db: Session = Depends(get_db),
    admin_courant: models.Utilisateur = Depends(auth.exiger_role_admin),
    # Cette dependency bloque l'accès à quiconque n'est pas administrateur :
    # seul le compte admin peut importer une liste d'élèves (cf. cahier de
    # charges : "la liste des élèves par classe devra pouvoir être fournie
    # depuis le compte de l'administrateur").
):
    """
    Reçoit une liste d'élèves (typiquement extraite d'un fichier Excel/CSV
    côté interface web admin) et les insère en une seule transaction.
    """
    classes_ids = {e.classe_id for e in eleves}
    # On récupère l'ensemble (sans doublons) des classe_id présents dans
    # la liste envoyée, pour vérifier en une seule requête qu'elles
    # appartiennent bien à l'établissement de l'administrateur connecté.

    classes_valides = db.query(models.Classe.id).join(models.Section).filter(
        models.Section.etablissement_id == admin_courant.etablissement_id,
        models.Classe.id.in_(classes_ids),
    ).all()
    ids_valides = {c.id for c in classes_valides}

    if ids_valides != classes_ids:
        # Empêche un administrateur d'importer des élèves dans une classe
        # qui n'appartient pas à son établissement — c'est la garde-fou
        # multi-tenant au niveau applicatif, en plus du filtrage systématique.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Une ou plusieurs classes n'appartiennent pas à votre établissement",
        )

    nouveaux_eleves = []
    for e in eleves:
        # On construit un objet Eleve par ligne du fichier importé.
        nouveaux_eleves.append(models.Eleve(
            nom=e.nom,
            prenom=e.prenom,
            matricule=e.matricule,
            classe_id=e.classe_id,
        ))

    db.add_all(nouveaux_eleves)
    # add_all : ajoute plusieurs objets en une seule opération, plus
    # efficace qu'une boucle de db.add() suivie de commits séparés.
    db.commit()

    for e in nouveaux_eleves:
        db.refresh(e)
        # Recharge chaque élève pour récupérer son id auto-généré,
        # nécessaire pour construire la réponse (ElevePublic exige un id).

    return nouveaux_eleves


@router.get("/classe/{classe_id}", response_model=List[schemas.ElevePublic])
def lister_eleves_de_classe(
    classe_id: int,
    db: Session = Depends(get_db),
    utilisateur_courant: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
    # Ici on autorise admin ET enseignant : c'est cette liste qui alimente
    # le tableau de saisie des notes décrit dans le cahier de charges.
):
    """
    Renvoie la liste des élèves d'une classe, utilisée pour construire
    le tableau à deux colonnes (nom / note) côté application web enseignant.
    """
    classe = db.query(models.Classe).join(models.Section).filter(
        models.Classe.id == classe_id,
        models.Section.etablissement_id == utilisateur_courant.etablissement_id,
        # Vérifie que la classe demandée appartient bien à l'établissement
        # de l'utilisateur connecté, quel que soit son rôle.
    ).first()

    if classe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="Classe introuvable pour votre établissement")

    return db.query(models.Eleve).filter(models.Eleve.classe_id == classe_id).order_by(
        models.Eleve.nom, models.Eleve.prenom
    ).all()
    # Tri alphabétique par nom puis prénom : correspond à l'affichage
    # attendu dans le tableau de saisie.
