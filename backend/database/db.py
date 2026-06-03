import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

AWS_REGION = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "eu-central-1"))
CHATS_TABLE = os.getenv("DYNAMODB_CHATS_TABLE", "travel-chats")
MESSAGES_TABLE = os.getenv("DYNAMODB_MESSAGES_TABLE", "travel-messages")
USERS_TABLE = os.getenv("DYNAMODB_USERS_TABLE", "travel-users")

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
chats_table = dynamodb.Table(CHATS_TABLE)
messages_table = dynamodb.Table(MESSAGES_TABLE)
users_table = dynamodb.Table(USERS_TABLE)


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
        {
            "id": i["chat_id"],
            "title": i.get("title", "New Chat"),
            "updated_at": i.get("updated_at", ""),
        }
        for i in items
    ]


def get_chat(chat_id: str) -> Optional[Dict[str, Any]]:
    response = chats_table.get_item(Key={"chat_id": chat_id})
    item = response.get("Item")
    if not item:
        return None
    return {
        "id": item["chat_id"],
        "title": item.get("title", "New Chat"),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
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
    try:
        chats_table.update_item(
            Key={"chat_id": chat_id},
            UpdateExpression="SET #t = :title, updated_at = :now",
            ConditionExpression="attribute_exists(chat_id)",
            ExpressionAttributeNames={"#t": "title"},
            ExpressionAttributeValues={":title": title, ":now": now},
        )
    except chats_table.meta.client.exceptions.ConditionalCheckFailedException:
        pass


def sync_messages(chat_id: str, messages: List[Dict[str, str]]):
    _delete_all_messages(chat_id)
    base = datetime.now(timezone.utc).timestamp()
    with messages_table.batch_writer() as batch:
        for i, msg in enumerate(messages):
            raw = msg.get("created_at")
            if raw:
                created_at = raw
            else:
                created_at = datetime.fromtimestamp(base + i * 0.001, tz=timezone.utc).isoformat()
            msg_id = f"{created_at}#{i:06d}#{uuid.uuid4()}"
            batch.put_item(Item={
                "chat_id": chat_id,
                "msg_id": msg_id,
                "role": msg["role"],
                "content": msg["content"],
                "created_at": created_at,
            })
    now = datetime.now(timezone.utc).isoformat()
    try:
        chats_table.update_item(
            Key={"chat_id": chat_id},
            UpdateExpression="SET updated_at = :now",
            ConditionExpression="attribute_exists(chat_id)",
            ExpressionAttributeValues={":now": now},
        )
    except chats_table.meta.client.exceptions.ConditionalCheckFailedException:
        pass


def add_message(chat_id: str, role: str, content: str):
    now = datetime.now(timezone.utc).isoformat()
    msg_id = f"{now}#{uuid.uuid4()}"
    item = {
        "chat_id": chat_id,
        "msg_id": msg_id,
        "role": role,
        "content": content,
        "created_at": now,
    }
    messages_table.put_item(Item=item)

    try:
        chats_table.update_item(
            Key={"chat_id": chat_id},
            UpdateExpression="SET updated_at = :now",
            ConditionExpression="attribute_exists(chat_id)",
            ExpressionAttributeValues={":now": now},
        )
    except chats_table.meta.client.exceptions.ConditionalCheckFailedException:
        pass


def get_messages(chat_id: str) -> List[Dict[str, Any]]:
    response = messages_table.query(
        KeyConditionExpression=Key("chat_id").eq(chat_id),
        ScanIndexForward=True,
    )
    return [
        {
            "role": i["role"],
            "content": i["content"],
            "created_at": i["created_at"],
        }
        for i in response.get("Items", [])
    ]


def create_user(email: str, password_hash: str) -> Dict[str, Any]:
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": user_id,
        "email": email,
        "password_hash": password_hash,
        "created_at": now,
    }
    users_table.put_item(Item=item)
    return {"user_id": user_id, "email": email, "created_at": now}


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    response = users_table.query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email),
    )
    items = response.get("Items", [])
    if not items:
        return None
    return items[0]


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    response = users_table.get_item(Key={"user_id": user_id})
    item = response.get("Item")
    if not item:
        return None
    return {
        "user_id": item["user_id"],
        "email": item["email"],
        "created_at": item.get("created_at", ""),
    }
