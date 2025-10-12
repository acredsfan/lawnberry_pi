from enum import Enum
from typing import Optional, Dict
from pydantic import BaseModel, Field, ConfigDict


class RemoteAccessProvider(str, Enum):
    CLOUDFLARE = "cloudflare"
    NGROK = "ngrok"
    CUSTOM = "custom"
    DISABLED = "disabled"


class CloudflareConfig(BaseModel):
    account_id: Optional[str] = None
    tunnel_name: Optional[str] = None
    credentials_file: Optional[str] = None  # path to JSON credentials
    hostname: Optional[str] = None


class NgrokConfig(BaseModel):
    authtoken: Optional[str] = None
    region: Optional[str] = None  # e.g., us, eu, ap
    edge: Optional[str] = None    # reserved domain or edge config


class CustomTunnelConfig(BaseModel):
    command: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)


class RemoteAccessConfig(BaseModel):
    provider: RemoteAccessProvider = RemoteAccessProvider.DISABLED
    enabled: bool = False
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    ngrok: NgrokConfig = Field(default_factory=NgrokConfig)
    custom: CustomTunnelConfig = Field(default_factory=CustomTunnelConfig)

    model_config = ConfigDict(use_enum_values=True)
