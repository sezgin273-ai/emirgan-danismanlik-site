#!/usr/bin/env python3
"""FTP deploy — kimlik bilgisi içermez; FTP_HOST / FTP_USER / FTP_PASS ortam değişkenlerinden okunur."""
from __future__ import annotations

import copy
import getpass
import io
import json
import os
import re
import subprocess
import sys
from ftplib import FTP, FTP_TLS, error_perm
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_HTML = ROOT / "public_html"
CONTENT_DIR = ROOT / "content"
CONFIG_PATH = PUBLIC_HTML / "config.php"
PHP_BIN = ROOT / ".tools/php/php.exe"
PHP_INI = ROOT / ".tools/php/php.ini"

WEB_ROOT_CANDIDATES = ("httpdocs", "public_html", "www")
EXCLUDED_PUBLIC_FILES = frozenset({"router.php", "config.php"})
CHMOD_DIRS = (
    ("content", "content/"),
    ("content/backups", "content/backups/"),
    ("content/mail-log", "content/mail-log/"),
    ("uploads", "assets/img/uploads/"),
)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"HATA: {name} ortam değişkeni gerekli.", file=sys.stderr)
        sys.exit(1)
    return value


def php_cmd(*args: str) -> list[str]:
    cmd = [str(PHP_BIN)]
    if PHP_INI.exists():
        cmd.extend(["-c", str(PHP_INI)])
    cmd.extend(args)
    return cmd


def connect_ftp(host: str, user: str, password: str) -> FTP:
    last_error: Exception | None = None
    for factory, label in ((FTP_TLS, "FTPS"), (FTP, "FTP")):
        try:
            ftp = factory()
            ftp.connect(host, 21, timeout=60)
            if isinstance(ftp, FTP_TLS):
                ftp.auth()
                ftp.prot_p()
            ftp.login(user, password)
            ftp.set_pasv(True)
            print(f"FTP bağlantısı kuruldu ({label}).")
            return ftp
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"FTP bağlantısı kurulamadı: {last_error}") from last_error


def ftp_list_names(ftp: FTP, path: str = ".") -> list[str]:
    cwd = ftp.pwd()
    try:
        ftp.cwd(path)
        return ftp.nlst()
    finally:
        ftp.cwd(cwd)


def detect_web_root(ftp: FTP) -> str:
    root_names = {name.lower(): name for name in ftp_list_names(ftp, ".")}
    for candidate in WEB_ROOT_CANDIDATES:
        actual = root_names.get(candidate.lower())
        if actual is None:
            continue
        entries = {name.lower() for name in ftp_list_names(ftp, actual)}
        if "index.php" in entries or "index.html" in entries:
            return actual
        if entries:
            return actual
    listing = sorted(root_names.values())
    raise RuntimeError(
        "Web kökü tespit edilemedi. Kök dizin: "
        + ", ".join(listing[:20])
        + (" …" if len(listing) > 20 else "")
        + f". Beklenen adlardan biri: {', '.join(WEB_ROOT_CANDIDATES)}"
    )


def verify_content_path_contract(web_root_name: str) -> None:
    """public_html/includes → dirname(__DIR__, 2)/content ile canlı yerleşim uyumu."""
    includes = PUBLIC_HTML / "includes" / "bootstrap.php"
    text = includes.read_text(encoding="utf-8")
    if "dirname(__DIR__, 2) . '/content/content.json'" not in text:
        raise RuntimeError(
            "content yolu beklenen ../content sözleşmesiyle uyumlu değil; deploy durduruldu."
        )
    # Canlıda web kökü (ör. httpdocs) bir üst dizinde content/ olmalı.
    _ = web_root_name


