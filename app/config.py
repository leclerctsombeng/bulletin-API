# app/config.py
# Ce fichier centralise TOUTE la configuration de l'application.
# Objectif : ne jamais écrire une valeur "en dur" (mot de passe, secret...)
# ailleurs dans le code. Tout passe par des variables d'environnement,
# ce qui permet de changer la config entre développement et production
# sans toucher au code source.

import os
# "os" est un module natif de Python qui permet de lire les variables
# d'environnement du système (os.getenv).

from pydantic_settings import BaseSettings
# BaseSettings (de pydantic) permet de déclarer la configuration comme une
# classe Python typée : Pydantic va automatiquement lire les variables
# d'environnement correspondantes et valider leur type (str, int, etc.).


class Settings(BaseSettings):
    # URL de connexion à la base de données MySQL.
    # Format attendu : mysql+pymysql://utilisateur:motdepasse@hote:port/nom_bdd
    # Valeur par défaut fournie pour pouvoir démarrer immédiatement en local.
    database_url: str = "mysql+pymysql://root:root@localhost:3306/bulletin_scolaire"

    # Clé secrète utilisée pour signer les tokens JWT (authentification).
    # ATTENTION : en production, cette valeur DOIT être remplacée par une
    # chaîne aléatoire longue et gardée secrète (jamais dans le code versionné).
    secret_key: str = "CHANGER_CETTE_CLE_EN_PRODUCTION_avec_une_valeur_aleatoire_longue"

    # Algorithme cryptographique utilisé pour signer le JWT.
    # HS256 est un standard simple et largement supporté.
    algorithm: str = "HS256"

    # Durée de validité d'un token de connexion, en minutes.
    # Après ce délai, l'enseignant/admin devra se reconnecter.
    access_token_expire_minutes: int = 480  # 8 heures, adapté à une journée de travail

    class Config:
        # Indique à Pydantic de lire aussi un fichier ".env" s'il existe,
        # en plus des vraies variables d'environnement du système.
        env_file = ".env"


# On crée une seule instance de la configuration, réutilisée partout
# dans l'application (pattern "singleton" simple).
settings = Settings()
