# app/models.py
# Ce fichier définit toutes les TABLES de la base de données, sous forme
# de classes Python (ORM = Object-Relational Mapping). Chaque classe
# correspond à une table, chaque attribut à une colonne.
# Ce fichier traduit directement le modèle de données de la section 3
# du document d'analyse.

import enum
# "enum" permet de définir des listes de valeurs fixes (ex: rôle admin/enseignant)
# plutôt que d'accepter n'importe quelle chaîne de caractères.

from datetime import datetime
# Utilisé pour horodater automatiquement certaines lignes (création, modification).

from sqlalchemy import (
    Column, Integer, String, ForeignKey, Enum, DateTime, Float, UniqueConstraint
)
# Column : déclare une colonne de table.
# Integer, String, Float, DateTime, Enum : types de colonnes disponibles.
# ForeignKey : déclare une clé étrangère (lien vers une autre table).
# UniqueConstraint : impose qu'une combinaison de colonnes soit unique.

from sqlalchemy.orm import relationship
# relationship permet de naviguer facilement entre tables liées en Python
# (ex: eleve.classe donne directement l'objet Classe correspondant).

from app.database import Base
# On importe la classe de base créée dans database.py : toutes nos tables
# doivent hériter de cette classe pour être reconnues par SQLAlchemy.


# ---------------------------------------------------------------------------
# ETABLISSEMENT — Le pivot du système multi-tenant : presque toutes les
# autres tables sont rattachées, directement ou indirectement, à un
# établissement. C'est ce qui permet à plusieurs écoles d'utiliser le
# même système sans jamais voir les données des autres.
# ---------------------------------------------------------------------------
class Etablissement(Base):
    __tablename__ = "etablissements"
    # __tablename__ donne le nom exact de la table dans MySQL.

    id = Column(Integer, primary_key=True, index=True)
    # Clé primaire auto-incrémentée. index=True accélère les recherches par id.

    nom = Column(String(255), nullable=False)
    # Nom de l'établissement (ex: "Collège Bilingue Linda et les Anges").
    # nullable=False : ce champ est obligatoire.

    code_inscription = Column(String(20), unique=True, nullable=False)
    # Code unique communiqué aux enseignants pour qu'ils rattachent leur
    # compte au bon établissement lors de l'auto-inscription.

    date_creation = Column(DateTime, default=datetime.utcnow)
    # Horodatage automatique, rempli par défaut à la création de la ligne.

    # Relations Python : permettent d'écrire etablissement.classes,
    # etablissement.utilisateurs, etc. sans écrire de requête SQL manuelle.
    utilisateurs = relationship("Utilisateur", back_populates="etablissement")
    sections = relationship("Section", back_populates="etablissement")
    matieres = relationship("Matiere", back_populates="etablissement")


# ---------------------------------------------------------------------------
# UTILISATEUR — Comptes administrateurs et enseignants.
# ---------------------------------------------------------------------------
class RoleUtilisateur(str, enum.Enum):
    # Enumération des rôles possibles : évite les fautes de frappe
    # ("admni" au lieu de "admin") et documente les valeurs autorisées.
    ADMIN = "admin"
    ENSEIGNANT = "enseignant"


class Utilisateur(Base):
    __tablename__ = "utilisateurs"

    id = Column(Integer, primary_key=True, index=True)

    etablissement_id = Column(Integer, ForeignKey("etablissements.id"), nullable=False)
    # Clé étrangère : chaque utilisateur appartient à un seul établissement.
    # C'est la colonne centrale du filtrage multi-tenant.

    email = Column(String(255), unique=True, nullable=False, index=True)
    # unique=True : deux comptes ne peuvent pas partager le même email.

    mot_de_passe_hash = Column(String(255), nullable=False)
    # On ne stocke JAMAIS un mot de passe en clair : uniquement son empreinte
    # (hash) générée par bcrypt (voir auth.py).

    nom_complet = Column(String(255), nullable=False)

    role = Column(Enum(RoleUtilisateur), nullable=False)
    # Restreint la valeur de ce champ aux deux valeurs de l'énumération ci-dessus.

    actif = Column(Integer, default=1)
    # 1 = compte actif, 0 = désactivé par l'administrateur.
    # (Utilisé pour valider ou bloquer un compte enseignant.)

    etablissement = relationship("Etablissement", back_populates="utilisateurs")
    # Permet d'écrire utilisateur.etablissement pour remonter à l'établissement.


