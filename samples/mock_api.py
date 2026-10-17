"""Local mock API for demos, screenshots and end-to-end tests.

    python samples/mock_api.py            # http://127.0.0.1:8099

POST /users      -> 201; 500 when name contains "fail"; 422 when email has no "@"
GET  /users/{id} -> 200 with a user; 404 for id > 1000
GET  /flaky      -> fails twice per key (?key=...), then succeeds - shows automatic retry
"""

from __future__ import annotations

import itertools
from collections import defaultdict

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

api = FastAPI(title="API Runner mock")
_ids = itertools.count(1001)
_flaky: dict[str, int] = defaultdict(int)


@api.post("/users")
async def create_user(request: Request):
    body = await request.json()
    name = str(body.get("name", ""))
    if "fail" in name.lower():
        return JSONResponse({"error": "internal error while saving user", "name": name}, status_code=500)
    if "@" not in str(body.get("email", "")):
        return JSONResponse({"error": "email is invalid", "field": "email"}, status_code=422)
    return JSONResponse({"id": next(_ids), "created": True, **body}, status_code=201)


@api.get("/users/{user_id}")
async def get_user(user_id: int, verbose: bool = False):
    if user_id > 1000:
        return JSONResponse({"error": f"user {user_id} not found"}, status_code=404)
    user = {"id": user_id, "name": f"User {user_id}", "email": f"user{user_id}@example.com"}
    if verbose:
        user["roles"] = ["reader", "writer"]
    return user


@api.get("/flaky")
async def flaky(key: str = "default"):
    _flaky[key] += 1
    if _flaky[key] <= 2:
        return JSONResponse({"error": "temporarily unavailable"}, status_code=503)
    return {"ok": True, "attempt": _flaky[key]}


if __name__ == "__main__":
    uvicorn.run(api, host="127.0.0.1", port=8099, log_level="warning")
