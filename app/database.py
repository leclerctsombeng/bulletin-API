# app/database.py
# Ce fichier configure la connexion à la base de données et fournit
# les outils que le reste de l'application utilisera pour dialoguer avec elle.

from sqlalchemy import create_engine
# create_engine crée l'objet qui gère le "tuyau" de communication
# entre Python et le serveur MySQL (pool de connexions, etc.).

from sqlalchemy.orm import sessionmaker, declarative_base
# sessionmaker : fabrique de "sessions" (une session = une conversation
#   avec la base de données pendant une requête HTTP).
# declarative_base : fonction qui crée une classe de base dont hériteront
#   tous nos modèles (tables) définis dans models.py.

from app.config import settings
# On importe la configuration créée précédemment pour récupérer l'URL
# de connexion à la base de données.

# Création du moteur de connexion à la base de données.
# pool_pre_ping=True : avant chaque requête, SQLAlchemy vérifie que la
# connexion est toujours active ; évite les erreurs si MySQL a coupé
# une connexion inactive depuis longtemps (cas fréquent en production).
engine = create_engine(settings.database_url, pool_pre_ping=True)

# SessionLocal est une "fabrique" : chaque appel à SessionLocal()
# crée une nouvelle session indépendante pour une requête HTTP donnée.
# autocommit=False : les changements ne sont écrits en base que si on
#   appelle explicitement session.commit() (sécurité contre les écritures
#   accidentelles).
# autoflush=False : SQLAlchemy n'envoie pas les changements en base tant
#   qu'on ne le lui demande pas explicitement (meilleure prévisibilité).
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base est la classe mère dont hériteront tous les modèles (tables).
# C'est elle qui permet à SQLAlchemy de savoir quelles classes Python
# correspondent à quelles tables SQL.
Base = declarative_base()


def get_db():
    """
    Fonction "dependency" utilisée par FastAPI pour fournir une session
    de base de données à chaque endpoint qui en a besoin, et la fermer
    automatiquement une fois la requête terminée (même en cas d'erreur).
    """
    db = SessionLocal()
    # On ouvre une nouvelle session pour cette requête HTTP précise.
    try:
        yield db
        # "yield" renvoie la session à l'endpoint qui l'a demandée,
        # puis met la fonction en pause jusqu'à la fin de la requête.
    finally:
        db.close()
        # Une fois la requête terminée (succès ou erreur), on ferme
        # systématiquement la session pour libérer la connexion.
