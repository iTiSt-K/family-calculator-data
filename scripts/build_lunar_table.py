"""한국천문연구원(KASI) 음양력 정보 API로 음력표(lunar/table.json)를 만든다.

- 인증키는 GitHub Actions 시크릿 KASI_API_KEY 로만 받는다(앱·저장소에 키 없음).
- 양력 날짜 → 음력 날짜(getLunCalInfo)를 양력 한 달씩 조회해, 음력 해마다
  "설날(음력 1월 1일)의 양력 날짜 + 달마다 날 수 + 윤달" 로 줄인다.
- 음력표는 이미 정해진 값이라 한 번 만들면 된다(수동 실행 워크플로).
- 범위: 음력 1900년(양력 1900-01-31)부터 KASI가 제공하는 마지막 해까지. 끝 연도는
  실제 조회로 찾는다(추정하지 않는다). 조회 결과가 앞뒤로 어긋나면 실패시킨다.

출력 형식 — README 참고:
  {"years":[{"y":1900,"start":"1900-01-31","leap":8,"days":[29,30,...]}]}
  days 는 달 순서대로(윤달이 있으면 그 달 바로 뒤에 윤달), leap 은 윤달이 붙는 달(없으면 0).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API = "https://apis.data.go.kr/B090041/openapi/service/LrsrCldInfoService/getLunCalInfo"
OUT = Path(__file__).resolve().parent.parent / "lunar" / "table.json"
FIRST_SOLAR_YEAR = 1900
PROBE_LAST_YEAR = 2200  # 끝 연도를 찾을 때 이보다 뒤는 보지 않는다
KST = timezone(timedelta(hours=9))


def call(key: str, year: int, month: int) -> list[dict]:
    """양력 year-month 의 모든 날(최대 31개)에 대한 음력 정보. 데이터가 없으면 []."""
    query = urllib.parse.urlencode(
        {"solYear": f"{year:04d}", "solMonth": f"{month:02d}", "numOfRows": 31,
         "_type": "json", "ServiceKey": key}
    )
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": "family-calculator-data"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
            break
        except urllib.error.URLError as error:  # 일시 오류는 잠깐 쉬고 다시
            if attempt == 3:
                raise SystemExit(f"요청 실패 {year}-{month:02d}: {error.reason}")
            time.sleep(2 * (attempt + 1))
    if not body.lstrip().startswith("{"):
        # 키 미등록 등은 XML 오류로 온다(키 값은 들어 있지 않음).
        raise SystemExit(f"API 오류 응답 {year}-{month:02d}: {body[:300]}")
    data = json.loads(body)["response"]
    code = data["header"]["resultCode"]
    if code != "00":
        raise SystemExit(f"API 결과 {code} {year}-{month:02d}: {data['header'].get('resultMsg')}")
    items = (data.get("body") or {}).get("items") or {}
    item = items.get("item") if isinstance(items, dict) else None
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


def has_data(key: str, year: int) -> bool:
    return bool(call(key, year, 12))


def find_last_year(key: str) -> int:
    """양력 12월 자료가 있는 마지막 해(이진 탐색)."""
    if not has_data(key, FIRST_SOLAR_YEAR):
        raise SystemExit(f"{FIRST_SOLAR_YEAR}년 자료가 없습니다.")
    lo, hi = FIRST_SOLAR_YEAR, PROBE_LAST_YEAR
    if has_data(key, hi):
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if has_data(key, mid):
            lo = mid
        else:
            hi = mid
    return lo


def collect(key: str, last_year: int) -> list[tuple[date, int, int, bool, int, int]]:
    """(양력, 음력년, 음력월, 윤달?, 음력일, 그 달 날 수) — 양력 순서."""
    rows = []
    for year in range(FIRST_SOLAR_YEAR, last_year + 1):
        for month in range(1, 13):
            for it in call(key, year, month):
                rows.append((
                    date(int(it["solYear"]), int(it["solMonth"]), int(it["solDay"])),
                    int(it["lunYear"]), int(it["lunMonth"]),
                    str(it["lunLeapmonth"]).strip() == "윤",
                    int(it["lunDay"]), int(it["lunNday"]),
                ))
            time.sleep(0.05)
        print(f"{year} 완료", flush=True)
    rows.sort(key=lambda r: r[0])
    return rows


def build(rows: list[tuple[date, int, int, bool, int, int]]) -> list[dict]:
    # 1) 하루도 빠짐없이 이어지는지
    for a, b in zip(rows, rows[1:]):
        if b[0] - a[0] != timedelta(days=1):
            raise SystemExit(f"양력 날짜가 끊김: {a[0]} → {b[0]}")

    # 2) 음력 달 단위로 묶기: (년, 월, 윤) → 시작 양력, 날 수
    months: list[dict] = []
    for solar, ly, lm, leap, ld, nday in rows:
        if ld == 1:
            months.append({"y": ly, "m": lm, "leap": leap, "start": solar, "days": nday, "seen": 0})
        if not months:
            continue  # 첫 음력 초하루 이전
        cur = months[-1]
        if (cur["y"], cur["m"], cur["leap"]) != (ly, lm, leap) or ld != cur["seen"] + 1 \
                or nday != cur["days"]:
            raise SystemExit(f"음력 날짜가 어긋남: {solar} = {ly}-{lm}{'(윤)' if leap else ''}-{ld}")
        cur["seen"] = ld
    # 앞뒤로 잘린 달은 버린다(첫 설날 이전, 마지막 해의 끝).
    months = [m for m in months if m["seen"] == m["days"]]

    # 3) 음력 해 단위로
    years: list[dict] = []
    for m in months:
        if m["days"] not in (29, 30):
            raise SystemExit(f"한 달 날 수가 이상함: {m}")
        if m["m"] == 1 and not m["leap"]:
            years.append({"y": m["y"], "start": m["start"].isoformat(), "leap": 0, "days": [], "_order": []})
        if not years or years[-1]["y"] != m["y"]:
            continue  # 첫 설날 이전 자투리
        year = years[-1]
        year["_order"].append((m["m"], m["leap"]))
        year["days"].append(m["days"])
        if m["leap"]:
            year["leap"] = m["m"]

    # 4) 해마다 1~12월(+윤달 하나)이 순서대로 다 있는지. 마지막 해가 덜 찼으면 버린다.
    complete = []
    for year in years:
        expected = [(i, False) for i in range(1, 13)]
        if year["leap"]:
            expected.insert(year["leap"], (year["leap"], True))
        if year["_order"] == expected:
            del year["_order"]
            complete.append(year)
        elif year is years[-1]:
            print(f"마지막 음력 {year['y']}년은 자료가 끝까지 없어 제외")
        else:
            raise SystemExit(f"음력 {year['y']}년 달 순서가 이상함: {year['_order']}")

    # 5) 다음 해 설날 = 이번 해 시작 + 날 수 합
    for a, b in zip(complete, complete[1:]):
        end = date.fromisoformat(a["start"]) + timedelta(days=sum(a["days"]))
        if end.isoformat() != b["start"] or b["y"] != a["y"] + 1:
            raise SystemExit(f"음력 {a['y']} → {b['y']} 이어지지 않음")
    return complete


def main() -> None:
    key = os.environ.get("KASI_API_KEY", "").strip()
    if not key:
        raise SystemExit("KASI_API_KEY 가 비어 있습니다.")

    last = find_last_year(key)
    print(f"KASI 제공 범위 확인: 양력 {FIRST_SOLAR_YEAR}~{last}년")
    years = build(collect(key, last))
    first, final = years[0], years[-1]
    final_end = date.fromisoformat(final["start"]) + timedelta(days=sum(final["days"]) - 1)

    data = {
        "version": 1,
        "source": "한국천문연구원 음양력 정보 (공공데이터포털 15012679)",
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "firstSolar": first["start"],
        "lastSolar": final_end.isoformat(),
        "years": years,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"저장: 음력 {first['y']}~{final['y']}년 (양력 {first['start']} ~ {final_end})")


if __name__ == "__main__":
    main()
