from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth

app = FastAPI(title="CargoFlow API", version="0.1.0")

# CORS explicito -- ver seccion 10 del master spec. Ajustar origenes reales antes de produccion.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health")
def health():
    return {"status": "ok"}

from app.routers import orders

app.include_router(orders.router)

from app.routers import vehicles

app.include_router(vehicles.router)

from app.routers import drivers

app.include_router(drivers.router)
