# family-calculator-data

가족 계산기 앱이 읽어 가는 **공개 데이터** 저장소입니다. 앱 코드는 들어 있지 않습니다.

## 환율 — `exchange/rates.json`

- 출처: [한국수출입은행 현재환율 Open API](https://www.koreaexim.go.kr/ir/HPHKIR020M01?apino=2&viewtype=C) 매매기준율
- 갱신: GitHub Actions(`.github/workflows/exchange-rates.yml`)가 평일 11:30, 16:00(KST)에 받아 바뀌었을 때만 커밋
- 주말·공휴일·고시 전에는 가장 최근 영업일 고시값을 유지
- 인증키는 저장소 시크릿 `KOREAEXIM_API_KEY`에만 있고, 앱·파일에는 없습니다.

```json
{
  "version": 1,
  "source": "한국수출입은행 현재환율 (매매기준율)",
  "noticeDate": "2026-11-06",
  "fetchedAt": "2026-11-06T11:30:12+09:00",
  "rates": [
    { "code": "USD", "name": "미국 달러", "unit": 1, "krw": "1385.5" },
    { "code": "JPY", "name": "일본 옌", "unit": 100, "krw": "912.34" }
  ]
}
```

- `unit`: 고시 단위. `JPY`·`IDR`은 **100 단위**(100엔 = `krw`원)입니다.
- `krw`: 소수 정확도를 위해 문자열로 저장합니다.
- 매매기준율은 은행·카드사의 실제 환전·결제 환율과 다를 수 있습니다(수수료 미포함).

## 인증키 관리

- 수출입은행 개인정보 보유기간(2년)이 지나면 키가 파기됩니다. 만료 전 오는 "재동의" 메일에 꼭 동의하세요.
- 워크플로가 `API result 3`으로 실패하면 키 만료/오류이니 새로 발급받아 시크릿을 교체하세요.
