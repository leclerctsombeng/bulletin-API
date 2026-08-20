# app/routers/notes.py
# Endpoint central du système : la saisie des notes par un enseignant,
# correspondant exactement au workflow décrit dans le cahier de charges :
# "section → classe → matière → tableau élèves/notes → Valider/Modifier".

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/notes", tags=["Notes"])


def _verifier_affectation(db: Session, enseignant_id: int, classe_id: int, matiere_id: int) -> models.AffectationEnseignant:
    """
    Fonction utilitaire (préfixée par "_" car réservée à ce fichier) qui
    vérifie qu'un enseignant est bien autorisé à saisir des notes pour
    cette classe et cette matière précises, et renvoie son affectation
    (qui contient le coefficient déclaré).
    """
    affectation = db.query(models.AffectationEnseignant).filter(
        models.AffectationEnseignant.enseignant_id == enseignant_id,
        models.AffectationEnseignant.classe_id == classe_id,
        models.AffectationEnseignant.matiere_id == matiere_id,
    ).first()

    if affectation is None:
        # Empêche un enseignant de saisir des notes dans une classe/matière
        # où il n'est pas déclaré : sécurité fonctionnelle indispensable,
        # au-delà du simple filtrage par établissement.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas affecté à cette classe pour cette matière",
        )
    return affectation


@router.get("/saisie-actuelle", response_model=dict)
def obtenir_saisie_actuelle(
    classe_id: int,
    matiere_id: int,
    sequence_id: int,
    db: Session = Depends(get_db),
    enseignant_courant: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    """
    Renvoie, pour une classe/matière/séquence donnée, la liste des élèves
    avec leur note existante (ou null si pas encore saisie) et le
    coefficient actuellement déclaré. C'est cet endpoint qui permet à
    l'interface enseignant de construire le tableau à deux colonnes du
    cahier de charges, pré-rempli si une saisie précédente existe
    (nécessaire pour le bouton "Modifier"), et de savoir si la séquence
    est encore ouverte à la modification.
    """
    affectation = _verifier_affectation(db, enseignant_courant.id, classe_id, matiere_id)

    sequence = db.query(models.Sequence).filter(
        models.Sequence.id == sequence_id,
        models.Sequence.etablissement_id == enseignant_courant.etablissement_id,
    ).first()
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Séquence introuvable")

    eleves = db.query(models.Eleve).filter(models.Eleve.classe_id == classe_id).order_by(
        models.Eleve.nom, models.Eleve.prenom
    ).all()

    # On charge toutes les notes existantes de la classe/matière/séquence
    # en une seule requête, puis on les indexe par eleve_id pour un accès
    # instantané ligne par ligne (plutôt qu'une requête par élève, ce qui
    # serait lent pour un grand effectif).
    notes_existantes = db.query(models.Note).join(models.Eleve).filter(
        models.Eleve.classe_id == classe_id,
        models.Note.matiere_id == matiere_id,
        models.Note.sequence_id == sequence_id,
    ).all()
    index_notes = {n.eleve_id: n.valeur for n in notes_existantes}

    lignes = [
        {"eleve_id": e.id, "nom": e.nom, "prenom": e.prenom,
         "valeur": index_notes.get(e.id)}  # None si pas encore saisie
        for e in eleves
    ]

    return {
        "coefficient": affectation.coefficient,
        "sequence_cloturee": sequence.cloturee == 1,
        "saisie_existante": len(notes_existantes) > 0,
        # Indique au frontend s'il doit afficher le tableau en lecture
        # seule avec un bouton "Modifier", ou directement en saisie libre
        # (cf. cahier de charges : boutons Valider / Modifier).
        "lignes": lignes,
    }


@router.post("/valider-lot", response_model=List[schemas.NotePublic])
def valider_notes_en_lot(
    saisie: schemas.SaisieNotesLot,
    db: Session = Depends(get_db),
    enseignant_courant: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    """
    Correspond au clic sur le bouton "Valider" de l'interface enseignant :
    reçoit toutes les notes de la classe/matière/séquence en une seule
    requête et les enregistre (création si absente, mise à jour sinon).
    """
    if enseignant_courant.role != models.RoleUtilisateur.ENSEIGNANT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="Seul un enseignant peut saisir des notes")

    affectation = _verifier_affectation(
        db, enseignant_courant.id, saisie.classe_id, saisie.matiere_id
    )

    sequence = db.query(models.Sequence).filter(
        models.Sequence.id == saisie.sequence_id,
        models.Sequence.etablissement_id == enseignant_courant.etablissement_id,
    ).first()
    if sequence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Séquence introuvable")

    if sequence.cloturee == 1:
        # Une séquence clôturée par l'administrateur ne peut plus recevoir
        # de nouvelles notes (cf. section 9 du document d'analyse,
        # "Verrouillage des notes après synchronisation").
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Cette séquence est clôturée : la saisie n'est plus modifiable",
        )

    # Si l'enseignant a modifié le coefficient depuis sa dernière saisie,
    # on met à jour l'affectation pour rester cohérent avec le calcul
    # de moyenne pondérée qui sera fait côté desktop.
    affectation.coefficient = saisie.coefficient

    notes_resultat = []
    for ligne in saisie.lignes:
        # Pour chaque élève du tableau, on cherche si une note existe déjà
        # (cas d'une modification) ou s'il faut en créer une nouvelle.
        note_existante = db.query(models.Note).filter(
            models.Note.eleve_id == ligne.eleve_id,
            models.Note.matiere_id == saisie.matiere_id,
            models.Note.sequence_id == saisie.sequence_id,
        ).first()

        if note_existante is not None:
            # Mise à jour d'une note déjà saisie (cas du bouton "Modifier").
            note_existante.valeur = ligne.valeur
            note_existante.statut = models.StatutNote.VALIDEE
            note_existante.enseignant_id = enseignant_courant.id
            notes_resultat.append(note_existante)
        else:
            # Première saisie pour cet élève sur cette matière/séquence.
            nouvelle_note = models.Note(
                eleve_id=ligne.eleve_id,
                matiere_id=saisie.matiere_id,
                sequence_id=saisie.sequence_id,
                enseignant_id=enseignant_courant.id,
                valeur=ligne.valeur,
                statut=models.StatutNote.VALIDEE,
            )
            db.add(nouvelle_note)
            notes_resultat.append(nouvelle_note)

    db.commit()
    # Une seule transaction pour toute la classe : soit toutes les notes
    # sont enregistrées, soit aucune (évite un tableau à moitié sauvegardé
    # en cas d'erreur réseau au milieu de l'opération).

    for n in notes_resultat:
        db.refresh(n)

    return notes_resultat


