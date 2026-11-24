from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_database: str = "bionicpro"
    clickhouse_user: str = "default"
    clickhouse_password: str = "clickhouse"
    etl_pipeline: str = "bionicpro_reports_etl"


settings = Settings()
