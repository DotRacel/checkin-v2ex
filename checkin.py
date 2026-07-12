#!/usr/bin/env python3
"""V2EX daily check-in. Auth via browser cookie, optional Apprise notify.

Exit: 0 claimed, 2 already claimed today, 1 failure.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

BASE_URL = "https://www.v2ex.com"
MISSION_URL = f"{BASE_URL}/mission/daily"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

log = logging.getLogger("v2ex-checkin")


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Config:
    cookie: str
    user_agent: str
    apprise_urls: list[str]
    timeout: int
    retries: int
    run_mode: str
    checkin_time: str

    @classmethod
    def from_env(cls) -> "Config":
        cookie = os.environ.get("V2EX_COOKIE", "").strip()
        if not cookie:
            raise SystemExit("V2EX_COOKIE is not set (see .env.example).")
        urls = [u.strip() for u in re.split(r"[\n,]", os.environ.get("APPRISE_URLS", "")) if u.strip()]
        return cls(
            cookie=cookie,
            user_agent=os.environ.get("V2EX_USER_AGENT", DEFAULT_UA),
            apprise_urls=urls,
            timeout=int(os.environ.get("HTTP_TIMEOUT", "20")),
            retries=int(os.environ.get("HTTP_RETRIES", "3")),
            run_mode=os.environ.get("RUN_MODE", "once").lower(),
            checkin_time=os.environ.get("CHECKIN_TIME", "08:30"),
        )


@dataclass
class CheckinResult:
    status: str  # claimed | already | auth_failed | error
    message: str
    streak: int | None = None
    balance: str | None = None

    @property
    def exit_code(self) -> int:
        return {"claimed": 0, "already": 2}.get(self.status, 1)

    @property
    def ok(self) -> bool:
        return self.status in ("claimed", "already")

    def title(self) -> str:
        icon = {"claimed": "✅", "already": "ℹ️", "auth_failed": "🔑", "error": "❌"}
        return f"{icon.get(self.status, '❓')} V2EX 签到 {self.status}"

    def body(self) -> str:
        parts = [self.message]
        if self.streak is not None:
            parts.append(f"已连续登录 {self.streak} 天")
        if self.balance:
            parts.append(f"当前余额: {self.balance}")
        return "\n".join(parts)


def build_session(cfg: Config) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": cfg.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cookie": cfg.cookie,
    })
    return s


def get(session: requests.Session, url: str, cfg: Config, *, referer: str | None = None):
    headers = {"Referer": referer} if referer else {}
    last_exc: Exception | None = None
    for attempt in range(1, cfg.retries + 1):
        try:
            return session.get(url, headers=headers, timeout=cfg.timeout, allow_redirects=False)
        except requests.RequestException as exc:
            last_exc = exc
            wait = min(2 ** attempt, 10)
            log.warning("GET %s failed (%d/%d): %s; retry in %ds", url, attempt, cfg.retries, exc, wait)
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]


REDEEM_RE = re.compile(r"/mission/daily/redeem\?once=(\d+)")
STREAK_RE = re.compile(r"已连续登录\s*(\d+)\s*天")
BALANCE_RE = re.compile(r"(\d+)\s*<img[^>]*/(gold|silver|bronze)@2x", re.IGNORECASE)
ALREADY_RE = re.compile(r"每日登录奖励已领取|已领取")


def parse_streak(html: str) -> int | None:
    m = STREAK_RE.search(html)
    return int(m.group(1)) if m else None


def parse_balance(html: str) -> str | None:
    label = {"gold": "金", "silver": "银", "bronze": "铜"}
    pairs = [(m.group(2).lower(), m.group(1)) for m in BALANCE_RE.finditer(html)]
    return " ".join(f"{amt} {label[k]}" for k, amt in pairs) or None


def is_auth_redirect(resp) -> bool:
    if resp.status_code in (301, 302, 303, 307, 308):
        loc = resp.headers.get("Location", "")
        return any(p in loc for p in ("/2fa", "/signin", "/login"))
    return False


def do_checkin(cfg: Config) -> CheckinResult:
    session = build_session(cfg)
    try:
        resp = get(session, MISSION_URL, cfg)
    except requests.RequestException as exc:
        return CheckinResult("error", f"网络错误，无法访问签到页: {exc}")

    if is_auth_redirect(resp):
        loc = resp.headers.get("Location", "")
        return CheckinResult("auth_failed", f"会话已失效 (跳转到 {loc})，请更新 V2EX_COOKIE。")
    if resp.status_code != 200:
        return CheckinResult("error", f"签到页返回异常状态码 {resp.status_code}")

    html = resp.text
    streak, balance = parse_streak(html), parse_balance(html)

    match = REDEEM_RE.search(html)
    if not match:
        if ALREADY_RE.search(html):
            return CheckinResult("already", "今日已签到，无需重复领取。", streak, balance)
        return CheckinResult("error", "未找到领取按钮，页面结构可能已变化。")

    once = match.group(1)
    log.info("Claiming daily reward")
    try:
        redeem_resp = get(session, f"{BASE_URL}/mission/daily/redeem?once={once}", cfg, referer=MISSION_URL)
    except requests.RequestException as exc:
        return CheckinResult("error", f"领取请求失败: {exc}")
    if is_auth_redirect(redeem_resp):
        return CheckinResult("auth_failed", "领取时会话失效，请更新 Cookie。")

    try:
        confirm = get(session, MISSION_URL, cfg)
        chtml = confirm.text if confirm.status_code == 200 else ""
    except requests.RequestException:
        chtml = ""

    if chtml:
        streak = parse_streak(chtml) or streak
        balance = parse_balance(chtml) or balance
        confirmed = ALREADY_RE.search(chtml) and not REDEEM_RE.search(chtml)
    else:
        confirmed = redeem_resp.status_code in (200, 302)

    if confirmed:
        return CheckinResult("claimed", "签到成功，已领取每日登录奖励！", streak, balance)
    return CheckinResult("error", "已发送领取请求，但未能确认状态，请手动核对。", streak, balance)


def notify(cfg: Config, result: CheckinResult) -> None:
    if not cfg.apprise_urls:
        return
    try:
        import apprise
    except ImportError:
        log.warning("apprise not installed; skipping notification.")
        return
    ap = apprise.Apprise()
    for i, url in enumerate(cfg.apprise_urls):
        if not ap.add(url):
            log.warning("Apprise rejected notification URL #%d", i + 1)
    if ap.urls():
        log.info("Notification sent: %s", ap.notify(title=result.title(), body=result.body()))


def run_once(cfg: Config) -> int:
    result = do_checkin(cfg)
    (log.info if result.ok else log.error)("%s | %s", result.title(), result.body().replace("\n", " | "))
    notify(cfg, result)
    return result.exit_code


def run_daemon(cfg: Config) -> int:
    log.info("Daemon mode: daily check-in at %s (local time)", cfg.checkin_time)
    target = tuple(int(x) for x in cfg.checkin_time.split(":"))
    last_run_day = None
    while True:
        now = time.localtime()
        today = (now.tm_year, now.tm_yday)
        if (now.tm_hour, now.tm_min) >= target and last_run_day != today:
            run_once(cfg)
            last_run_day = today
        time.sleep(30)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    load_dotenv(Path(__file__).with_name(".env"))
    cfg = Config.from_env()
    return run_daemon(cfg) if cfg.run_mode == "daemon" else run_once(cfg)


if __name__ == "__main__":
    sys.exit(main())
