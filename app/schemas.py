# app/schemas.py
# Les "schemas" définissent la FORME des données que l'API accepte en entrée
# (ex: le JSON envoyé par le formulaire de connexion) et renvoie en sortie.
# Contrairement à models.py (qui décrit les TABLES en base de données),
# ce fichier décrit les DONNEES ECHANGEES avec les clients (Web et Desktop).
# Séparer les deux évite, par exemple, de renvoyer accidentellement le
# mot_de_passe_hash d'un utilisateur dans une réponse API.

from pydantic import BaseModel, EmailStr, Field
# BaseModel : classe de base pour tout schéma Pydantic.
# EmailStr : type qui valide automatiquement le format d'une adresse email.
# Field : permet d'ajouter des contraintes supplémentaires à un champ
#   (ex: valeur minimale/maximale).

from typing import Optional
# Optional indique qu'un champ peut être absent (None).

from datetime import datetime
from app.models import RoleUtilisateur, StatutNote
# On réutilise les mêmes énumérations que dans models.py pour rester cohérent
# entre la base de données et l'API.


# ---------------------------------------------------------------------------
# UTILISATEUR — création de compte, connexion, réponse publique.
# ---------------------------------------------------------------------------
class UtilisateurCreation(BaseModel):
    # Schéma attendu quand un enseignant crée son compte (auto-inscription).
    email: EmailStr
    mot_de_passe: str = Field(min_length=8)
    # min_length=8 : refuse un mot de passe trop court dès la validation,
    # avant même d'atteindre la logique métier.
    nom_complet: str
    code_etablissement: str
    # L'enseignant fournit le code d'inscription de son établissement
    # (cf. Etablissement.code_inscription dans models.py) pour être
    # automatiquement rattaché au bon etablissement_id.


class UtilisateurConnexion(BaseModel):
    # Schéma attendu pour se connecter (endpoint /auth/login).
    email: EmailStr
    mot_de_passe: str


class UtilisateurPublic(BaseModel):
    # Schéma renvoyé par l'API : ne contient JAMAIS mot_de_passe_hash.
    id: int
    email: EmailStr
    nom_complet: str
    role: RoleUtilisateur
    etablissement_id: int
    actif: int

    class Config:
        # Autorise Pydantic à lire directement un objet SQLAlchemy
        # (model.attribut) plutôt qu'un dictionnaire — indispensable
        # pour convertir facilement nos modèles en réponses API.
        from_attributes = True


class Token(BaseModel):
    # Schéma renvoyé après une connexion réussie.
    access_token: str
    token_type: str = "bearer"
    # "bearer" est la convention standard indiquant comment le client doit
    # envoyer le token dans les requêtes suivantes (en-tête Authorization).


# ---------------------------------------------------------------------------
# ELEVE — création (import en masse) et réponse.
# ---------------------------------------------------------------------------
class EleveCreation(BaseModel):
    nom: str
    prenom: str
    matricule: str
    classe_id: int


class ElevePublic(BaseModel):
    id: int
    nom: str
    prenom: str
    matricule: str
    classe_id: int
    photo_url: Optional[str] = None
    # Optional avec valeur par défaut None : la photo peut être absente
    # tant qu'elle n'a pas été ajoutée par l'établissement.

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# NOTE — saisie par l'enseignant et réponse.
# ---------------------------------------------------------------------------
class NoteCreation(BaseModel):
    eleve_id: int
    matiere_id: int
    sequence_id: int
    valeur: float = Field(ge=0, le=20)
    # ge=0 (greater or equal) et le=20 (less or equal) : empêchent à la
    # racine toute note hors barème 0-20 (cf. section 9 du document
    # d'analyse, "Notes hors barème"). Le barème pourra être rendu
    # configurable par établissement dans une version ultérieure.


class NotePublic(BaseModel):
    id: int
    eleve_id: int
    matiere_id: int
    sequence_id: int
    enseignant_id: int
    valeur: float
    statut: StatutNote
    date_modification: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# LISTE DE NOTES POUR UN TABLEAU DE SAISIE (section → classe → matière)
