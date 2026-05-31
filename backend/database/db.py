import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

CHATS_TABLE = os.getenv("DYNAMODB_CHATS_TABLE", "travel-chats")
MESSAGES_TABLE = os.getenv("DYNAMODB_MESSAGES_TABLE", "travel-messages")

dynamodb = boto3.resource("dynamodb")
chats_table = dynamodb.Table(CHATS_TABLE)
messages_table = dynamodb.Table(MESSAGES_TABLE)


def create_chat(chat_id: str, title: str = "New Chat") -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "chat_id": chat_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    chats_table.put_item(Item=item)
    return {"id": chat_id, "title": title, "created_at": now, "updated_at": now}


def list_chats() -> List[Dict[str, Any]]:
    response = chats_table.scan()
    items = response.get("Items", [])
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return [
        {"id": i["chat_id"], "title": i["title"], "updated_at": i["updated_at"]}
        for i in items
    ]


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    response = chats_table.get_item(Key={"chat_id": chat_id})
    item = response.get("Item")
    if not item:
        return None
    return {
        "id": item["chat_id"],
        "title": item["title"],
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }


def delete_chat(chat_id: str) -> bool:
    response = chats_table.delete_item(
        Key={"chat_id": chat_id},
        ReturnValues="ALL_OLD",
    )
    deleted = response.get("Attributes") is not None
    if deleted:
        _delete_all_messages(chat_id)
    return deleted


def _delete_all_messages(chat_id: str):
    response = messages_table.query(
        KeyConditionExpression=Key("chat_id").eq(chat_id),
        ProjectionExpression="chat_id,msg_id",
    )
    items = response.get("Items", [])
    with messages_table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"chat_id": item["chat_id"], "msg_id": item["msg_id"]})


def update_chat_title(chat_id: str, title: str):
    now = datetime.now(timezone.utc).isoformat()
    chats_table.update_item(
        Key={"chat_id": chat_id},
        UpdateExpression="SET #t = :title, updated_at = :now",
        ExpressionAttributeNames={"#t": "title"},
        ExpressionAttributeValues={":title": title, ":now": now},
    )


def add_message(chat_id: str, role: str, content: str):
    now = datetime.now(timezone.utc).isoformat()
    msg_id = str(uuid.uuid4())
    item = {
        "chat_id": chat_id,
        "msg_id": msg_id,
        "role": role,
        "content": content,
        "created_at": now,
    }
    messages_table.put_item(Item=item)

    chats_table.update_item(
        Key={"chat_id": chat_id},
        UpdateExpression="SET updated_at = :now",
        ExpressionAttributeValues={":now": now},
    )


def get_messages(chat_id: str) -> List[Dict[str, Any]]:
    response = messages_table.query(
        KeyConditionExpression=Key("chat_id").eq(chat_id),
        ScanIndexForward=True,
    )
    items = response.get("Items", [])
    items.sort(key=lambda x: x.get("created_at", ""))
    return [
        {
            "role": i["role"],
            "content": i["content"],
            "created_at": i["created_at"],
        }
        for i in items
    ]
