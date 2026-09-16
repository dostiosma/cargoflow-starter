from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://cargoflow:cargoflow@localhost:5432/cargoflow"
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "change-me-in-production-use-a-real-random-secret-key"
    jwt_expiration_minutes: int = 30
    jwt_algorithm: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
