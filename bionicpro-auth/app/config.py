from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    keycloak_url: str = "http://localhost:8180"
    keycloak_internal_url: str = "http://keycloak:8080"
    keycloak_realm: str = "reports-realm"
    keycloak_client_id: str = "reports-frontend"
    keycloak_client_secret: str = "bionicpro-auth-client-secret"

    auth_public_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    redirect_uri: str = "http://localhost:8000/auth/callback"

    session_cookie_name: str = "bionicpro_session"
    session_ttl_seconds: int = 1800  # > access_token (120s)
    cookie_secure: bool = False  # True behind HTTPS; False for local HTTP
    cookie_samesite: str = "lax"

    token_encryption_key: str = "change-me-32-byte-key-for-fernet!!"
    database_url: str = "postgresql://auth_user:auth_password@auth_db:5432/auth_db"

    reports_api_url: str = "http://reports-api:8001"

    yandex_userinfo_url: str = "https://login.yandex.ru/info?format=json"


settings = Settings()
