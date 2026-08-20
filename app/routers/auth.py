# app/routers/auth.py
# Ce fichier regroupe les endpoints publics d'authentification :
# création de compte (enseignant) et connexion (admin + enseignant).
# "Router" = un mini-groupe d'endpoints que l'on branchera sur l'app
# principale dans main.py, pour garder le code organisé par domaine.

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
# OAuth2PasswordRequestForm : lit automatiquement un formulaire standard
# (username/password) envoyé par le client lors de la connexion ; c'est
# le format attendu par la convention OAuth2 utilisée par oauth2_scheme.

from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

# Crée un routeur dédié à l'authentification, avec un préfixe d'URL commun
# et une étiquette utilisée dans la documentation Swagger auto-générée.
router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/inscription", response_model=schemas.UtilisateurPublic)
def inscription(donnees: schemas.UtilisateurCreation, db: Session = Depends(get_db)):
    """
    Permet à un enseignant de créer son propre compte (auto-inscription),
    en fournissant le code d'inscription de son établissement.
    response_model=UtilisateurPublic garantit que le mot_de_passe_hash
    ne sera JAMAIS renvoyé dans la réponse HTTP, même par erreur.
    """
    etablissement = db.query(models.Etablissement).filter(
        models.Etablissement.code_inscription == donnees.code_etablissement
    ).first()
    # Recherche l'établissement correspondant au code fourni.

    if etablissement is None:
        # Le code d'établissement n'existe pas : on refuse la création
        # plutôt que de créer un compte "orphelin".
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="Code établissement invalide")

    email_existant = db.query(models.Utilisateur).filter(
        models.Utilisateur.email == donnees.email
    ).first()
    if email_existant is not None:
        # Empêche deux comptes avec le même email (la contrainte unique en
        # base le ferait aussi, mais un message d'erreur clair est préférable
        # à une erreur SQL brute renvoyée au client).
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Cet email est déjà utilisé")

    nouvel_utilisateur = models.Utilisateur(
        etablissement_id=etablissement.id,
        email=donnees.email,
        mot_de_passe_hash=auth.hacher_mot_de_passe(donnees.mot_de_passe),
        # On ne stocke jamais donnees.mot_de_passe tel quel : uniquement
        # son empreinte bcrypt.
        nom_complet=donnees.nom_complet,
        role=models.RoleUtilisateur.ENSEIGNANT,
        # L'auto-inscription ne peut créer QUE des comptes enseignants ;
        # un compte admin doit être créé par un autre moyen (script initial
        # ou promotion manuelle), pour éviter qu'un tiers ne s'auto-désigne admin.
        actif=1,
    )
    db.add(nouvel_utilisateur)
    # Prépare l'insertion (encore en mémoire, pas encore écrite en base).
    db.commit()
    # Écrit réellement la nouvelle ligne en base de données.
    db.refresh(nouvel_utilisateur)
    # Recharge l'objet depuis la base pour récupérer son id auto-généré.

    return nouvel_utilisateur


@router.post("/login", response_model=schemas.Token)
def connexion(
    identifiants: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Vérifie l'email et le mot de passe, puis renvoie un token JWT si
    les identifiants sont corrects. C'est ce token que le client (Web
    ou Desktop) devra ensuite joindre à chaque requête protégée.
    """
    utilisateur = db.query(models.Utilisateur).filter(
        models.Utilisateur.email == identifiants.username
        # OAuth2PasswordRequestForm nomme le champ "username" même si,
        # ici, il contient un email : c'est la convention du standard.
    ).first()

    identifiants_invalides = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email ou mot de passe incorrect",
    )

    if utilisateur is None:
        raise identifiants_invalides

    if not auth.verifier_mot_de_passe(identifiants.password, utilisateur.mot_de_passe_hash):
        # Compare le mot de passe fourni à l'empreinte stockée, sans jamais
        # déchiffrer cette dernière (bcrypt est un hachage à sens unique).
        raise identifiants_invalides

    if utilisateur.actif == 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="Ce compte a été désactivé par l'administration")

    token = auth.creer_token_acces(donnees={"sub": str(utilisateur.id)})
    # On encode uniquement l'id utilisateur dans le token ; le rôle et
    # l'établissement seront relus depuis la base à chaque requête
    # (obtenir_utilisateur_courant), ce qui permet de révoquer un accès
    # immédiatement en désactivant le compte, sans attendre l'expiration du token.

    return schemas.Token(access_token=token)


@router.get("/moi", response_model=schemas.UtilisateurPublic)
def mon_profil(
    utilisateur_courant: models.Utilisateur = Depends(auth.obtenir_utilisateur_courant),
):
    """
    Renvoie les informations du compte actuellement connecté (id, rôle,
    établissement...). Utilisé côté frontend juste après la connexion
    pour savoir vers quel tableau de bord rediriger (admin ou enseignant),
    puisque /auth/login ne renvoie qu'un token, sans détail sur son titulaire.
    """
    return utilisateur_courant
