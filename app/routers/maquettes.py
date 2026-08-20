# app/routers/maquettes.py
# Ce fichier permet à un établissement de téléverser SA PROPRE maquette de
# bulletin depuis le compte administrateur (cf. cahier de charges : "chaque
# établissement devrait pouvoir fournir sa maquette de bulletins"), et
# permet à l'application desktop de la télécharger avant génération —
# plutôt que d'obliger l'opérateur à conserver le bon fichier .docx sur
# CHAQUE poste desktop qui génère des bulletins.

import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/administration/maquettes", tags=["Maquettes de bulletins"])

# Dossier de stockage des fichiers .docx téléversés, sur le disque du
# serveur. En production, ce dossier devrait être remplacé par un espace
# de stockage persistant dédié (ex: volume monté, stockage objet type S3),
# car le disque local d'un serveur applicatif peut être réinitialisé lors
# d'un redéploiement — point à clarifier lors du choix d'hébergement final
# (cf. remarque similaire sur les photos d'élèves, section 9 du document
# d'analyse). Pour cette phase, un dossier local suffit à démontrer le
# fonctionnement de bout en bout.
DOSSIER_STOCKAGE = Path(__file__).resolve().parent.parent.parent / "stockage_fichiers" / "maquettes"
DOSSIER_STOCKAGE.mkdir(parents=True, exist_ok=True)

EXTENSIONS_AUTORISEES = {".docx"}
TAILLE_MAX_OCTETS = 10 * 1024 * 1024  # 10 Mo : largement suffisant pour un .docx de maquette,
                                        # évite qu'un envoi accidentel ou malveillant ne remplisse le disque.


@router.post("", response_model=schemas.MaquettePublic)
def televerser_maquette(
    nom: str,
    fichier: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    """
    Téléverse une nouvelle maquette de bulletin pour l'établissement de
    l'administrateur connecté. Le fichier est stocké sur disque sous un
    nom généré aléatoirement (pas le nom d'origine) pour éviter tout
    conflit entre deux établissements qui téléverseraient un fichier
    appelé, par exemple, "maquette.docx".
    """
    extension = Path(fichier.filename).suffix.lower()
    if extension not in EXTENSIONS_AUTORISEES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seuls les fichiers .docx sont acceptés pour une maquette de bulletin.",
        )

    nom_fichier_stockage = f"{uuid.uuid4().hex}{extension}"
    chemin_complet = DOSSIER_STOCKAGE / nom_fichier_stockage

    taille_ecrite = 0
    with open(chemin_complet, "wb") as destination:
        while True:
            morceau = fichier.file.read(1024 * 1024)  # Lecture par blocs de 1 Mo
            # Lire par blocs plutôt que fichier.file.read() d'un coup évite
            # de charger un très gros fichier entièrement en mémoire avant
            # même d'avoir vérifié sa taille.
            if not morceau:
                break
            taille_ecrite += len(morceau)
            if taille_ecrite > TAILLE_MAX_OCTETS:
                destination.close()
                chemin_complet.unlink(missing_ok=True)
                # Nettoie le fichier partiellement écrit avant de refuser :
                # ne laisse jamais de fichier tronqué traîner sur le disque.
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Le fichier dépasse la taille maximale autorisée (10 Mo).",
                )
            destination.write(morceau)

    maquette = models.MaquetteBulletin(
        etablissement_id=admin.etablissement_id,
        nom=nom,
        chemin_fichier=str(chemin_complet),
    )
    db.add(maquette)
    db.commit()
    db.refresh(maquette)
    return maquette


@router.get("", response_model=List[schemas.MaquettePublic])
def lister_maquettes(
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
    # Accessible aussi aux enseignants en lecture seule : sans utilité
    # immédiate côté web, mais l'application desktop se connecte avec un
    # compte admin de toute façon (cf. README du projet desktop) — cette
    # ouverture n'introduit donc pas de risque, et évite une restriction
    # arbitraire si un futur usage en avait besoin.
):
    """Liste les maquettes disponibles pour l'établissement de l'utilisateur connecté."""
    return db.query(models.MaquetteBulletin).filter(
        models.MaquetteBulletin.etablissement_id == utilisateur.etablissement_id
    ).order_by(models.MaquetteBulletin.date_upload.desc()).all()


@router.get("/{maquette_id}/fichier")
def telecharger_maquette(
    maquette_id: int,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    """
    Renvoie le fichier .docx brut d'une maquette : c'est cet endpoint que
    l'application desktop appelle avant de générer les bulletins, pour
    toujours utiliser la version la plus à jour de la maquette de
    l'établissement sans dépendre d'une copie locale sur le poste.
    """
    maquette = db.query(models.MaquetteBulletin).filter(
        models.MaquetteBulletin.id == maquette_id,
        models.MaquetteBulletin.etablissement_id == admin.etablissement_id,
    ).first()

    if maquette is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maquette introuvable")

    if not os.path.isfile(maquette.chemin_fichier):
        # Cas rare mais possible (fichier supprimé manuellement du disque
        # serveur, disque redéployé...) : mieux vaut un message clair
        # qu'une erreur 500 générique côté application desktop.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Le fichier de cette maquette est introuvable sur le serveur.",
        )

    return FileResponse(
        path=maquette.chemin_fichier,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{maquette.nom}.docx",
        # filename : nom sous lequel le fichier sera proposé au
        # téléchargement, indépendant du nom aléatoire utilisé pour le
        # stockage interne (chemin_fichier).
    )


@router.delete("/{maquette_id}", status_code=status.HTTP_204_NO_CONTENT)
def supprimer_maquette(
    maquette_id: int,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    """Supprime une maquette (fichier + enregistrement en base)."""
    maquette = db.query(models.MaquetteBulletin).filter(
        models.MaquetteBulletin.id == maquette_id,
        models.MaquetteBulletin.etablissement_id == admin.etablissement_id,
    ).first()

    if maquette is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maquette introuvable")

    chemin = Path(maquette.chemin_fichier)
    if chemin.is_file():
        chemin.unlink()
        # Supprime le fichier physique en plus de l'enregistrement en
        # base : sans cela, le dossier de stockage grossirait indéfiniment
        # avec des fichiers orphelins jamais référencés nulle part.

    db.delete(maquette)
    db.commit()
