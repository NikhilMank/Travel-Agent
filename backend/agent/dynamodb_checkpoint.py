import json
import os
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple

TABLE_NAME = os.getenv("DYNAMODB_CHECKPOINTS_TABLE", "travel-checkpoints")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


class DynamoDBSaver(BaseCheckpointSaver):
    def __init__(self, *, serde=None):
        super().__init__(serde=serde)
        self.table = table

    def get(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None
        response = self.table.query(
            KeyConditionExpression=Key("thread_id").eq(thread_id),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None
        return json.loads(items[0].get("checkpoint", "{}"))

    def get_tuple(self, config: Dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return None
        response = self.table.query(
            KeyConditionExpression=Key("thread_id").eq(thread_id),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None
        item = items[0]
        if "checkpoint" not in item:
            return None
        checkpoint = json.loads(item["checkpoint"])
        metadata = json.loads(item.get("metadata", "{}"))
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
            checkpoint = json.loads(item["checkpoint"])
            metadata = json.loads(item.get("metadata", "{}"))
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
        checkpoint_id = str(uuid4())
        item = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "checkpoint": json.dumps(checkpoint, default=str),
            "metadata": json.dumps(metadata, default=str),
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
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", str(uuid4()))
        for _chan, _val in writes:
            item = {
                "thread_id": thread_id,
                "checkpoint_id": f"{checkpoint_id}_{task_id}",
                "write_key": task_id,
                "write_value": json.dumps(_val, default=str),
            }
            self.table.put_item(Item=item)
