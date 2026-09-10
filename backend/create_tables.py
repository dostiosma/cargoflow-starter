from app.database import Base, engine
from app import models  # noqa: F401 - registra las clases en Base.metadata

Base.metadata.create_all(bind=engine)
print("Tablas creadas (o ya existentes).")
