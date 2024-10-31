import pydantic_settings
from pydantic import SecretStr


class Settings(pydantic_settings.BaseSettings):
    """
    класс Settings, который является подклассом BaseSettings
    """
    bot_token: SecretStr
    model_config = pydantic_settings.SettingsConfigDict(
        env_file='.env'
        ,
        env_file_encoding='utf-8'
    )

config = Settings()