import json
import base64
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple
from langchain_core.messages import message_to_dict, messages_from_dict


AWS_REGION = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "eu-central-1"))
TABLE_NAME = os.getenv("DYNAMODB_CHECKPOINTS_TABLE", "travel-checkpoints")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(TABLE_NAME)


def _serialize(obj: Any) -> str:
    """Serialize checkpoint dict to JSON string, handling BaseMessage objects."""
    serialized = json.dumps(obj, default=_json_default)
    return base64.b64encode(serialized.encode()).decode()


def _deserialize(data: Any) -> Any:
    """Deserialize checkpoint data, handling both new (base64+JSON) and old formats."""
    if isinstance(data, bytes):
        return _deserialize_legacy(data)
    if isinstance(data, str):
        try:
            raw = base64.b64decode(data).decode()
            return json.loads(raw, object_hook=_json_object_hook)
        except (ValueError, UnicodeDecodeError):
            return _deserialize_legacy(data)
    return {}


def _deserialize_legacy(data: Any) -> Any:
    """Fallback for old-format checkpoints (plain JSON with default=str)."""
    try:
        return json.loads(data) if isinstance(data, (str, bytes)) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "type") and hasattr(obj, "content"):
        return {"__message__": True, "data": message_to_dict(obj)}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return str(obj)


def _json_object_hook(d: dict) -> Any:
    if d.get("__message__"):
        return messages_from_dict([d["data"]])[0]
    return d


class DynamoDBSaver(BaseCheckpointSaver):
    def __init__(self, *, serde=None):
        super().__init__(serde=serde)
        self.table = table

    def _find_checkpoint_item(self, thread_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=Key("thread_id").eq(thread_id),
            ScanIndexForward=False,
            Limit=50,
        )
        for item in response.get("Items", []):
            if "checkpoint" in item:
                return item
        return None

    def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None
        item = self._find_checkpoint_item(thread_id)
        if not item:
            return None
        return _deserialize(item["checkpoint"])

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None
        item = self._find_checkpoint_item(thread_id)
        if not item:
            return None
        checkpoint = _deserialize(item["checkpoint"])
        metadata = _deserialize(item["metadata"])
        cfg = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": item["checkpoint_id"],
            }
        }
        return CheckpointTuple(cfg, checkpoint, metadata, None)

    def list(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        filter: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
    ) -> List[CheckpointTuple]:
        if not config:
            return []
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return []
        response = self.table.query(
            KeyConditionExpression=Key("thread_id").eq(thread_id),
            ScanIndexForward=False,
        )
        results = []
        for item in response.get("Items", []):
            if "checkpoint" not in item:
                continue
            checkpoint = _deserialize(item["checkpoint"])
            metadata = _deserialize(item["metadata"])
            cfg = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": item["checkpoint_id"],
                }
            }
            results.append(CheckpointTuple(cfg, checkpoint, metadata, None))
            if before and len(results) >= 10:
                break
        return results

    def put(
        self,
        config: Dict[str, Any],
        checkpoint: Dict[str, Any],
        metadata: Dict[str, Any],
        new_versions: Any = None,
    ) -> Dict[str, Any]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            raise ValueError("thread_id is required in config")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        checkpoint_id = f"T{ts}#{uuid4()}"
        item = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint": _serialize(checkpoint),
            "metadata": _serialize(metadata),
        }
        self.table.put_item(Item=item)
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: Dict[str, Any],
        writes: List[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", "")
        # 'S' prefix sorts before 'T' prefix in ascending order,
        # so writes sort AFTER checkpoints with ScanIndexForward=False (descending)
        for _chan, _val in writes:
            item = {
                "thread_id": thread_id,
                "checkpoint_id": f"S{checkpoint_id[1:]}__{task_id}",
                "write_key": task_id,
                "write_value": _serialize(_val),
            }
            self.table.put_item(Item=item)
