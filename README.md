# family-calculator-data

가족 계산기 앱이 읽어 가는 데이터 저장소입니다. 앱 코드는 들어 있지 않습니다.

## 환율 — `exchange/rates.dat`

- 출처: [한국수출입은행 현재환율 Open API](https://www.koreaexim.go.kr/ir/HPHKIR020M01?apino=2&viewtype=C) 매매기준율
  (공공데이터포털 등록 정보: [이용허락범위 제한 없음](https://www.data.go.kr/data/3068846/openapi.do)). 값은 바꾸지 않고 형식만 바꿉니다.
- 갱신: GitHub Actions(`.github/workflows/exchange-rates.yml`)가 평일 11:30, 16:00(KST)에 받아 바뀌었을 때만 커밋
- 주말·공휴일·고시 전에는 가장 최근 영업일 고시값을 유지
- 앱은 이 파일을 GitHub에서 받고, 실패하면 jsDelivr(`cdn.jsdelivr.net/gh/iTiSt-K/family-calculator-data@main/exchange/rates.dat`)에서 받습니다.

### 형식 (v2)

```json
{ "v": 2, "kid": 1, "payload": "<base64>", "sig": "<base64>" }
```

- `sig`: `payload` 바이트에 대한 **Ed25519 서명**. 앱은 내장 공개키(`kid`로 선택)로 확인하고, 맞지 않으면 파일 전체를 버립니다.
- `payload`: 환율 JSON → gzip → 고정 키 XOR → base64. XOR은 평문이 바로 보이지 않게 하는 약속일 뿐 **보안 장치가 아닙니다**.
- 풀린 JSON:

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

## 키 관리

- `KOREAEXIM_API_KEY`: 수출입은행 인증키. 개인정보 보유기간(2년)이 지나면 파기되므로 만료 전 "재동의" 메일에 꼭 동의하세요.
  워크플로가 `API result 3`으로 실패하면 키 만료/오류이니 새로 발급받아 시크릿을 교체하세요.
- `RATES_SIGNING_KEY`: 서명용 Ed25519 비밀키(PEM). 저장소 밖 어디에도 사본이 없습니다.
  교체 시: 새 키 생성 → 앱에 새 공개키를 다음 `kid`로 추가해 배포 → 시크릿 교체 + 스크립트의 `KEY_ID` 증가.
