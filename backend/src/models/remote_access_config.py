from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RemoteAccessProvider(str, Enum):
    CLOUDFLARE = "cloudflare"
    NGROK = "ngrok"
    CUSTOM = "custom"
    DISABLED = "disabled"


class CloudflareConfig(BaseModel):
    account_id: str | None = None
    tunnel_name: str | None = None
    credentials_file: str | None = None  # path to JSON credentials
    hostname: str | None = None


class NgrokConfig(BaseModel):
    authtoken: str | None = None
    region: str | None = None  # e.g., us, eu, ap
    edge: str | None = None  # reserved domain or edge config


class CustomTunnelConfig(BaseModel):
    command: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class RemoteAccessConfig(BaseModel):
    provider: RemoteAccessProvider = RemoteAccessProvider.DISABLED
    enabled: bool = False
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    ngrok: NgrokConfig = Field(default_factory=NgrokConfig)
    custom: CustomTunnelConfig = Field(default_factory=CustomTunnelConfig)

    model_config = ConfigDict(use_enum_values=True)
