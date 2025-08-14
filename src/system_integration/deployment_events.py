"""Deployment Events module providing structured lifecycle event payloads."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from ..communication.client import MQTTClient


class DeploymentLifecycleEvent(str, Enum):
    UPDATE_AVAILABLE = "update_available"
    DEPLOYMENT_STARTED = "deployment_started"
    DEPLOYMENT_SUCCESS = "deployment_success"
    DEPLOYMENT_FAILURE = "deployment_failure"
    ROLLBACK_SUCCESS = "rollback_success"
    ROLLBACK_FAILURE = "rollback_failure"


@dataclass
class DeploymentEvent:
    event: DeploymentLifecycleEvent
    status: str
    version: Optional[str]
    package_type: Optional[str]
    message: str
    device_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: str = ""

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload["type"] = "deployment_event"
        return payload


def build_event(
    event: DeploymentLifecycleEvent,
    status: str,
    version: Optional[str],
    package_type: Optional[str],
    message: str,
    device_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return DeploymentEvent(
        event=event,
        status=status,
        version=version,
        package_type=package_type,
        message=message,
        device_id=device_id,
        metadata=metadata,
    ).to_payload()


class DeploymentEventPublisherProtocol:  # documentation / type aid only
    async def publish_event(self, payload: Dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError


class MQTTDeploymentEventPublisher(DeploymentEventPublisherProtocol):
    """Publish deployment events over MQTT."""

    def __init__(self, mqtt_client: MQTTClient, topic: str = "lawnberry/system/deployment_events"):
        self.mqtt_client = mqtt_client
        self.topic = topic

    async def publish_event(self, payload: Dict[str, Any]) -> None:
        await self.mqtt_client.publish(self.topic, payload)
