# app/routers/administration.py
# Ce fichier regroupe tous les endpoints de CONFIGURATION d'un établissement,
# réservés à l'administrateur : sections, classes, matières, affectation des
# enseignants (avec coefficient), séquences/trimestres. C'est ce qui permet
# à chaque établissement de définir librement sa propre structure
# (cf. section 7 du document d'analyse : "aucune valeur codée en dur").

from fastapi import APIRouter, Depends, HTTPException, status, Query
# Query permet de déclarer explicitement un paramètre d'URL optionnel
# (ex: /administration/classes?section_id=3) avec sa valeur par défaut,
# de façon plus explicite qu'un simple argument Python optionnel.
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/administration", tags=["Administration"])


@router.get("/etablissement", response_model=schemas.EtablissementPublic)
def mon_etablissement(
    utilisateur: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
    db: Session = Depends(get_db),
):
    """
    Renvoie les informations de l'établissement de l'utilisateur connecté
    (nom, notamment). Utilisé par l'application DESKTOP pour afficher le
    nom réel de l'établissement sur les bulletins générés, plutôt qu'une
    valeur codée en dur — indispensable pour un système multi-établissement
    (cf. section 7 du document d'analyse).
    """
    etablissement = db.query(models.Etablissement).filter(
        models.Etablissement.id == utilisateur.etablissement_id
    ).first()
    return etablissement


# ---------------------------------------------------------------------------
# SECTIONS (ex : Francophone / Anglophone)
# ---------------------------------------------------------------------------
@router.post("/sections", response_model=schemas.SectionPublic)
def creer_section(
    donnees: schemas.SectionCreation,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
    # Seul l'admin peut créer une section : structure fondamentale de l'école.
):
    section = models.Section(etablissement_id=admin.etablissement_id, nom=donnees.nom)
    # On force etablissement_id à celui de l'admin connecté : impossible
    # pour un admin de créer une section dans un autre établissement,
    # même s'il essayait de le forcer dans la requête.
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


@router.get("/sections", response_model=List[schemas.SectionPublic])
def lister_sections(
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
    # Accessible aux admins ET aux enseignants (ils en ont besoin pour
    # le workflow de saisie : "choisir la section").
):
    return db.query(models.Section).filter(
        models.Section.etablissement_id == utilisateur.etablissement_id
    ).all()


# ---------------------------------------------------------------------------
# CLASSES (ex : 6e, 5e, ... Terminale D)
# ---------------------------------------------------------------------------
@router.post("/classes", response_model=schemas.ClassePublic)
def creer_classe(
    donnees: schemas.ClasseCreation,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    section = db.query(models.Section).filter(
        models.Section.id == donnees.section_id,
        models.Section.etablissement_id == admin.etablissement_id,
        # Vérifie que la section appartient bien à l'établissement de l'admin
        # avant d'y rattacher une classe (garde-fou multi-tenant).
    ).first()
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="Section introuvable pour votre établissement")

    classe = models.Classe(section_id=donnees.section_id, nom=donnees.nom)
    db.add(classe)
    db.commit()
    db.refresh(classe)
    return classe