# Ce schéma correspond exactement au tableau à deux colonnes décrit dans
# le cahier de charges : nom de l'élève / note à saisir.
# ---------------------------------------------------------------------------
class LigneSaisieNote(BaseModel):
    eleve_id: int
    valeur: float = Field(ge=0, le=20)


class SaisieNotesLot(BaseModel):
    # Schéma envoyé en une seule requête quand l'enseignant clique sur
    # "Valider" : toutes les notes de sa classe/matière/séquence d'un coup,
    # plutôt qu'un appel réseau par élève (plus rapide, plus fiable).
    classe_id: int
    matiere_id: int
    sequence_id: int
    coefficient: float = Field(gt=0)
    # gt=0 (greater than) : un coefficient nul ou négatif n'a pas de sens.
    lignes: list[LigneSaisieNote]


# ---------------------------------------------------------------------------
# SECTION / CLASSE / MATIERE — schémas de configuration d'établissement,
# utilisés par les endpoints du router administration.py.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ETABLISSEMENT — utilisé par l'application desktop pour personnaliser
# l'en-tête des bulletins générés (nom réel, pas une valeur codée en dur).
# ---------------------------------------------------------------------------
class EtablissementPublic(BaseModel):
    id: int
    nom: str
    code_inscription: str

    class Config:
        from_attributes = True


class SectionCreation(BaseModel):
    nom: str  # Ex: "Francophone", "Anglophone"


class SectionPublic(BaseModel):
    id: int
    nom: str
    etablissement_id: int

    class Config:
        from_attributes = True


class ClasseCreation(BaseModel):
    nom: str  # Ex: "6e", "Terminale C"
    section_id: int


class ClassePublic(BaseModel):
    id: int
    nom: str
    section_id: int

    class Config:
        from_attributes = True


class MatiereCreation(BaseModel):
    nom: str  # Ex: "Mathématiques"


class MatierePublic(BaseModel):
    id: int
    nom: str
    etablissement_id: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# AFFECTATION — lie un enseignant à une classe/matière avec un coefficient.
# ---------------------------------------------------------------------------
class AffectationCreation(BaseModel):
    enseignant_id: int
    classe_id: int
    matiere_id: int
    coefficient: float = Field(gt=0)


class AffectationPublic(BaseModel):
    id: int
    enseignant_id: int
    classe_id: int
    matiere_id: int
    coefficient: float

    class Config:
        from_attributes = True


class AffectationDetaillee(BaseModel):
    # Version "enrichie" avec les noms lisibles, renvoyée à l'enseignant
    # pour peupler directement ses menus déroulants sans requête supplémentaire.
    id: int
    classe_id: int
    classe_nom: str
    matiere_id: int
    matiere_nom: str
    coefficient: float


class AffectationClasseDetaillee(BaseModel):
    # Utilisée par l'application desktop : donne le coefficient de chaque
    # matière enseignée dans une classe, nécessaire au calcul de la
    # moyenne pondérée (cf. section 6.1 du document d'analyse).
    matiere_id: int
    matiere_nom: str
    coefficient: float
    enseignant_nom: str


# ---------------------------------------------------------------------------
# TRIMESTRE / SEQUENCE
# ---------------------------------------------------------------------------
class TrimestreCreation(BaseModel):
    numero: int = Field(ge=1, le=3)
    annee_scolaire: str  # Ex: "2025-2026"


class TrimestrePublic(BaseModel):
    id: int
    numero: int
    annee_scolaire: str

    class Config:
        from_attributes = True


class SequenceCreation(BaseModel):
    trimestre_id: int
    numero: int = Field(ge=1, le=6)


class SequencePublic(BaseModel):
    id: int
    trimestre_id: int
    numero: int
    cloturee: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# MAQUETTE DE BULLETIN
# ---------------------------------------------------------------------------
class MaquettePublic(BaseModel):
    # Ne contient volontairement PAS chemin_fichier : c'est un détail de
    # stockage interne au serveur, sans intérêt (et potentiellement
    # sensible) pour le client web ou desktop, qui téléchargent le
    # fichier via l'endpoint dédié /fichier plutôt que d'accéder au chemin
    # disque directement.
    id: int
    nom: str
    date_upload: datetime

    class Config:
        from_attributes = True
