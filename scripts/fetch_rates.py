"""한국수출입은행 현재환율(매매기준율)을 받아 exchange/rates.dat 으로 저장한다.

- 인증키는 GitHub Actions 시크릿 KOREAEXIM_API_KEY 로만 받는다(앱·저장소에 키 없음).
- 주말·공휴일·고시 전(오전 11시 전후)에는 그날 데이터가 비어 있으므로
  가장 최근 영업일까지 하루씩 거슬러 올라간다.
- 금액은 정확성을 위해 숫자가 아니라 문자열("1385.5")로 저장한다.
- 고시일과 환율이 이전 파일과 같으면 파일을 다시 쓰지 않는다(불필요한 커밋 방지).

파일 형식(v2) — README 참고:
  {"v":2,"kid":1,"payload":base64(XOR(gzip(JSON))),"sig":base64(Ed25519(payload 바이트))}
- 서명: 시크릿 RATES_SIGNING_KEY(Ed25519 PEM)로 openssl 이 서명한다. 앱은 공개키로 확인해
  서명이 맞지 않는 파일(위변조)을 버린다. ← 실제 보안 장치
- XOR: 앱과 정한 고정 키로 섞어 평문이 바로 보이지 않게 할 뿐이다. 공개 저장소·앱에서 누구나
  알 수 있는 키라 보안 장치가 아니다(도구로 대충 퍼 가는 것만 귀찮게 하는 "약속").
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
OUT = Path(__file__).resolve().parent.parent / "exchange" / "rates.dat"
KST = timezone(timedelta(hours=9))
MAX_LOOKBACK_DAYS = 10

FORMAT_VERSION = 2
KEY_ID = 1  # 서명 키 번호. 키를 바꾸면 올리고, 앱에 새 공개키를 같은 번호로 추가한다.
XOR_KEY = b"family-calculator/exchange/v2"  # 앱 rates_envelope.dart 의 값과 같아야 한다.
RESULT_MESSAGES = {
    2: "DATA 코드 오류",
    3: "인증키 오류 (키가 틀렸거나, 2년 보유기간 만료로 파기됐을 수 있음)",
    4: "일일 호출 한도(1,000회) 초과",
}


def fetch(key: str, day: datetime) -> list[dict]:
    query = urllib.parse.urlencode(
        {"authkey": key, "searchdate": day.strftime("%Y%m%d"), "data": "AP01"}
    )
    request = urllib.request.Request(
        f"{API_URL}?{query}", headers={"User-Agent": "family-calculator-data"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    items = json.loads(body) if body.strip() else []
    for item in items:
        result = item.get("result")
        if result not in (None, 1):
            raise SystemExit(f"API result {result}: {RESULT_MESSAGES.get(result, '알 수 없는 오류')}")
    return items


# 앱이 받아들이는 형식과 같다(앱도 같은 규칙으로 검사해, 어긋나면 파일 전체를 버린다).
# 이상한 값을 게시해 모든 사용자의 갱신을 막기보다, 여기서 실패해 이전 파일을 유지한다.
CODE_RE = re.compile(r"^[A-Z]{3}$")
KRW_RE = re.compile(r"^\d{1,9}(\.\d{1,6})?$")
UNIT_RE = re.compile(r"^\d{1,5}$")
MAX_NAME = 40


def parse(items: list[dict]) -> list[dict]:
    rates = []
    for item in items:
        raw_unit = str(item.get("cur_unit") or "")  # "USD", "JPY(100)"
        code, _, rest = raw_unit.partition("(")
        code = code.strip()
        base = str(item.get("deal_bas_r") or "").replace(",", "").strip()
        if not code or code == "KRW" or not base:
            continue
        unit_text = rest.rstrip(")").strip() if rest else "1"
        name = str(item.get("cur_nm") or code).strip()
        if (
            not CODE_RE.match(code)
            or not KRW_RE.match(base)
            or float(base) <= 0
            or not UNIT_RE.match(unit_text)
            or not 1 <= int(unit_text) <= 10000
            or len(name) > MAX_NAME
        ):
            raise SystemExit(f"예상과 다른 환율 항목이라 게시하지 않습니다: {raw_unit!r} {base!r}")
        rates.append({"code": code, "name": name, "unit": int(unit_text), "krw": base})
    if len({r["code"] for r in rates}) != len(rates):
        raise SystemExit("통화 코드가 중복돼 게시하지 않습니다.")
    return rates


def xor(data: bytes) -> bytes:
    return bytes(b ^ XOR_KEY[i % len(XOR_KEY)] for i, b in enumerate(data))


def encode(data: dict) -> bytes:
    plain = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return xor(gzip.compress(plain, mtime=0))


def decode(payload: bytes) -> dict:
    return json.loads(gzip.decompress(xor(payload)).decode("utf-8"))


def sign(payload: bytes) -> bytes:
    """openssl 로 Ed25519 서명. 비밀키는 임시 파일에만 잠깐 두고 지운다."""
    pem = os.environ.get("RATES_SIGNING_KEY", "")
    if "PRIVATE KEY" not in pem:
        raise SystemExit("RATES_SIGNING_KEY 가 비어 있거나 형식이 다릅니다.")
    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / "key.pem"
        msg = Path(tmp) / "payload.bin"
        sig = Path(tmp) / "sig.bin"
        key.touch(mode=0o600)
        key.write_text(pem, encoding="utf-8")
        msg.write_bytes(payload)
        subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-inkey", str(key), "-rawin",
             "-in", str(msg), "-out", str(sig)],
            check=True,
            capture_output=True,
        )
        signature = sig.read_bytes()
    if len(signature) != 64:
        raise SystemExit("서명 길이가 올바르지 않습니다.")
    return signature


def read_previous() -> dict | None:
    try:
        envelope = json.loads(OUT.read_text(encoding="utf-8"))
        return decode(base64.b64decode(envelope["payload"]))
    except (OSError, ValueError, KeyError):
        return None  # 없거나 형식이 바뀐 파일 → 새로 쓴다


def main() -> None:
    key = os.environ.get("KOREAEXIM_API_KEY", "").strip()
    if not key:
        raise SystemExit("KOREAEXIM_API_KEY 가 비어 있습니다.")

    now = datetime.now(KST)
    for back in range(MAX_LOOKBACK_DAYS):
        day = now - timedelta(days=back)
        rates = parse(fetch(key, day))
        if rates:
            break
    else:
        raise SystemExit(f"최근 {MAX_LOOKBACK_DAYS}일 동안 고시 환율이 없습니다.")

    data = {
        "version": 1,
        "source": "한국수출입은행 현재환율 (매매기준율)",
        "noticeDate": day.strftime("%Y-%m-%d"),
        "fetchedAt": now.isoformat(timespec="seconds"),
        "rates": rates,
    }

    old = read_previous()
    if old and old.get("noticeDate") == data["noticeDate"] and old.get("rates") == data["rates"]:
        print(f"변경 없음: {data['noticeDate']} 고시, {len(rates)}개 통화")
        return

    payload = encode(data)
    if decode(payload) != data:  # 왕복 확인
        raise SystemExit("인코딩 왕복 검사 실패")
    envelope = {
        "v": FORMAT_VERSION,
        "kid": KEY_ID,
        "payload": base64.b64encode(payload).decode("ascii"),
        "sig": base64.b64encode(sign(payload)).decode("ascii"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    print(f"저장: {data['noticeDate']} 고시, {len(rates)}개 통화")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as error:  # 네트워크/SSL 문제는 실패로 표시
        print(f"요청 실패: {error}", file=sys.stderr)
        sys.exit(1)
