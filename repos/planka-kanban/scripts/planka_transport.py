"""Edition-neutral HTTP, authentication and secret-safe output."""
import json
import os
import urllib.error
import urllib.request
import uuid

SECRET_KEYS = {"password", "token", "apiKey", "api_key", "pendingToken", "Authorization", "smtpPassword", "accessToken", "httpOnlyToken", "secret"}

class PlankaError(RuntimeError):
    def __init__(self, status: int | None, message: str, body: object | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def redact(value):
    if isinstance(value, dict):
        return {k: ("<redacted>" if k in SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def print_json(value):
    print(json.dumps(redact(value), ensure_ascii=True, indent=2, sort_keys=True))


def env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name)
    if required and not value:
        raise SystemExit(f"Missing environment variable: {name}")
    return value


class PlankaClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, data: dict | None = None, token: str | None = None):
        url = self.base_url + path
        body = None
        headers = {"Accept": "application/json"}
        bearer = token if token is not None else self.token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            message = f"HTTP {exc.code}"
            if isinstance(parsed, dict) and parsed.get("message"):
                message += f": {parsed['message']}"
            raise PlankaError(exc.code, message, parsed) from exc

    def request_multipart(
        self,
        method: str,
        path: str,
        fields: dict,
        token: str | None = None,
    ):
        boundary = f"----codex-planka-{uuid.uuid4().hex}"
        chunks = []
        for key, value in fields.items():
            chunks.append(f"--{boundary}\r\n".encode("ascii"))
            chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("ascii"))
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))

        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        bearer = token if token is not None else self.token
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"

        req = urllib.request.Request(
            self.base_url + path,
            data=b"".join(chunks),
            method=method.upper(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            message = f"HTTP {exc.code}"
            if isinstance(parsed, dict) and parsed.get("message"):
                message += f": {parsed['message']}"
            raise PlankaError(exc.code, message, parsed) from exc

    def login(self, username: str, password: str):
        payload = {
            "emailOrUsername": username,
            "password": password,
            "withHttpOnlyToken": False,
        }
        data = self.request("POST", "/api/access-tokens", payload, token=None)
        if not isinstance(data, dict) or not isinstance(data.get("item"), str) or not data['item']:
            raise PlankaError(None, 'Login did not return an access token; inspect required authentication step without accepting terms or changing account state')
        self.token = data["item"]
        return self.token


