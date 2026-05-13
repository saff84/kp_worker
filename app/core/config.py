from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Parser KP"
    app_env: str = "dev"
    secret_key: str = "change-me"
    # Comma-separated emails for admin API + UI tab (case-insensitive).
    admin_emails: str = "admin@local"
    # If true, seed demo users + sample catalog when DB is empty (set false on public servers).
    seed_demo_users: bool = True
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/parser_kp"
    redis_url: str = "redis://localhost:6379/0"
    rq_queue: str = "default"
    storage_root: str = "./storage"
    hybrid_enabled: bool = True
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "catalog_products"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def admin_email_set(self) -> set[str]:
        parts = [p.strip().lower() for p in self.admin_emails.split(",") if p.strip()]
        return set(parts)

    def is_admin_email(self, email: str) -> bool:
        return email.strip().lower() in self.admin_email_set()


settings = Settings()
