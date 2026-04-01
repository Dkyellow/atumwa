from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # WhatsApp / Meta
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "atumwa_webhook_verify_token"

    # Database
    database_url: str = "postgresql+asyncpg://atumwa:password@localhost:5432/atumwa_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # App
    app_env: str = "development"
    secret_key: str = "change_me"

    # EcoCash (Phase 3)
    ecocash_merchant_code: str = ""
    ecocash_api_key: str = ""

    @property
    def whatsapp_api_url(self) -> str:
        return f"https://graph.facebook.com/v19.0/{self.whatsapp_phone_number_id}/messages"


settings = Settings()
