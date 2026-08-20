# app/main.py
# Point d'entrée de l'application : crée l'objet FastAPI, crée les tables
# en base de données si elles n'existent pas encore, et branche tous les
# routers (groupes d'endpoints) définis dans le dossier routers/.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# CORSMiddleware autorise le navigateur (application web, servie depuis
# un autre nom de domaine/port que l'API) à appeler cette API sans être
# bloqué par la politique de sécurité par défaut des navigateurs.

from app.database import Base, engine
from app.routers import auth, eleves, notes, administration, maquettes
# On importe les routers créés précédemment pour les rattacher à l'app.

# Crée physiquement les tables en base de données à partir des classes
# définies dans models.py, si elles n'existent pas déjà.
# NB : en production, on préférera un outil de migration (Alembic) pour
# faire évoluer le schéma sans perdre de données ; create_all() convient
# pour démarrer le développement rapidement.
Base.metadata.create_all(bind=engine)

# Création de l'application FastAPI, avec un titre et une description
# qui apparaîtront automatiquement dans la documentation Swagger
# générée sur /docs.
app = FastAPI(
    title="API Bulletins Scolaires",
    description="API centrale consommée par l'application web (enseignants/admin) "
                 "et l'application desktop (calculs et génération des bulletins).",
    version="0.1.0",
)

# Configuration CORS : en développement, on autorise toutes les origines
# ("*") pour simplifier les tests. En production, cette liste devra être
# restreinte au(x) nom(s) de domaine réel(s) de l'application web.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Branchement des routers : chaque router apporte son propre préfixe
# d'URL (défini dans le fichier correspondant, ex: "/auth", "/eleves").
app.include_router(auth.router)
app.include_router(eleves.router)
app.include_router(notes.router)
app.include_router(administration.router)
app.include_router(maquettes.router)


@app.get("/", tags=["Santé"])
def verifier_etat():
    """
    Endpoint simple, sans authentification, pour vérifier que l'API
    est démarrée et joignable (utile pour un test rapide ou un
    outil de supervision).
    """
    return {"statut": "API opérationnelle"}
