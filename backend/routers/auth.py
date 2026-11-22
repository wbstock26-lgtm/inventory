from fastapi import APIRouter, HTTPException, Request
import uuid, json, os

router = APIRouter()

# token → {username, role}
_tokens: dict[str, dict] = {}

AUTH_PATH = os.path.join(os.path.dirname(__file__), "../../auth.json")

DEFAULT_USERS = [{"username": "admin", "password": "admin1234", "role": "admin"}]


def _load_users() -> list[dict]:
    if not os.path.exists(AUTH_PATH):
        return DEFAULT_USERS
    with open(AUTH_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # 구형 포맷 자동 마이그레이션 {"username":..., "password":...}
    if "users" not in data:
        return [{"username": data["username"], "password": data["password"], "role": "admin"}]
    return data["users"]


def _save_users(users: list[dict]):
    with open(AUTH_PATH, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False, indent=2)


def _is_default() -> bool:
    users = _load_users()
    return len(users) == 1 and users[0]["username"] == "admin" and users[0]["password"] == "admin1234"


# ── 로그인 ───────────────────────────────────────────────────
@router.post("/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    users = _load_users()
    user = next((u for u in users if u["username"] == username and u["password"] == password), None)
    if not user:
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다")
    token = str(uuid.uuid4())
    _tokens[token] = {"username": user["username"], "role": user["role"]}
    return {"token": token, "role": user["role"]}


# ── 로그아웃 ─────────────────────────────────────────────────
@router.post("/logout")
async def logout(request: Request):
    body = await request.json()
    _tokens.pop(body.get("token", ""), None)
    return {"ok": True}


# ── 토큰 확인 ────────────────────────────────────────────────
@router.get("/check")
def check_token(token: str = ""):
    if token not in _tokens:
        raise HTTPException(401, "인증이 필요합니다")
    return {"ok": True, "role": _tokens[token]["role"]}


# ── 내 정보 ──────────────────────────────────────────────────
@router.get("/me")
def get_me(token: str = ""):
    if token not in _tokens:
        raise HTTPException(401, "인증이 필요합니다")
    info = _tokens[token]
    return {"username": info["username"], "role": info["role"]}


# ── 최초 계정 등록 (기본 상태일 때만) ───────────────────────
@router.post("/register")
async def register(request: Request):
    if not _is_default():
        raise HTTPException(403, "이미 계정이 등록되어 있습니다. 계정 설정에서 변경해주세요.")
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    if len(username) < 2:
        raise HTTPException(400, "아이디는 2자 이상이어야 합니다")
    if len(password) < 4:
        raise HTTPException(400, "비밀번호는 4자 이상이어야 합니다")
    _save_users([{"username": username, "password": password, "role": "admin"}])
    return {"ok": True}


# ── 기본값 초기화 ────────────────────────────────────────────
@router.post("/reset")
def reset_credentials():
    _save_users(DEFAULT_USERS)
    _tokens.clear()
    return {"ok": True}


# ── 기본 계정 여부 확인 ──────────────────────────────────────
@router.get("/is-default")
def is_default():
    return {"default": _is_default()}


# ── 내 비밀번호 변경 ─────────────────────────────────────────
@router.post("/update-credentials")
async def update_credentials(request: Request):
    body = await request.json()
    token = body.get("token", "")
    if token not in _tokens:
        raise HTTPException(401, "인증이 필요합니다")
    info = _tokens[token]
    users = _load_users()
    user = next((u for u in users if u["username"] == info["username"]), None)
    if not user:
        raise HTTPException(404, "사용자를 찾을 수 없습니다")
    if body.get("current_password") != user["password"]:
        raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다")
    new_username = (body.get("new_username") or "").strip()
    new_pw = (body.get("new_password") or "").strip()
    if new_username and len(new_username) < 2:
        raise HTTPException(400, "아이디는 2자 이상이어야 합니다")
    if new_pw and len(new_pw) < 4:
        raise HTTPException(400, "새 비밀번호는 4자 이상이어야 합니다")
    # admin 아이디는 변경 불가
    if new_username and user["role"] == "admin" and new_username != "admin":
        raise HTTPException(400, "admin 아이디는 변경할 수 없습니다")
    if new_username:
        user["username"] = new_username
        _tokens[token]["username"] = new_username
    if new_pw:
        user["password"] = new_pw
    _save_users(users)
    return {"ok": True}


# ── 사용자 목록 (admin 전용) ─────────────────────────────────
@router.get("/users")
def list_users(token: str = ""):
    if token not in _tokens or _tokens[token]["role"] != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다")
    users = _load_users()
    return [{"username": u["username"], "role": u["role"]} for u in users]


# ── 사용자 추가 (admin 전용) ─────────────────────────────────
@router.post("/users/add")
async def add_user(request: Request):
    body = await request.json()
    token = body.get("token", "")
    if token not in _tokens or _tokens[token]["role"] != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다")
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    role = body.get("role", "split")
    if len(username) < 2:
        raise HTTPException(400, "아이디는 2자 이상이어야 합니다")
    if len(password) < 4:
        raise HTTPException(400, "비밀번호는 4자 이상이어야 합니다")
    if role not in ("admin", "split"):
        raise HTTPException(400, "역할은 admin 또는 split이어야 합니다")
    users = _load_users()
    if any(u["username"] == username for u in users):
        raise HTTPException(400, "이미 존재하는 아이디입니다")
    users.append({"username": username, "password": password, "role": role})
    _save_users(users)
    return {"ok": True}


# ── 사용자 삭제 (admin 전용, admin 본인 삭제 불가) ───────────
@router.delete("/users/{username}")
def delete_user(username: str, token: str = ""):
    if token not in _tokens or _tokens[token]["role"] != "admin":
        raise HTTPException(403, "관리자 권한이 필요합니다")
    if username == "admin":
        raise HTTPException(400, "admin 계정은 삭제할 수 없습니다")
    users = _load_users()
    new_users = [u for u in users if u["username"] != username]
    if len(new_users) == len(users):
        raise HTTPException(404, "사용자를 찾을 수 없습니다")
    # 해당 유저의 토큰 삭제
    for t, info in list(_tokens.items()):
        if info["username"] == username:
            del _tokens[t]
    _save_users(new_users)
    return {"ok": True}
