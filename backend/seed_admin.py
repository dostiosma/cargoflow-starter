import os

from app.auth import hash_password
from app.database import SessionLocal
from app.models import User, UserRole

password = os.environ.get("SEED_ADMIN_PASSWORD")
if not password:
    raise RuntimeError("SEED_ADMIN_PASSWORD no está definida")

db = SessionLocal()
user = User(
    email="admin@example.com",
    password_hash=hash_password(password),
    role=UserRole.admin,
)
db.add(user)
db.commit()
print(f"Usuario creado: {user.email} / id={user.id}")
db.close()
