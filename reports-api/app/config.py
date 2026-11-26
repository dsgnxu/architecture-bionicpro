from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_database: str = "bionicpro"
    clickhouse_user: str = "default"
    clickhouse_password: str = "clickhouse"
    etl_pipeline: str = "bionicpro_reports_etl"

    s3_endpoint: str = "http://minio:4566"
    s3_access_key: str = "test"
    s3_secret_key: str = "test"
    s3_bucket: str = "bionicpro-reports"
    s3_region: str = "us-east-1"
    cdn_public_url: str = "http://localhost:8082"


settings = Settings()