@router.get("/classes", response_model=List[schemas.ClassePublic])
def lister_classes(
    section_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    """section_id est optionnel : si absent, renvoie toutes les classes
    de l'établissement ; si présent, filtre sur une section précise
    (utile pour le menu déroulant "choisir la classe" après la section)."""
    requete = db.query(models.Classe).join(models.Section).filter(
        models.Section.etablissement_id == utilisateur.etablissement_id
    )
    if section_id is not None:
        requete = requete.filter(models.Classe.section_id == section_id)
    return requete.all()


# ---------------------------------------------------------------------------
# MATIERES
# ---------------------------------------------------------------------------
@router.post("/matieres", response_model=schemas.MatierePublic)
def creer_matiere(
    donnees: schemas.MatiereCreation,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    matiere = models.Matiere(etablissement_id=admin.etablissement_id, nom=donnees.nom)
    db.add(matiere)
    db.commit()
    db.refresh(matiere)
    return matiere


@router.get("/matieres", response_model=List[schemas.MatierePublic])
def lister_matieres(
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    return db.query(models.Matiere).filter(
        models.Matiere.etablissement_id == utilisateur.etablissement_id
    ).all()


# ---------------------------------------------------------------------------
# ENSEIGNANTS (pour peupler le menu déroulant "affecter un enseignant")
# ---------------------------------------------------------------------------
@router.get("/enseignants", response_model=List[schemas.UtilisateurPublic])
def lister_enseignants(
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    return db.query(models.Utilisateur).filter(
        models.Utilisateur.etablissement_id == admin.etablissement_id,
        models.Utilisateur.role == models.RoleUtilisateur.ENSEIGNANT,
    ).all()


# ---------------------------------------------------------------------------
# AFFECTATIONS (enseignant <-> classe <-> matière, avec coefficient)
# ---------------------------------------------------------------------------
@router.post("/affectations", response_model=schemas.AffectationPublic)
def creer_affectation(
    donnees: schemas.AffectationCreation,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    # On vérifie que l'enseignant, la classe et la matière appartiennent
    # tous les trois à l'établissement de l'admin, pour éviter toute
    # affectation "croisée" entre établissements différents.
    enseignant = db.query(models.Utilisateur).filter(
        models.Utilisateur.id == donnees.enseignant_id,
        models.Utilisateur.etablissement_id == admin.etablissement_id,
        models.Utilisateur.role == models.RoleUtilisateur.ENSEIGNANT,
    ).first()
    classe = db.query(models.Classe).join(models.Section).filter(
        models.Classe.id == donnees.classe_id,
        models.Section.etablissement_id == admin.etablissement_id,
    ).first()
    matiere = db.query(models.Matiere).filter(
        models.Matiere.id == donnees.matiere_id,
        models.Matiere.etablissement_id == admin.etablissement_id,
    ).first()

    if not (enseignant and classe and matiere):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="Enseignant, classe ou matière introuvable pour votre établissement")

    existante = db.query(models.AffectationEnseignant).filter(
        models.AffectationEnseignant.enseignant_id == donnees.enseignant_id,
        models.AffectationEnseignant.classe_id == donnees.classe_id,
        models.AffectationEnseignant.matiere_id == donnees.matiere_id,
    ).first()
    if existante is not None:
        # Si l'affectation existe déjà, on met simplement à jour son
        # coefficient plutôt que de renvoyer une erreur de doublon :
        # plus pratique pour l'admin qui corrige une valeur.
        existante.coefficient = donnees.coefficient
        db.commit()
        db.refresh(existante)
        return existante

    affectation = models.AffectationEnseignant(
        enseignant_id=donnees.enseignant_id,
        classe_id=donnees.classe_id,
        matiere_id=donnees.matiere_id,
        coefficient=donnees.coefficient,
    )
    db.add(affectation)
    db.commit()
    db.refresh(affectation)
    return affectation


@router.get("/affectations/classe/{classe_id}", response_model=List[schemas.AffectationClasseDetaillee])
def affectations_de_la_classe(
    classe_id: int,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    """
    Renvoie, pour une classe donnée, la liste des matières enseignées
    avec leur coefficient et l'enseignant en charge. C'est cet endpoint
    que l'application DESKTOP interroge pour connaître le coefficient à
    appliquer à chaque matière lors du calcul de la moyenne pondérée
    (section 6.1 du document d'analyse) : les notes seules (via
    /notes/releve-classe) ne suffisent pas, il faut aussi le poids de
    chaque matière.
    """
    classe = db.query(models.Classe).join(models.Section).filter(
        models.Classe.id == classe_id,
        models.Section.etablissement_id == admin.etablissement_id,
    ).first()
    if classe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Classe introuvable")

    affectations = db.query(models.AffectationEnseignant).filter(
        models.AffectationEnseignant.classe_id == classe_id,
    ).all()

    resultat = []
    for a in affectations:
        # NOTE (point à clarifier avec l'établissement, cf. section 9 du
        # document d'analyse) : si jamais deux enseignants différents
        # étaient un jour affectés à la MÊME matière pour la MÊME classe
        # avec des coefficients différents, ce cas n'est pas résolu ici —
        # chaque affectation est renvoyée telle quelle. En pratique,
        # l'unique contrainte d'affectation (une ligne par enseignant)
        # suppose qu'une matière n'a qu'un seul enseignant par classe.
        resultat.append(schemas.AffectationClasseDetaillee(
            matiere_id=a.matiere_id,
            matiere_nom=a.matiere.nom,
            coefficient=a.coefficient,
            enseignant_nom=a.enseignant.nom_complet,
        ))
    return resultat


@router.get("/affectations/moi", response_model=List[schemas.AffectationDetaillee])
def mes_affectations(
    db: Session = Depends(get_db),
    enseignant: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    """
    Renvoie à l'enseignant connecté la liste de ses propres affectations
    (classe + matière + coefficient), utilisée pour peupler les menus
    déroulants "choisir la classe" / "choisir la matière" du formulaire
    de saisie de notes — un enseignant ne voit QUE ce qui lui a été
    attribué par l'administrateur.
    """
    affectations = db.query(models.AffectationEnseignant).filter(
        models.AffectationEnseignant.enseignant_id == enseignant.id
    ).all()

    resultat = []
    for a in affectations:
        # On enrichit chaque affectation avec les noms lisibles (classe,
        # matière) plutôt que de laisser le frontend refaire des requêtes
        # séparées pour chaque ligne.
        resultat.append(schemas.AffectationDetaillee(
            id=a.id,
            classe_id=a.classe_id,
            classe_nom=a.classe.nom,
            matiere_id=a.matiere_id,
            matiere_nom=a.matiere.nom,
            coefficient=a.coefficient,
        ))
    return resultat


# ---------------------------------------------------------------------------
# TRIMESTRES / SEQUENCES
# ---------------------------------------------------------------------------
@router.post("/trimestres", response_model=schemas.TrimestrePublic)
def creer_trimestre(
    donnees: schemas.TrimestreCreation,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    trimestre = models.Trimestre(
        etablissement_id=admin.etablissement_id,
        numero=donnees.numero,
        annee_scolaire=donnees.annee_scolaire,
    )
    db.add(trimestre)
    db.commit()
    db.refresh(trimestre)
    return trimestre


@router.get("/trimestres", response_model=List[schemas.TrimestrePublic])
def lister_trimestres(
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    """
    Liste les trimestres de l'établissement, utilisée côté frontend pour
    peupler le menu déroulant "choisir le trimestre" avant de créer une
    séquence, sans avoir à reconstruire la liste manuellement après
    chaque ajout.
    """
    return db.query(models.Trimestre).filter(
        models.Trimestre.etablissement_id == utilisateur.etablissement_id
    ).order_by(models.Trimestre.annee_scolaire, models.Trimestre.numero).all()


@router.post("/sequences", response_model=schemas.SequencePublic)
def creer_sequence(
    donnees: schemas.SequenceCreation,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    trimestre = db.query(models.Trimestre).filter(
        models.Trimestre.id == donnees.trimestre_id,
        models.Trimestre.etablissement_id == admin.etablissement_id,
    ).first()
    if trimestre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trimestre introuvable")

    sequence = models.Sequence(
        etablissement_id=admin.etablissement_id,
        trimestre_id=donnees.trimestre_id,
        numero=donnees.numero,
    )
    db.add(sequence)
    db.commit()
    db.refresh(sequence)
    return sequence


@router.get("/sequences", response_model=List[schemas.SequencePublic])
def lister_sequences(
    db: Session = Depends(get_db),
    utilisateur: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    return db.query(models.Sequence).filter(
        models.Sequence.etablissement_id == utilisateur.etablissement_id
    ).order_by(models.Sequence.numero).all()


@router.patch("/sequences/{sequence_id}/cloturer", response_model=schemas.SequencePublic)
def cloturer_sequence(
    sequence_id: int,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    """
    Verrouille une séquence : les enseignants ne peuvent plus modifier
    leurs notes après cette action (cf. section 9 du document d'analyse).
    C'est typiquement déclenché juste avant que l'administrateur ne
    lance la synchronisation depuis l'application desktop.
    """
    sequence = db.query(models.Sequence).filter(
        models.Sequence.id == sequence_id,
        models.Sequence.etablissement_id == admin.etablissement_id,
    ).first()
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Séquence introuvable")

    sequence.cloturee = 1
    db.commit()
    db.refresh(sequence)
    return sequence
