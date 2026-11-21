from fastapi import APIRouter, HTTPException, Request
import uuid, json, os

router = APIRouter()

_tokens: set[str] = set()

def _get_credentials() -> dict:
    path = os.path.join(os.path.dirname(__file__), "../../auth.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"username": "admin", "password": "admin1234"}


@router.post("/login")
async def login(request: Request):
    body = await request.json()
    creds = _get_credentials()
    if body.get("username") != creds["username"] or body.get("password") != creds["password"]:
        raise HTTPException(401, "아이디 또는 비밀번호가 올바르지 않습니다")
    token = str(uuid.uuid4())
    _tokens.add(token)
    return {"token": token}


@router.post("/logout")
async def logout(request: Request):
    body = await request.json()
    _tokens.discard(body.get("token", ""))
    return {"ok": True}


@router.get("/check")
def check_token(token: str = ""):
    if token not in _tokens:
        raise HTTPException(401, "인증이 필요합니다")
    return {"ok": True}


DEFAULT_CREDS = {"username": "admin", "password": "admin1234"}

def _is_default() -> bool:
    creds = _get_credentials()
    return creds == DEFAULT_CREDS

@router.post("/register")
async def register(request: Request):
    """처음 사용 시 또는 기본 계정 상태일 때만 계정 등록 허용"""
    if not _is_default():
        raise HTTPException(403, "이미 계정이 등록되어 있습니다. 계정 설정에서 변경해주세요.")
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    if len(username) < 2:
        raise HTTPException(400, "아이디는 2자 이상이어야 합니다")
    if len(password) < 4:
        raise HTTPException(400, "비밀번호는 4자 이상이어야 합니다")
    path = os.path.join(os.path.dirname(__file__), "../../auth.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"username": username, "password": password}, f, ensure_ascii=False, indent=2)
    return {"ok": True}


@router.get("/is-default")
def is_default():
    return {"default": _is_default()}


@router.get("/me")
def get_me(token: str = ""):
    if token not in _tokens:
        raise HTTPException(401, "인증이 필요합니다")
    creds = _get_credentials()
    return {"username": creds["username"]}


@router.post("/update-credentials")
async def update_credentials(request: Request):
    body = await request.json()
    token = body.get("token", "")
    if token not in _tokens:
        raise HTTPException(401, "인증이 필요합니다")
    creds = _get_credentials()
    if body.get("current_password") != creds["password"]:
        raise HTTPException(400, "현재 비밀번호가 올바르지 않습니다")
    new_username = (body.get("new_username") or "").strip()
    new_pw = (body.get("new_password") or "").strip()
    if new_username and len(new_username) < 2:
        raise HTTPException(400, "아이디는 2자 이상이어야 합니다")
    if new_pw and len(new_pw) < 4:
        raise HTTPException(400, "새 비밀번호는 4자 이상이어야 합니다")
    if new_username:
        creds["username"] = new_username
    if new_pw:
        creds["password"] = new_pw
    path = os.path.join(os.path.dirname(__file__), "../../auth.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(creds, f, ensure_ascii=False, indent=2)
    return {"ok": True}
