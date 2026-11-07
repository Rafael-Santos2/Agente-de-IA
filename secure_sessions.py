"""Sessões autenticadas; chave separada, protegida por DPAPI no Windows."""
import csv
import ctypes
import hashlib
import hmac
import json
import os
import secrets
import stat
import subprocess
import threading
import weakref
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from strands.session.file_session_manager import FileSessionManager

MANIFEST = ".integrity.json"
MAX_FILE_BYTES = 256_000
MAX_MANIFEST_BYTES = 512_000
MAX_FILES = 2000
MAX_SESSION_BYTES = 16_000_000


class IntegrityError(Exception):
    pass


def reject_links(path):
    for part in (Path(path), *Path(path).parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise IntegrityError("Links e reparse points não são permitidos.")


def private_directory(path):
    path = Path(path).absolute()
    reject_links(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        user = subprocess.check_output(
            ["whoami", "/user", "/fo", "csv", "/nh"], text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        sid = next(csv.reader(user.strip().splitlines()))[1]
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        path.chmod(0o700)
    return path


def _dpapi(data, protect):
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    function = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    function.argtypes = [
        ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise IntegrityError("Não foi possível acessar a chave de integridade.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)


def load_signing_key():
    project = hashlib.sha256(str(Path(__file__).resolve().parent).encode()).hexdigest()[:16]
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    directory = private_directory(base / "IaCafe" / project)
    key_path = directory / "session-key.bin"
    reject_links(key_path)
    if not key_path.exists():
        key = secrets.token_bytes(32)
        data = _dpapi(key, True) if os.name == "nt" else key
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
    data = key_path.read_bytes()
    key = _dpapi(data, False) if os.name == "nt" else data
    if len(key) != 32:
        raise IntegrityError("Chave de integridade inválida.")
    return key


def new_session_id():
    return "sessao-" + str(uuid4())


def valid_session_id(value):
    try:
        return value == "sessao-" + str(UUID(value.removeprefix("sessao-"), version=4))
    except (ValueError, AttributeError):
        return False


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _signature(key, folder, payload):
    return hmac.new(key, folder.name.encode() + b"\0" + _canonical(payload), hashlib.sha256).hexdigest()


def read_manifest(folder, key):
    path = folder / MANIFEST
    reject_links(path)
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise IntegrityError("Sessão sem integridade verificável.")
    try:
        signed = json.loads(path.read_text(encoding="utf-8"))
        payload = signed["payload"]
        if not hmac.compare_digest(signed["hmac"], _signature(key, folder, payload)):
            raise IntegrityError("Assinatura inválida.")
        if payload["version"] != 1 or not isinstance(payload["files"], dict):
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError):
        raise IntegrityError("Manifesto inválido.") from None


def verify_session(folder, key):
    payload = read_manifest(folder, key)
    files = list(folder.rglob("*.json"))
    actual = {file.relative_to(folder).as_posix() for file in files if file.name != MANIFEST}
    if actual != set(payload["files"]) or len(actual) > MAX_FILES or "session.json" not in actual:
        raise IntegrityError("Conjunto de arquivos da sessão alterado.")
    size = 0
    for name, digest in payload["files"].items():
        file = folder / name
        reject_links(file)
        length = file.stat().st_size
        size += length
        if length > MAX_FILE_BYTES or size > MAX_SESSION_BYTES:
            raise IntegrityError("Sessão excede o limite de tamanho.")
        if not hmac.compare_digest(hashlib.sha256(file.read_bytes()).hexdigest(), digest):
            raise IntegrityError("Histórico adulterado.")
    return payload["updated_at"]


class SecureSessionManager(FileSessionManager):
    def __init__(self, session_id, storage_dir, *, signing_key=None):
        if not valid_session_id(session_id):
            raise IntegrityError("Identificador de sessão inválido.")
        self.key = signing_key if signing_key is not None else load_signing_key()
        self.root = Path(storage_dir).absolute()
        reject_links(self.root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.folder = self.root / ("session_" + session_id)
        reject_links(self.folder)
        existed = self.folder.exists()
        self.folder.mkdir(mode=0o700, exist_ok=True)
        self.guard = threading.RLock()
        reject_links(self.folder / ".lock")
        handle = open(self.folder / ".lock", "a+b")
        self._release = weakref.finalize(self, handle.close)
        try:
            if handle.seek(0, 2) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if existed:
                verify_session(self.folder, self.key)
            super().__init__(session_id=session_id, storage_dir=str(self.root))
        except Exception:
            self.close()
            raise

    def close(self):
        self._release()

    def create_session(self, session, **kwargs):
        # A pasta já existe para manter o lock adquirido antes de qualquer leitura.
        if (self.folder / "session.json").exists():
            raise IntegrityError("Sessão já existente.")
        (self.folder / "agents").mkdir(mode=0o700, exist_ok=True)
        (self.folder / "multi_agents").mkdir(mode=0o700, exist_ok=True)
        self._write_file(str(self.folder / "session.json"), session.to_dict())
        return session

    def _read_file(self, path):
        file = Path(path)
        reject_links(file)
        payload = read_manifest(self.folder, self.key)
        name = file.relative_to(self.folder).as_posix()
        with file.open("rb") as source:
            raw = source.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise IntegrityError("Registro excessivo.")
        digest = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(payload["files"].get(name, ""), digest):
            raise IntegrityError("Registro adulterado.")
        # Validar e interpretar os mesmos bytes, sem reabrir o arquivo após o hash.
        return json.loads(raw)

    def _write_file(self, path, data):
        with self.guard:
            file = Path(path)
            reject_links(file)
            name = file.relative_to(self.folder).as_posix()
            length = len(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
            if length > MAX_FILE_BYTES:
                raise IntegrityError("Registro excessivo.")
            manifest_path = self.folder / MANIFEST
            if manifest_path.exists():
                payload = read_manifest(self.folder, self.key)
            else:
                payload = {"version": 1, "files": {}}
            if name not in payload["files"] and len(payload["files"]) >= MAX_FILES:
                raise IntegrityError("Limite da sessão atingido; inicie uma nova.")
            previous_size = sum((self.folder / entry).stat().st_size
                                for entry in payload["files"] if entry != name)
            if previous_size + length > MAX_SESSION_BYTES:
                raise IntegrityError("Sessão excede o limite de tamanho.")
            super()._write_file(str(file), data)
            payload["files"][name] = hashlib.sha256(file.read_bytes()).hexdigest()
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            super()._write_file(str(manifest_path), {
                "payload": payload, "hmac": _signature(self.key, self.folder, payload),
            })


def verified_sessions(storage_dir, key):
    sessions = []
    ignored = 0
    for folder in Path(storage_dir).glob("session_*"):
        session_id = folder.name.removeprefix("session_")
        try:
            if not valid_session_id(session_id):
                raise IntegrityError()
            updated_at = verify_session(folder, key)
            sessions.append((updated_at, session_id))
        except (IntegrityError, OSError, ValueError, TypeError):
            ignored += 1
    return sorted(sessions, reverse=True), ignored