@router.get("/statut-saisie/{classe_id}", response_model=dict)
def statut_saisie_par_classe(
    classe_id: int,
    sequence_id: int,
    db: Session = Depends(get_db),
    admin_courant: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    """
    Alimente le tableau de bord administrateur : pour une classe et une
    séquence données, indique quelles matières n'ont pas encore été
    saisies par leur enseignant (cf. cahier de charges : "les matières où
    un enseignant n'a pas encore enregistré les notes devra être marqué").
    """
    matieres_attendues = db.query(models.Matiere).join(
        models.AffectationEnseignant, models.AffectationEnseignant.matiere_id == models.Matiere.id
    ).filter(
        models.AffectationEnseignant.classe_id == classe_id,
        models.Matiere.etablissement_id == admin_courant.etablissement_id,
    ).distinct().all()
    # Liste des matières censées avoir des notes pour cette classe,
    # d'après les affectations enseignant déclarées.

    resultat = {}
    for matiere in matieres_attendues:
        nb_notes = db.query(models.Note).join(models.Eleve).filter(
            models.Eleve.classe_id == classe_id,
            models.Note.matiere_id == matiere.id,
            models.Note.sequence_id == sequence_id,
            models.Note.statut == models.StatutNote.VALIDEE,
        ).count()

        nb_eleves = db.query(models.Eleve).filter(models.Eleve.classe_id == classe_id).count()

        # Une matière est marquée "complète" seulement si TOUS les élèves
        # de la classe ont une note validée pour cette matière/séquence.
        resultat[matiere.nom] = "complete" if nb_notes == nb_eleves and nb_eleves > 0 else "en_attente"

    return resultat


@router.get("/releve-classe/{classe_id}", response_model=dict)
def releve_notes_classe(
    classe_id: int,
    sequence_id: int,
    db: Session = Depends(get_db),
    admin: models.Utilisateur = Depends(auth.exiger_role_admin),
):
    """
    Vue globale demandée par le cahier de charges : "une liste par classe
    recensant toutes les notes sur chaque matière". Renvoie un tableau
    croisé élève x matière, exploitable directement par l'interface admin
    pour l'affichage et l'export Excel (cf. section 10 du document d'analyse).
    """
    classe = db.query(models.Classe).join(models.Section).filter(
        models.Classe.id == classe_id,
        models.Section.etablissement_id == admin.etablissement_id,
    ).first()
    if classe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Classe introuvable")

    eleves = db.query(models.Eleve).filter(models.Eleve.classe_id == classe_id).order_by(
        models.Eleve.nom, models.Eleve.prenom
    ).all()

    matieres = db.query(models.Matiere).join(
        models.AffectationEnseignant, models.AffectationEnseignant.matiere_id == models.Matiere.id
    ).filter(
        models.AffectationEnseignant.classe_id == classe_id,
    ).distinct().all()

    # On charge toutes les notes de la classe/séquence en une seule requête
    # (plutôt qu'une requête par élève x matière) pour rester performant
    # même avec un grand effectif — puis on les indexe en mémoire par
    # (eleve_id, matiere_id) pour un accès instantané dans la boucle d'affichage.
    notes = db.query(models.Note).join(models.Eleve).filter(
        models.Eleve.classe_id == classe_id,
        models.Note.sequence_id == sequence_id,
    ).all()
    index_notes = {(n.eleve_id, n.matiere_id): n.valeur for n in notes}

    tableau = []
    for eleve in eleves:
        ligne = {"eleve": f"{eleve.nom} {eleve.prenom}", "matricule": eleve.matricule}
        for matiere in matieres:
            # None si la note n'existe pas encore : permet à l'interface
            # d'afficher une cellule vide plutôt qu'une fausse valeur 0.
            ligne[matiere.nom] = index_notes.get((eleve.id, matiere.id))
        tableau.append(ligne)

    return {
        "classe": classe.nom,
        "matieres": [m.nom for m in matieres],
        "lignes": tableau,
    }