# ---------------------------------------------------------------------------
# SECTION — Francophone / Anglophone (ou tout autre découpage propre
# à un établissement donné).
# ---------------------------------------------------------------------------
class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    etablissement_id = Column(Integer, ForeignKey("etablissements.id"), nullable=False)
    nom = Column(String(100), nullable=False)
    # Ex: "Francophone", "Anglophone" — libre, défini par chaque établissement.

    etablissement = relationship("Etablissement", back_populates="sections")
    classes = relationship("Classe", back_populates="section")


# ---------------------------------------------------------------------------
# CLASSE — 6e, 5e, ... Terminale D, propres à une section.
# ---------------------------------------------------------------------------
class Classe(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False)
    nom = Column(String(100), nullable=False)
    # Ex: "6e", "Terminale C". Aucune valeur codée en dur : chaque
    # établissement définit librement la liste de ses classes.

    section = relationship("Section", back_populates="classes")
    eleves = relationship("Eleve", back_populates="classe")


# ---------------------------------------------------------------------------
# ELEVE — Fiche élève, importée en masse par l'administrateur.
# ---------------------------------------------------------------------------
class Eleve(Base):
    __tablename__ = "eleves"

    id = Column(Integer, primary_key=True, index=True)
    classe_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    nom = Column(String(100), nullable=False)
    prenom = Column(String(100), nullable=False)
    matricule = Column(String(50), unique=True, nullable=False)
    # Identifiant scolaire unique de l'élève, utilisé aussi pour retrouver
    # sa photo et croiser ses notes.

    photo_url = Column(String(500), nullable=True)
    # Chemin/URL vers la photo de l'élève, insérée automatiquement dans
    # le bulletin par l'application desktop. Nullable : peut être ajoutée plus tard.

    classe = relationship("Classe", back_populates="eleves")


# ---------------------------------------------------------------------------
# MATIERE — Catalogue de matières propre à chaque établissement.
# ---------------------------------------------------------------------------
class Matiere(Base):
    __tablename__ = "matieres"

    id = Column(Integer, primary_key=True, index=True)
    etablissement_id = Column(Integer, ForeignKey("etablissements.id"), nullable=False)
    nom = Column(String(150), nullable=False)
    # Ex: "Mathématiques", "Anglais". Défini librement par l'établissement.

    etablissement = relationship("Etablissement", back_populates="matieres")


# ---------------------------------------------------------------------------
# AFFECTATION ENSEIGNANT — Lie un enseignant à une classe et une matière,
# avec LE coefficient qu'il déclare pour cette matière (le cahier de
# charges précise que le coefficient est fourni par l'enseignant).
# ---------------------------------------------------------------------------
class AffectationEnseignant(Base):
    __tablename__ = "affectations_enseignant"

    id = Column(Integer, primary_key=True, index=True)
    enseignant_id = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    classe_id = Column(Integer, ForeignKey("classes.id"), nullable=False)
    matiere_id = Column(Integer, ForeignKey("matieres.id"), nullable=False)
    coefficient = Column(Float, nullable=False, default=1.0)
    # Poids de la matière dans le calcul de la moyenne pondérée (section 6.1
    # du document d'analyse).

    __table_args__ = (
        # Empêche qu'un même enseignant soit affecté deux fois à la même
        # classe + matière (éviterait des coefficients contradictoires).
        UniqueConstraint("enseignant_id", "classe_id", "matiere_id", name="uniq_affectation"),
    )

    # Relations de navigation : permettent d'écrire affectation.classe.nom
    # ou affectation.matiere.nom directement en Python (utilisé par
    # administration.py pour enrichir la réponse envoyée à l'enseignant),
    # sans avoir à écrire une jointure SQL manuelle à chaque fois.
    # Aucun back_populates ici : Classe et Matiere n'ont pas besoin de
    # naviguer dans l'autre sens vers leurs affectations pour l'instant.
    classe = relationship("Classe")
    matiere = relationship("Matiere")
    enseignant = relationship("Utilisateur")