def iter_public_html_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(PUBLIC_HTML.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(PUBLIC_HTML).as_posix()
        if rel in EXCLUDED_PUBLIC_FILES:
            continue
        files.append(path)
    return files


def iter_content_files() -> list[Path]:
    files: list[Path] = []
    if not CONTENT_DIR.is_dir():
        return files
    for path in sorted(CONTENT_DIR.rglob("*")):
        if path.is_file():
            files.append(path)
    return files


def ensure_remote_dir(ftp: FTP, remote_dir: str) -> None:
    parts = PurePosixPath(remote_dir).parts
    current = ""
    for part in parts:
        current = f"{current}/{part}" if current else part
        try:
            ftp.mkd(current)
        except error_perm:
            pass


def upload_file(ftp: FTP, local_path: Path, remote_path: str) -> None:
    remote_dir = str(PurePosixPath(remote_path).parent)
    if remote_dir not in (".", ""):
        ensure_remote_dir(ftp, remote_dir)
    with local_path.open("rb") as handle:
        ftp.storbinary(f"STOR {remote_path}", handle)


def site_chmod(ftp: FTP, remote_path: str, mode: int) -> tuple[int, bool]:
    for attempt in (mode, 0o775):
        try:
            ftp.voidcmd(f"SITE CHMOD {attempt:o} {remote_path}")
            return attempt, True
        except error_perm:
            continue
    return mode, False


def ftp_delete_file(ftp: FTP, remote_path: str) -> bool:
    try:
        ftp.delete(remote_path)
        return True
    except error_perm:
        return False


def ftp_delete_tree(ftp: FTP, remote_dir: str) -> None:
    try:
        entries = ftp.nlst(remote_dir)
    except error_perm:
        return
    for entry in entries:
        name = entry.rsplit("/", 1)[-1]
        if name in (".", "..") or entry == remote_dir:
            continue
        try:
            ftp.size(entry)
            ftp.delete(entry)
        except error_perm:
            ftp_delete_tree(ftp, entry)
    try:
        ftp.rmd(remote_dir)
    except error_perm:
        pass


def cleanup_natro_placeholders(ftp: FTP, web_root: str) -> list[str]:
    """Natro varsayilan dosyalarini kaldir (index.php onceligi icin)."""
    removed: list[str] = []
    if ftp_delete_file(ftp, f"{web_root}/index.html"):
        removed.append(f"{web_root}/index.html")
    for dirname in ("bootstrap-3.3.7", "css", "images"):
        path = f"{web_root}/{dirname}"
        try:
            ftp.nlst(path)
        except error_perm:
            continue
        ftp_delete_tree(ftp, path)
        removed.append(path)
    return removed


def deploy_public_html(ftp: FTP, web_root: str) -> int:
    count = 0
    for local_path in iter_public_html_files():
        rel = local_path.relative_to(PUBLIC_HTML).as_posix()
        remote = f"{web_root}/{rel}"
        upload_file(ftp, local_path, remote)
        count += 1
    return count


def deploy_content(ftp: FTP) -> int:
    count = 0
    ensure_remote_dir(ftp, "content/mail-log")
    ensure_remote_dir(ftp, "content/backups")
    for local_path in iter_content_files():
        rel = local_path.relative_to(CONTENT_DIR).as_posix()
        remote = f"content/{rel}"
        upload_file(ftp, local_path, remote)
        count += 1
    return count


def apply_chmod(ftp: FTP, web_root: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, rel in CHMOD_DIRS:
        remote = rel if rel.startswith("content/") else f"{web_root}/{rel}"
        ensure_remote_dir(ftp, remote.rstrip("/"))
        mode, ok = site_chmod(ftp, remote.rstrip("/"), 0o755)
        rows.append({"path": remote.rstrip("/"), "label": label, "mode": oct(mode), "ok": ok})
    return rows


def generate_live_config(
    admin_password: str | None = None,
    *,
    smtp_host: str = "mail.kurumsaleposta.com",
    smtp_port: int = 465,
    smtp_secure: str = "ssl",
) -> None:
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    if not smtp_pass:
        print("HATA: SMTP_PASS ortam değişkeni gerekli.", file=sys.stderr)
        sys.exit(1)
    env = os.environ.copy()
    env["SMTP_PASS"] = smtp_pass
    cmd = [str(PHP_BIN)]
    if PHP_INI.exists():
        cmd.extend(["-c", str(PHP_INI)])
    cmd.append(str(ROOT / "scripts/create_admin_config.php"))
    if admin_password:
        cmd.append(f"--password={admin_password}")
    cmd.append("--mail-mode=smtp")
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise RuntimeError("config.php üretilemedi.")
    text = CONFIG_PATH.read_text(encoding="utf-8")
    text = re.sub(r"('mail_mode'\s*=>\s*)'[^']*'", r"\1'smtp'", text, count=1)
    text = re.sub(
        r"('mail_to'\s*=>\s*)'[^']*'",
        r"\1'info@emirgandanismanlik.com'",
        text,
        count=1,
    )
    text = re.sub(
        r"('smtp_port'\s*=>\s*)\d+",
        lambda m: f"{m.group(1)}{smtp_port}",
        text,
        count=1,
    )
    text = re.sub(
        r"('smtp_secure'\s*=>\s*)'[^']*'",
        lambda _: f"'smtp_secure' => '{smtp_secure}'",
        text,
        count=1,
    )
    text = re.sub(
        r"('smtp_host'\s*=>\s*)'[^']*'",
        lambda _: f"'smtp_host' => '{smtp_host}'",
        text,
        count=1,
    )
    CONFIG_PATH.write_text(text, encoding="utf-8")


def download_remote_file(ftp: FTP, remote_path: str, local_path: Path) -> bool:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with local_path.open("wb") as handle:
            ftp.retrbinary(f"RETR {remote_path}", handle.write)
        return local_path.is_file() and local_path.stat().st_size > 0
    except error_perm:
        return False


def backup_live_smtp_files(ftp: FTP, web_root: str, backup_dir: Path) -> dict[str, bool]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    rows = {
        "contact.php": download_remote_file(
            ftp, f"{web_root}/api/contact.php", backup_dir / "contact.php"
        ),
        "config.php": download_remote_file(
            ftp, f"{web_root}/config.php", backup_dir / "config.php"
        ),
    }
    return rows


def upload_smtp_bundle(ftp: FTP, web_root: str) -> list[str]:
    uploaded: list[str] = []
    contact_local = PUBLIC_HTML / "api" / "contact.php"
    upload_file(ftp, contact_local, f"{web_root}/api/contact.php")
    uploaded.append(f"{web_root}/api/contact.php")

    phpmailer_dir = PUBLIC_HTML / "api" / "lib" / "phpmailer"
    for name in ("PHPMailer.php", "SMTP.php", "Exception.php"):
        local_path = phpmailer_dir / name
        remote = f"{web_root}/api/lib/phpmailer/{name}"
        upload_file(ftp, local_path, remote)
        uploaded.append(remote)

    upload_config(ftp, web_root)
    uploaded.append(f"{web_root}/config.php")
    return uploaded


def rollback_smtp_files(ftp: FTP, web_root: str, backup_dir: Path) -> list[str]:
    restored: list[str] = []
    for name in ("contact.php", "config.php"):
        local_path = backup_dir / name
        if not local_path.is_file():
            continue
        remote = f"{web_root}/api/{name}" if name == "contact.php" else f"{web_root}/{name}"
        upload_file(ftp, local_path, remote)
        restored.append(remote)
    return restored


def smtp_login(server, user: str, password: str) -> None:
    import base64
    import smtplib

    try:
        server.login(user, password)
        return
    except UnicodeEncodeError:
        pass

    auth_plain = base64.b64encode(f"\0{user}\0{password}".encode("utf-8")).decode("ascii")
    code, resp = server.docmd("AUTH", "PLAIN " + auth_plain)
    if code == 235:
        return

    code, resp = server.docmd("AUTH LOGIN")
    if code != 334:
        raise smtplib.SMTPAuthenticationError(code, resp)
    code, resp = server.docmd(base64.b64encode(user.encode("utf-8")).decode("ascii"))
    if code != 334:
        raise smtplib.SMTPAuthenticationError(code, resp)
    code, resp = server.docmd(base64.b64encode(password.encode("utf-8")).decode("ascii"))
    if code != 235:
        raise smtplib.SMTPAuthenticationError(code, resp)


def probe_smtp_via_php(host: str, user: str, password: str, port: int, secure: str) -> bool:
    php_code = """<?php
declare(strict_types=1);
require 'public_html/api/lib/phpmailer/Exception.php';
require 'public_html/api/lib/phpmailer/SMTP.php';
require 'public_html/api/lib/phpmailer/PHPMailer.php';
$host = getenv('SMTP_PROBE_HOST') ?: '';
$user = getenv('SMTP_PROBE_USER') ?: '';
$pass = getenv('SMTP_PROBE_PASS') ?: '';
$port = (int) (getenv('SMTP_PROBE_PORT') ?: '0');
$secure = getenv('SMTP_PROBE_SECURE') ?: '';
try {
    $mailer = new PHPMailer\\PHPMailer\\PHPMailer(true);
    $mailer->isSMTP();
    $mailer->Host = $host;
    $mailer->Port = $port;
    $mailer->SMTPAuth = true;
    $mailer->Username = $user;
    $mailer->Password = $pass;
    $mailer->SMTPDebug = 0;
    $mailer->Timeout = 20;
    if ($secure === 'ssl') {
        $mailer->SMTPSecure = PHPMailer\\PHPMailer\\PHPMailer::ENCRYPTION_SMTPS;
    } elseif ($secure === 'tls') {
        $mailer->SMTPSecure = PHPMailer\\PHPMailer\\PHPMailer::ENCRYPTION_STARTTLS;
    }
    return $mailer->smtpConnect() ? 0 : 1;
} catch (Throwable $e) {
    return 1;
}
"""
    env = os.environ.copy()
    env["SMTP_PROBE_HOST"] = host
    env["SMTP_PROBE_USER"] = user
    env["SMTP_PROBE_PASS"] = password
    env["SMTP_PROBE_PORT"] = str(port)
    env["SMTP_PROBE_SECURE"] = secure
    cmd = [str(PHP_BIN)]
    if PHP_INI.exists():
        cmd.extend(["-c", str(PHP_INI)])
    cmd.extend(["-r", php_code])
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc.returncode == 0


def probe_smtp_settings(host: str, user: str, password: str) -> tuple[int, str] | None:
    import smtplib
    import ssl

    for port, secure in ((465, "ssl"), (587, "tls")):
        try:
            if secure == "ssl":
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
                    smtp_login(server, user, password)
                return port, secure
            else:
                with smtplib.SMTP(host, port, timeout=20) as server:
                    server.starttls(context=ssl.create_default_context())
                    smtp_login(server, user, password)
                return port, secure
        except OSError:
            continue
        except smtplib.SMTPException:
            continue

    for port, secure in ((465, "ssl"), (587, "tls")):
        if probe_smtp_via_php(host, user, password, port, secure):
            return port, secure
    return None


FAZ54_PUBLIC_REL = (
    "index.php",
    "assets/css/main.css",
    "admin/dashboard.php",
    "admin/actions.php",
    "admin/assets/admin.js",
)


def backup_live_faz54_files(ftp: FTP, web_root: str, backup_dir: Path) -> dict[str, bool]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    return {
        "index.php": download_remote_file(ftp, f"{web_root}/index.php", backup_dir / "index.php"),
        "main.css": download_remote_file(
            ftp, f"{web_root}/assets/css/main.css", backup_dir / "main.css"
        ),
        "content.json": download_remote_file(
            ftp, "content/content.json", backup_dir / "content.json"
        ),
    }


def rollback_faz54_files(ftp: FTP, web_root: str, backup_dir: Path) -> list[str]:
    restored: list[str] = []
    mapping = {
        "index.php": f"{web_root}/index.php",
        "main.css": f"{web_root}/assets/css/main.css",
        "content.json": "content/content.json",
    }
    for name, remote in mapping.items():
        local_path = backup_dir / name
        if not local_path.is_file():
            continue
        upload_file(ftp, local_path, remote)
        restored.append(remote)
    return restored


def merge_contact_hours_seed(live_path: Path, seed_hours: dict) -> dict[str, object]:
    live = json.loads(live_path.read_text(encoding="utf-8"))
    before = copy.deepcopy(live)
    contact = live.setdefault("contact", {})
    contact["hours"] = copy.deepcopy(seed_hours)
    before_cmp = copy.deepcopy(before)
    after_cmp = copy.deepcopy(live)
    before_cmp.get("contact", {}).pop("hours", None)
    after_cmp.get("contact", {}).pop("hours", None)
    if before_cmp != after_cmp:
        raise RuntimeError("content.json merge mevcut alanları değiştirir; deploy durduruldu.")
    live_path.write_text(
        json.dumps(live, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    return {
        "before_had_hours": "hours" in (before.get("contact") or {}),
        "hours_title": seed_hours.get("title", ""),
        "row_count": len(seed_hours.get("rows") or []),
    }


def upload_faz54_bundle(ftp: FTP, web_root: str, merged_content: Path) -> list[str]:
    uploaded: list[str] = []
    for rel in FAZ54_PUBLIC_REL:
        local_path = PUBLIC_HTML / rel
        remote = f"{web_root}/{rel}"
        upload_file(ftp, local_path, remote)
        uploaded.append(remote)
        if not assert_live_homepage():
            raise RuntimeError(f"Ana sayfa asserti başarısız ({remote} sonrası).")
    upload_file(ftp, merged_content, "content/content.json")
    uploaded.append("content/content.json")
    if not assert_live_homepage():
        raise RuntimeError("Ana sayfa asserti başarısız (content.json sonrası).")
    return uploaded


def assert_live_homepage() -> bool:
    import requests

    try:
        resp = requests.get("https://emirgandanismanlik.com/", timeout=30)
        return resp.status_code == 200 and "Güvenilir Çözüm Ortağınız" in resp.text
    except Exception:  # noqa: BLE001
        return False


def upload_config(ftp: FTP, web_root: str) -> None:
    remote = f"{web_root}/config.php"
    upload_file(ftp, CONFIG_PATH, remote)


def ftp_exists(ftp: FTP, remote_path: str) -> bool:
    try:
        ftp.size(remote_path)
        return True
    except error_perm:
        pass
    buf = io.BytesIO()
    try:
        ftp.retrbinary(f"RETR {remote_path}", buf.write)
        return buf.tell() > 0
    except error_perm:
        return False


def verify_post_deploy(ftp: FTP, web_root: str) -> dict[str, bool]:
    web_entries = {name.lower() for name in ftp_list_names(ftp, web_root)}
    root_entries = {name.lower() for name in ftp_list_names(ftp, ".")}
    uploads_htaccess = f"{web_root}/assets/img/uploads/.htaccess"
    return {
        "index_php": "index.php" in web_entries,
        "kvkk_php": "kvkk.php" in web_entries,
        "assets_dir": "assets" in web_entries,
        "admin_dir": "admin" in web_entries,
        "api_dir": "api" in web_entries,
        "htaccess": ftp_exists(ftp, f"{web_root}/.htaccess"),
        "uploads_htaccess": ftp_exists(ftp, uploads_htaccess),
        "content_outside_web_root": "content" in root_entries and "content" not in web_entries,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    host = require_env("FTP_HOST")
    user = require_env("FTP_USER")
    password = require_env("FTP_PASS")

    list_only = "--list-only" in sys.argv
    skip_config = "--skip-config" in sys.argv
    config_only = "--config-only" in sys.argv
    smtp_fix_config = "--smtp-fix-config" in sys.argv
    smtp_deploy = "--smtp-deploy" in sys.argv
    backup_only = "--backup-smtp" in sys.argv
    rollback_smtp = "--rollback-smtp" in sys.argv
    backup_dir = ROOT / ".tmp" / "live-smtp-backup"
    faz54_deploy = "--faz54-deploy" in sys.argv
    backup_faz54 = "--backup-faz54" in sys.argv
    rollback_faz54 = "--rollback-faz54" in sys.argv
    faz54_backup_dir = ROOT / ".tmp" / "live-faz54-backup"

    ftp = connect_ftp(host, user, password)
    root_listing = ftp_list_names(ftp, ".")
    print("Kök dizin:", ", ".join(sorted(root_listing)))

    if list_only:
        try:
            web_root = detect_web_root(ftp)
            print(f"Tespit edilen web kökü: {web_root}")
            print(f"Web kökü içeriği: {', '.join(sorted(ftp_list_names(ftp, web_root)))}")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    web_root = detect_web_root(ftp)
    verify_content_path_contract(web_root)
    print(f"Web kökü: {web_root}")

    if backup_only or smtp_deploy or rollback_smtp:
        if backup_only or smtp_deploy:
            backup_rows = backup_live_smtp_files(ftp, web_root, backup_dir)
            print(json.dumps({"backup": backup_rows, "backup_dir": str(backup_dir)}, ensure_ascii=False))
            if not all(backup_rows.values()):
                print("HATA: Canlı yedek eksik.", file=sys.stderr)
                ftp.quit()
                return 1
        if rollback_smtp:
            if not backup_dir.is_dir():
                print("HATA: Yedek dizini yok.", file=sys.stderr)
                ftp.quit()
                return 1
            restored = rollback_smtp_files(ftp, web_root, backup_dir)
            print(json.dumps({"restored": restored}, ensure_ascii=False))
            if not assert_live_homepage():
                print("HATA: Rollback sonrası ana sayfa asserti başarısız.", file=sys.stderr)
                ftp.quit()
                return 1
            ftp.quit()
            return 0
        if backup_only:
            ftp.quit()
            return 0

    if smtp_fix_config:
        if not assert_live_homepage():
            print("HATA: Fix öncesi ana sayfa asserti başarısız.", file=sys.stderr)
            ftp.quit()
            return 1
        smtp_user = "info@emirgandanismanlik.com"
        smtp_host = os.environ.get("SMTP_HOST", "").strip() or "mail.kurumsaleposta.com"
        smtp_pass = os.environ.get("SMTP_PASS", "").strip()
        if not smtp_pass:
            print("HATA: SMTP_PASS ortam değişkeni gerekli.", file=sys.stderr)
            ftp.quit()
            return 1
        probe = probe_smtp_settings(smtp_host, smtp_user, smtp_pass)
        if probe is None:
            print("HATA: SMTP probe başarısız.", file=sys.stderr)
            ftp.quit()
            return 1
        smtp_port, smtp_secure = probe
        backup_config = backup_dir / "config.php"
        if backup_config.is_file():
            CONFIG_PATH.write_bytes(backup_config.read_bytes())
        generate_live_config(
            None,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_secure=smtp_secure,
        )
        upload_config(ftp, web_root)
        if CONFIG_PATH.is_file():
            CONFIG_PATH.unlink()
            print("Yerel config.php silindi.")
        if not assert_live_homepage():
            print("HATA: Config fix sonrası ana sayfa — rollback.", file=sys.stderr)
            rollback_smtp_files(ftp, web_root, backup_dir)
            ftp.quit()
            return 1
        print(json.dumps({"fixed": "config.php", "smtp_host": smtp_host, "smtp_port": smtp_port, "smtp_secure": smtp_secure}, ensure_ascii=False))
        ftp.quit()
        return 0

    if smtp_deploy:
        if not assert_live_homepage():
            print("HATA: Deploy öncesi ana sayfa asserti başarısız.", file=sys.stderr)
            ftp.quit()
            return 1

        smtp_user = "info@emirgandanismanlik.com"
        smtp_host = os.environ.get("SMTP_HOST", "").strip() or "mail.kurumsaleposta.com"
        smtp_pass = os.environ.get("SMTP_PASS", "").strip()
        if not smtp_pass:
            print("HATA: SMTP_PASS ortam değişkeni gerekli.", file=sys.stderr)
            ftp.quit()
            return 1

        probe = probe_smtp_settings(smtp_host, smtp_user, smtp_pass)
        if probe is None:
            print("HATA: SMTP bağlantısı kurulamadı (465/ssl ve 587/tls).", file=sys.stderr)
            ftp.quit()
            return 1
        smtp_port, smtp_secure = probe
        print(json.dumps({"smtp_host": smtp_host, "smtp_port": smtp_port, "smtp_secure": smtp_secure}, ensure_ascii=False))

        admin_password: str | None = None
        backup_config = backup_dir / "config.php"
        if backup_config.is_file():
            CONFIG_PATH.write_bytes(backup_config.read_bytes())
        elif not CONFIG_PATH.is_file():
            admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()
            if not admin_password:
                admin_password = getpass.getpass("Canlı admin şifresi: ")
            if len(admin_password) < 8:
                print("HATA: Admin şifresi 8 karakterden kısa.", file=sys.stderr)
                ftp.quit()
                return 1

        generate_live_config(
            admin_password,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_secure=smtp_secure,
        )
        uploaded = upload_smtp_bundle(ftp, web_root)
        if CONFIG_PATH.is_file():
            CONFIG_PATH.unlink()
            print("Yerel config.php silindi.")
        if not assert_live_homepage():
            print("HATA: Deploy sonrası ana sayfa asserti başarısız — rollback.", file=sys.stderr)
            rollback_smtp_files(ftp, web_root, backup_dir)
            ftp.quit()
            return 1
        ftp.quit()
        print(json.dumps({"uploaded": uploaded, "smtp_port": smtp_port, "smtp_secure": smtp_secure}, ensure_ascii=False))
        return 0

    if backup_faz54 or faz54_deploy or rollback_faz54:
        if backup_faz54 or faz54_deploy:
            backup_rows = backup_live_faz54_files(ftp, web_root, faz54_backup_dir)
            print(json.dumps({"backup": backup_rows, "backup_dir": str(faz54_backup_dir)}, ensure_ascii=False))
            if not all(backup_rows.values()):
                print("HATA: Faz 5.4 canlı yedek eksik.", file=sys.stderr)
                ftp.quit()
                return 1
        if rollback_faz54:
            if not faz54_backup_dir.is_dir():
                print("HATA: Faz 5.4 yedek dizini yok.", file=sys.stderr)
                ftp.quit()
                return 1
            restored = rollback_faz54_files(ftp, web_root, faz54_backup_dir)
            print(json.dumps({"restored": restored}, ensure_ascii=False))
            if not assert_live_homepage():
                print("HATA: Faz 5.4 rollback sonrası ana sayfa asserti başarısız.", file=sys.stderr)
                ftp.quit()
                return 1
            ftp.quit()
            return 0
        if backup_faz54:
            ftp.quit()
            return 0

    if faz54_deploy:
        if not assert_live_homepage():
            print("HATA: Faz 5.4 deploy öncesi ana sayfa asserti başarısız.", file=sys.stderr)
            ftp.quit()
            return 1

        local_content = CONTENT_DIR / "content.json"
        seed = json.loads(local_content.read_text(encoding="utf-8"))
        seed_hours = seed.get("contact", {}).get("hours")
        if not seed_hours:
            print("HATA: Yerel content.json içinde contact.hours yok.", file=sys.stderr)
            ftp.quit()
            return 1

        merge_dir = ROOT / ".tmp" / "live-faz54-merge"
        merge_dir.mkdir(parents=True, exist_ok=True)
        live_content_copy = merge_dir / "content.json"
        live_content_copy.write_bytes((faz54_backup_dir / "content.json").read_bytes())
        merge_summary = merge_contact_hours_seed(live_content_copy, seed_hours)

        try:
            uploaded = upload_faz54_bundle(ftp, web_root, live_content_copy)
        except RuntimeError as exc:
            print(f"HATA: {exc} — rollback.", file=sys.stderr)
            rollback_faz54_files(ftp, web_root, faz54_backup_dir)
            ftp.quit()
            return 1

        ftp.quit()
        print(
            json.dumps(
                {"uploaded": uploaded, "content_merge": merge_summary},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"İçerik hedefi: content/ (web kökünün bir üst dizini)")

    public_count = 0
    content_count = 0
    removed_placeholders: list[str] = []
    if not config_only:
        public_count = deploy_public_html(ftp, web_root)
        content_count = deploy_content(ftp)
        removed_placeholders = cleanup_natro_placeholders(ftp, web_root)
        chmod_rows = apply_chmod(ftp, web_root)
    else:
        chmod_rows = []

    config_uploaded = False
    if not skip_config:
        admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()
        if not admin_password:
            admin_password = getpass.getpass("Canlı admin şifresi: ")
            confirm = getpass.getpass("Şifre tekrar: ")
            if admin_password != confirm:
                print("HATA: Şifreler eşleşmiyor.", file=sys.stderr)
                return 1
        if len(admin_password) < 8:
            print("HATA: Şifre 8 karakterden kısa.", file=sys.stderr)
            return 1
        generate_live_config(admin_password)
        upload_config(ftp, web_root)
        config_uploaded = True
        if CONFIG_PATH.is_file():
            CONFIG_PATH.unlink()
            print("Yerel config.php silindi.")

    checks = verify_post_deploy(ftp, web_root)
    ftp.quit()

    report = {
        "mapping": {
            "repo_public_html": f"public_html/ -> /{web_root}/",
            "repo_content": "content/ -> /content/ (web kokunun disinda)",
        },
        "uploaded_public_files": public_count,
        "uploaded_content_files": content_count,
        "removed_placeholders": removed_placeholders,
        "config_uploaded": config_uploaded,
        "chmod": chmod_rows,
        "post_checks": checks,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

    required = [
        "index_php",
        "kvkk_php",
        "assets_dir",
        "admin_dir",
        "api_dir",
        "htaccess",
        "uploads_htaccess",
        "content_outside_web_root",
    ]
    if config_only:
        if not config_uploaded:
            print("HATA: --config-only ile config yüklenemedi.", file=sys.stderr)
            return 1
        return 0
    if not all(checks.get(key) for key in required):
        print("HATA: FTP sonrası zorunlu dosya/dizin kontrolleri başarısız.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
