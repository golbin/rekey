[English](README.md) · **한국어** · [中文](README.zh.md) · [日本語](README.ja.md) · [Español](README.es.md)

# rekey

API 키를 한 명령으로 재발급하고, 쓰이는 모든 곳(.env, Vercel, Railway, Supabase, GCP, GitHub…)에 반영하고, 옛 키를 폐기합니다.

```bash
pipx install git+https://github.com/golbin/rekey   # 설치
rekey rotate project:shop   # 새 키 발급 → 모든 사용처 교체 → 서비스마다 재배포 시점 선택
rekey revoke project:shop   # 옛 키 폐기
```

- **잊고 있던 키까지 찾습니다.** `rekey init`은 기억에 의존하지 않고 모든 .env 파일과 Vercel·Railway·Supabase·GCP를 직접 읽습니다. 같은 값은 하나로 묶으므로, 아무도 기억하지 못하는 프로젝트를 포함해 스무 곳에 복사된 키도 하나로 정리됩니다. rekey가 읽을 수 없는 곳(팀원의 PC, 외부 서비스 대시보드)은 템플릿에 한 줄만 적어 두면 다시는 잊지 않습니다.
- 서비스를 몰라도 됩니다. API로 발급할 수 있는 키는 자동으로 처리합니다. 나머지는 발급 페이지를 열어 주니 키를 만들고 **복사만** 하면 됩니다.
- 키 값은 화면에 나오지 않습니다. 1Password에만 저장됩니다.
- Python 3.11 이상, 표준 라이브러리만 씁니다.
- 안내 문구는 시스템 언어를 따릅니다(English, 한국어, 中文, 日本語, Español). `REKEY_LANG=ko`로 정할 수도 있습니다.

## 동작 방식

| 무엇 | 어디에 |
|---|---|
| 키 값 | 1Password: 환경마다 볼트 하나(`Acme - Prod`, `Acme - Dev`, `Acme - Local`), 키마다 항목 하나, 이름은 `<프로젝트>.<서비스>` |
| 키가 쓰이는 곳, 일반 설정값 | `targets/<project>/**.tpl`: 팀 비공개 저장소 |
| 예외 정보 (잠금·태그·메모) | `keys.toml`: 팀 비공개 저장소 |

템플릿은 1Password 표준 문법 그대로이고, 파일 경로가 곧 값이 들어갈 곳입니다.

```
# targets/shop/vercel/shop/production.tpl  →  Vercel 프로젝트 shop의 production 환경
APP_URL=https://shop.example.com
OPENAI_API_KEY={{ op://Acme - Prod/shop.openai/credential }}
```

## 가이드

0. [팀 데이터 예시](https://github.com/golbin/rekey-example): 어떻게 생겼는지 보고 **Use this template**으로 시작
1. [처음 준비](docs/ko/setup.md): 10분
2. [사용법](docs/ko/usage.md)
3. 상황별: [키 하나가 유출됐다](docs/ko/situations/key-leaked.md) · [쓰는 플랫폼이 해킹당했다](docs/ko/situations/platform-breach.md) · [팀원이 나갔다](docs/ko/situations/member-left.md)

## 개발

```bash
python3 -m unittest discover -s tests
REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py   # 터미널 조작 테스트 (macOS, 클립보드 사용)
```

MIT License
