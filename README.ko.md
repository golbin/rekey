[English](README.md) · **한국어** · [中文](README.zh.md) · [日本語](README.ja.md) · [Español](README.es.md)

# rekey

API 키를 한 명령으로 재발급하고, 쓰이는 모든 곳(.env, Vercel, Railway, Supabase, GCP, GitHub…)에 반영하고, 옛 키를 폐기합니다.

```bash
rekey rotate 'openai.*'   # 새 키 발급 → 모든 사용처 교체 → 재배포 확인
rekey revoke 'openai.*'   # 옛 키 폐기
```

- 서비스를 몰라도 됩니다. API로 발급할 수 있는 키는 자동으로 처리합니다. 나머지는 발급 페이지를 열어 주니 키를 만들고 **복사만** 하면 됩니다.
- 키 값은 화면에 나오지 않습니다. 1Password에만 저장됩니다.
- Python 3.11 이상, 표준 라이브러리만 씁니다.

## 동작 방식

| 무엇 | 어디에 |
|---|---|
| 키 값 | 1Password (항목 하나 = 키 하나) |
| 키가 쓰이는 곳, 일반 설정값 | `targets/**.tpl`: 팀 비공개 저장소 |
| 예외 정보 (잠금·태그·메모) | `keys.toml`: 팀 비공개 저장소 |

템플릿은 1Password 표준 문법 그대로이고, 파일 경로가 곧 값이 들어갈 곳입니다.

```
# targets/vercel/shop/production.tpl  →  Vercel 프로젝트 shop의 production 환경
APP_URL=https://shop.example.com
OPENAI_API_KEY={{ op://Acme - Prod/openai.shop/credential }}
```

## 가이드

1. [처음 준비](docs/ko/setup.md): 10분
2. [사용법](docs/ko/usage.md)
3. 상황별: [키 하나가 유출됐다](docs/ko/situations/key-leaked.md) · [쓰는 플랫폼이 해킹당했다](docs/ko/situations/platform-breach.md) · [팀원이 나갔다](docs/ko/situations/member-left.md)

## 개발

```bash
python3 -m unittest discover -s tests
REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py   # 터미널 조작 테스트 (macOS, 클립보드 사용)
```

MIT License
