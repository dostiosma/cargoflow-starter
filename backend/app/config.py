from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://cargoflow:cargoflow@localhost:5432/cargoflow"
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "change-me-in-production-use-a-real-random-secret-key"
    jwt_expiration_minutes: int = 30
    jwt_algorithm: str = "HS256"
    # n8n (seccion 9 del master spec): URL base de los webhooks y secreto compartido
    # con la credencial Header Auth de n8n. Si alguno esta vacio, el aviso de
    # pedido creado no se envia (ver app/n8n_client.py).
    n8n_webhook_url: str = ""
    n8n_webhook_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
