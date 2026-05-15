from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    supabase_url: str
    supabase_anon_key: str
    supabase_jwt_secret: str

    google_client_id: str
    google_client_secret: str
    google_project_id: str
    google_pubsub_service_account_email: str

    encryption_key: str
    secret_key: str
    anthropic_api_key: str = ""
    sentry_dsn: str = ""

    environment: str = "development"
    backend_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
