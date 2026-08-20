# app/auth.py
# Ce fichier regroupe toute la logique de sécurité :
#   1) hacher/vérifier les mots de passe (jamais de stockage en clair)
#   2) créer et lire les tokens JWT
#   3) fournir la dependency FastAPI qui identifie "l'utilisateur courant"
#      et vérifie ses droits (admin vs enseignant) sur chaque endpoint protégé.

from datetime import datetime, timedelta
# timedelta permet de calculer une date d'expiration ("maintenant + X minutes").

from jose import JWTError, jwt
# La librairie "python-jose" fournit les fonctions de création/lecture
# de tokens JWT signés.

from passlib.context import CryptContext
# passlib fournit une API simple pour le hachage sécurisé de mots de passe.

from fastapi import Depends, HTTPException, status
# Depends : mécanisme d'injection de dépendances de FastAPI.
# HTTPException : permet de renvoyer une erreur HTTP propre (ex: 401, 403).
# status : constantes lisibles pour les codes HTTP (status.HTTP_401_UNAUTHORIZED).

from fastapi.security import OAuth2PasswordBearer
# Extrait automatiquement le token JWT de l'en-tête "Authorization: Bearer ..."
# envoyé par le client (Web ou Desktop) à chaque requête protégée.

from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models

# Contexte de hachage : bcrypt est l'algorithme recommandé pour les mots
# de passe (lent par conception, ce qui ralentit les attaques par force brute).
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Déclare le endpoint utilisé par les clients pour obtenir un token :
# c'est purement déclaratif ici, la vraie logique est dans routers/auth.py.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    """Transforme un mot de passe en clair en une empreinte bcrypt irréversible."""
    return pwd_context.hash(mot_de_passe)


def verifier_mot_de_passe(mot_de_passe_clair: str, mot_de_passe_hash: str) -> bool:
    """Compare un mot de passe saisi à l'empreinte stockée en base."""
    return pwd_context.verify(mot_de_passe_clair, mot_de_passe_hash)


def creer_token_acces(donnees: dict) -> str:
    """
    Génère un token JWT signé contenant les informations passées en argument
    (ex: id utilisateur, rôle, établissement) et une date d'expiration.
    """
    a_encoder = donnees.copy()
    # On copie le dictionnaire pour ne pas modifier l'original par effet de bord.

    expiration = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    # Calcule l'instant précis où le token deviendra invalide.

    a_encoder.update({"exp": expiration})
    # "exp" est le nom de champ standard JWT pour l'expiration : les
    # librairies JWT le reconnaissent et rejettent automatiquement un
    # token expiré.

    return jwt.encode(a_encoder, settings.secret_key, algorithm=settings.algorithm)
    # Signe le tout avec la clé secrète : impossible de falsifier un token
    # sans connaître cette clé.


def obtenir_utilisateur_courant(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Utilisateur:
    """
    Dependency FastAPI : à placer sur chaque endpoint protégé.
    Lit le token JWT envoyé par le client, vérifie sa signature et son
    expiration, puis retrouve l'utilisateur correspondant en base.
    Toute requête sans token valide est bloquée avant même d'exécuter
    le code de l'endpoint.
    """
    exception_identification = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Impossible de vérifier les identifiants",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Décode et vérifie le token avec la même clé secrète qui a servi
        # à le signer ; lève une exception si le token est invalide/expiré.
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        utilisateur_id: str = payload.get("sub")
        # "sub" (subject) est le champ standard JWT identifiant le titulaire
        # du token ; on y a stocké l'id utilisateur lors de la création du token.
        if utilisateur_id is None:
            raise exception_identification
    except JWTError:
        # Regroupe toutes les erreurs possibles de la librairie jose
        # (signature invalide, token expiré, format incorrect...).
        raise exception_identification

    utilisateur = db.query(models.Utilisateur).filter(
        models.Utilisateur.id == int(utilisateur_id)
    ).first()
    # Recherche l'utilisateur correspondant dans la base de données.

    if utilisateur is None or utilisateur.actif == 0:
        # Vérifie aussi que le compte n'a pas été désactivé par l'administrateur
        # depuis l'émission du token (cf. section 5.2, gestion des comptes).
        raise exception_identification

    return utilisateur


def exiger_role_admin(
    utilisateur: models.Utilisateur = Depends(obtenir_utilisateur_courant),
) -> models.Utilisateur:
    """
    Dependency supplémentaire à empiler sur les endpoints réservés à
    l'administration (ex: import des listes d'élèves, gestion des comptes).
    """
    if utilisateur.role != models.RoleUtilisateur.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action réservée à l'administrateur de l'établissement",
        )
    return utilisateur