# ---------------------------------------------------------------------------
# TRIMESTRE et SEQUENCE — Structure académique : 3 trimestres, chacun
# composé de 2 séquences (6 séquences au total sur l'année, cf. section 6.4).
# ---------------------------------------------------------------------------
class Trimestre(Base):
    __tablename__ = "trimestres"

    id = Column(Integer, primary_key=True, index=True)
    etablissement_id = Column(Integer, ForeignKey("etablissements.id"), nullable=False)
    numero = Column(Integer, nullable=False)  # 1, 2 ou 3
    annee_scolaire = Column(String(9), nullable=False)  # ex: "2025-2026"

    sequences = relationship("Sequence", back_populates="trimestre")


class Sequence(Base):
    __tablename__ = "sequences"

    id = Column(Integer, primary_key=True, index=True)
    etablissement_id = Column(Integer, ForeignKey("etablissements.id"), nullable=False)
    trimestre_id = Column(Integer, ForeignKey("trimestres.id"), nullable=False)
    numero = Column(Integer, nullable=False)  # 1 à 6 sur l'année
    cloturee = Column(Integer, default=0)
    # 0 = encore ouverte aux modifications des enseignants,
    # 1 = clôturée par l'administrateur (verrouille le bouton "Modifier",
    # cf. section 9 du document d'analyse : "Verrouillage des notes").

    trimestre = relationship("Trimestre", back_populates="sequences")


# ---------------------------------------------------------------------------
# NOTE — La table centrale : une note d'un élève, dans une matière,
# pour une séquence donnée.
# ---------------------------------------------------------------------------
class StatutNote(str, enum.Enum):
    BROUILLON = "brouillon"   # Saisie en cours, pas encore validée.
    VALIDEE = "validee"       # Validée par l'enseignant (bouton "Valider").


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    eleve_id = Column(Integer, ForeignKey("eleves.id"), nullable=False)
    matiere_id = Column(Integer, ForeignKey("matieres.id"), nullable=False)
    sequence_id = Column(Integer, ForeignKey("sequences.id"), nullable=False)
    enseignant_id = Column(Integer, ForeignKey("utilisateurs.id"), nullable=False)
    # On garde une trace de QUI a saisi la note (traçabilité, cf. section 10
    # "Journal d'activité" du document d'analyse).

    valeur = Column(Float, nullable=False)
    # La note elle-même. La validation "doit être comprise entre 0 et 20"
    # (section 9, "Notes hors barème") sera faite dans schemas.py avec Pydantic.

    statut = Column(Enum(StatutNote), default=StatutNote.BROUILLON)

    date_modification = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # onupdate : cette colonne se remet à jour automatiquement à chaque
    # modification de la ligne, sans code supplémentaire à écrire.

    __table_args__ = (
        # Un élève ne peut avoir qu'UNE SEULE note par matière et par séquence
        # (la modification se fait par UPDATE, pas par ajout d'une nouvelle ligne).
        UniqueConstraint("eleve_id", "matiere_id", "sequence_id", name="uniq_note_eleve_matiere_sequence"),
    )


# ---------------------------------------------------------------------------
# MAQUETTE BULLETIN — Le modèle Word propre à chaque établissement,
# utilisé par l'application desktop pour générer les bulletins (section 7).
# ---------------------------------------------------------------------------
class MaquetteBulletin(Base):
    __tablename__ = "maquettes_bulletin"

    id = Column(Integer, primary_key=True, index=True)
    etablissement_id = Column(Integer, ForeignKey("etablissements.id"), nullable=False)
    nom = Column(String(150), nullable=False)
    # Ex: "Bulletin Francophone", pour gérer plusieurs maquettes par établissement.

    chemin_fichier = Column(String(500), nullable=False)
    # Chemin du fichier .docx modèle stocké sur le serveur (téléversé par l'admin).

    date_upload = Column(DateTime, default=datetime.utcnow)
