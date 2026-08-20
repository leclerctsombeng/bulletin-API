# scripts/amorcer_etablissement.py
# Script à lancer UNE SEULE FOIS, manuellement, pour créer le tout premier
# établissement et son compte administrateur.
# Pourquoi un script séparé plutôt qu'un endpoint API ? Parce que
# l'endpoint /auth/inscription (routers/auth.py) ne peut créer QUE des
# comptes enseignants par design : ouvrir un endpoint public capable de
# créer un compte admin serait une faille de sécurité (n'importe qui
# pourrait se déclarer administrateur). La création du compte admin
# initial est donc un geste volontaire de l'opérateur du système, exécuté
# directement sur le serveur.
#
# Utilisation :
#   cd bulletin_api
#   python scripts/amorcer_etablissement.py

import sys
import os

# Ajoute le dossier parent au chemin de recherche des modules, pour que
# "from app import ..." fonctionne même en lançant ce script directement
# depuis le dossier scripts/.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine
from app import models, auth

# S'assure que les tables existent avant d'essayer d'y insérer des données
# (utile si ce script est lancé avant même le premier démarrage de l'API).
Base.metadata.create_all(bind=engine)


def amorcer():
    db = SessionLocal()
    try:
        nom_etablissement = input("Nom de l'établissement : ").strip()
        code_inscription = input("Code d'inscription (communiqué aux enseignants) : ").strip()
        email_admin = input("Email du compte administrateur : ").strip()
        mot_de_passe_admin = input("Mot de passe administrateur (8 caractères minimum) : ").strip()
        nom_admin = input("Nom complet de l'administrateur : ").strip()

        if len(mot_de_passe_admin) < 8:
            print("Erreur : le mot de passe doit contenir au moins 8 caractères.")
            return

        etablissement_existant = db.query(models.Etablissement).filter(
            models.Etablissement.code_inscription == code_inscription
        ).first()
        if etablissement_existant is not None:
            print("Erreur : ce code d'inscription est déjà utilisé par un autre établissement.")
            return

        # Création de l'établissement.
        etablissement = models.Etablissement(nom=nom_etablissement, code_inscription=code_inscription)
        db.add(etablissement)
        db.commit()
        db.refresh(etablissement)
        # refresh() est nécessaire ici pour récupérer etablissement.id,
        # utilisé juste après pour créer le compte admin.

        # Création du compte administrateur, directement avec le rôle ADMIN
        # (impossible à obtenir via l'auto-inscription publique).
        admin = models.Utilisateur(
            etablissement_id=etablissement.id,
            email=email_admin,
            mot_de_passe_hash=auth.hacher_mot_de_passe(mot_de_passe_admin),
            nom_complet=nom_admin,
            role=models.RoleUtilisateur.ADMIN,
            actif=1,
        )
        db.add(admin)
        db.commit()

        print(f"\nÉtablissement '{nom_etablissement}' créé avec succès.")
        print(f"Code d'inscription à communiquer aux enseignants : {code_inscription}")
        print(f"Compte administrateur créé : {email_admin}")

    finally:
        db.close()
        # Fermeture systématique de la session, comme dans get_db() (database.py).


if __name__ == "__main__":
    # Ce bloc ne s'exécute que si le fichier est lancé directement
    # (python scripts/amorcer_etablissement.py), pas s'il est importé
    # ailleurs — bonne pratique standard pour les scripts exécutables.
    amorcer()
