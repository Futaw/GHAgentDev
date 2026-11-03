#!/usr/bin/env python3
import json
import sys


def send(message: dict) -> None:
    print(json.dumps(message, separators=(",", ":")), flush=True)


approval_waiter = None
for raw_line in sys.stdin:
    message = json.loads(raw_line)
    method = message.get("method")
    request_id = message.get("id")
    if method is None and request_id == 999 and approval_waiter is not None:
        send({"id": approval_waiter, "result": message})
        approval_waiter = None
    elif method == "test/approval":
        approval_waiter = request_id
        kind = message["params"]["kind"]
        params = {
            "threadId": "thr_test",
            "turnId": "turn_test",
            "itemId": "item_test",
            "startedAtMs": 1,
        }
        if kind == "commandExecution":
            params.update(
                {
                    "kind": "command",
                    "environmentId": None,
                    "command": "echo fixture",
                    "cwd": "/fixture",
                }
            )
        elif kind == "permissions":
            params.update(
                {"environmentId": None, "cwd": "/fixture", "reason": None, "permissions": {}}
            )
        send({"id": 999, "method": "item/" + kind + "/requestApproval", "params": params})
    elif method == "initialize":
        send({"id": request_id, "result": {"serverInfo": {"name": "fake", "version": "1"}}})
    elif method == "initialized":
        continue
    elif method == "account/read":
        send(
            {
                "id": request_id,
                "result": {
                    "account": {
                        "type": "chatgpt",
                        "email": "hidden@example.com",
                        "planType": "plus",
                    },
                    "requiresOpenaiAuth": True,
                },
            }
        )
    elif method == "thread/start":
        send({"id": request_id, "result": {"thread": {"id": "thr_test"}}})
    elif method == "turn/start":
        send({"id": request_id, "result": {"turn": {"id": "turn_test", "status": "inProgress"}}})
        send(
            {
                "method": "turn/started",
                "params": {"threadId": "thr_test", "turn": {"id": "turn_test"}},
            }
        )
        send(
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thr_test",
                    "turnId": "turn_test",
                    "itemId": "item_test",
                    "delta": "fake answer",
                },
            }
        )
        send(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thr_test",
                    "turn": {"id": "turn_test", "status": "completed", "items": []},
                },
            }
        )
    elif method == "test/crash":
        sys.exit(7)
    elif method == "test/hang":
        continue
    elif request_id is not None:
        send({"id": request_id, "result": {}})
