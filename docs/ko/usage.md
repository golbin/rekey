# 사용법

명령은 팀 데이터 폴더 안에서 실행합니다. 바꾸는 명령(`rotate`, `issue`, `revoke`, `sync`, `import`, `arrange`)은 `--dry-run`을 붙이면 미리 보기만 합니다.

## 로컬 .env 만들기

```bash
rekey sync targets/file/shop/web/.env.local.tpl
```

- 키는 1Password에서 채웁니다. 파일에 있던 다른 줄은 그대로 둡니다.
- 로컬 템플릿에는 **키만** 들어 있습니다. 포트 같은 로컬 설정은 직접 적거나 프로젝트의 `.env.example`을 참고하세요.
- 팀이 같이 쓸 로컬 설정이 있으면 템플릿에 `KEY=값` 한 줄을 추가하세요. 다음 `sync`부터 함께 만들어집니다.

## 기존 .env에서 템플릿 만들기

```bash
rekey init ~/code/shop/web/.env.local                   # 파일 하나
rekey init ~/code/shop --with-settings                   # 폴더 안의 .env 전부, 일반 설정값 포함
```

- 키는 `{{ op://… }}` 참조로 바뀝니다. 이미 템플릿에 있는 키와 값이 같으면 그 키를 그대로 씁니다.
- 템플릿이 이미 있으면 없는 변수만 덧붙이고, 고쳐 둔 줄은 그대로 둡니다.
- `--with-settings`가 없으면 로컬 템플릿에 일반 설정값(포트, URL 등)은 넣지 않습니다.
- 그다음 `rekey arrange "Acme - {env}"`로 새 키를 맞는 볼트에 넣고, `rekey import`로 값을 1Password에 저장합니다.

## 키 찾기

```bash
rekey ls                     # 전체: 서비스, 발급 방식, 사용처 수, 태그
rekey ls project:shop        # 프로젝트 하나
rekey ls '*.openai'          # 서비스 하나
rekey where shop.openai      # 이 키가 들어간 템플릿과 변수
```

## 키 교체

```bash
rekey rotate shop.openai
```

1. 준비 점검을 합니다. 빠진 로그인 등은 그 자리에서 해결합니다.
2. 할 일을 요약해 보여 주고 시작할지 묻습니다.
3. 새 키를 받습니다.
   - **자동:** API로 발급하거나 로컬에서 생성합니다. 권한이 없는 등으로 안 되면 이유를 보여 주고 브라우저로 넘어갑니다.
   - **브라우저:** 무엇을 누를지 안내와 함께 페이지가 열립니다. 이름 칸에 ⌘V(이름은 미리 복사돼 있음) → 옛 키와 같은 권한으로(옛 키의 끝 네 글자를 보여 줌) 만들기 → 새 키 **복사**. 복사하는 순간 다음으로 넘어갑니다. `s`는 건너뛰기, `q`는 그만하기입니다.
   - 인증 코드, 옛 키, 다른 서비스의 키를 복사해도 새 키로 받지 않습니다.
   - DB 비밀번호는 맨 마지막입니다. 새 비밀번호를 저장하는 순간 옛 비밀번호가 끊기기 때문입니다.
4. 1Password에 저장합니다. 옛 값은 폐기할 때까지 보관합니다.
5. 모든 사용처를 바꿉니다. 그다음 서비스마다 지금 재배포할지 하나씩 묻습니다(기본값 N). 재시작하면 진행 중인 세션이 끊기는 서비스라면 N을 누르고, 나중에 평소 배포 방식이나 `rekey deploy <템플릿>`으로 배포하세요.
   - Supabase Edge Function, Fly, Worker는 바로 적용됩니다. GitHub Actions는 다음 실행부터 적용됩니다.
   - **GCP Secret Manager를 읽는 서비스는 직접 재시작**해야 새 키를 씁니다.
6. 모든 서비스를 재배포했다면 "옛 키를 지금 폐기할까요?"라고 묻습니다. 아니면 배포한 뒤에 폐기하세요.

```bash
rekey revoke shop.openai
```

- 옛 값이 아직 남아 있는 곳이 있으면 폐기를 거부합니다. 실행 중인 서비스가 읽어 둔 값이 아니라 변수를 확인하므로, 폐기는 배포한 뒤에 하세요.
- 폐기 API가 없는 서비스는 옛 키의 끝 네 글자를 보여 주고 페이지를 엽니다.
- 일부 사용처에 쓰지 못해도 나머지는 계속 진행하고, 마지막에 다시 시도할 명령을 알려 줍니다.

### 두 단계로 나눠서

바뀌기 전에 확인하고 싶으면 먼저 발급만 하고 나중에 반영하세요.

```bash
rekey issue project:shop     # 새 키를 1Password에만 저장. 어디도 바꾸지 않음
rekey apply project:shop     # 모든 곳에 반영. 재배포는 하나씩 묻습니다
```

### 잘못됐을 때

- **중간에 멈췄을 때:** 같은 명령을 다시 실행하세요. 끝난 키는 건너뜁니다. 교체한 키는 옛 키를 폐기하기 전까지 다시 교체하지 않습니다.
- **잘못된 값이 들어갔을 때**(인증 코드, 다른 키): `rekey rotate <키> --redo`로 새 키를 다시 만듭니다. 폐기할 옛 키는 처음 키 그대로입니다.
- **폐기 전에 되돌리고 싶을 때:** `rekey undo <키>`. 모든 곳을 옛 키로 되돌리고, 서비스를 재배포한 뒤 새 키를 삭제합니다.

## 여러 키를 한 번에

```bash
rekey rotate project:shop                  # 프로젝트 하나가 쓰는 키 전부 (저장소, Railway 서비스, Vercel 프로젝트…)
rekey rotate tag:breach-2026               # keys.toml 태그
rekey rotate 'in:railway/*'                # 이 템플릿들이 쓰는 키 전부
rekey rotate '*.cartesia'                  # 이름 패턴
rekey rotate tag:breach-2026 --only shop   # 좁히기: 프로젝트나 서비스, 이름, tag:, in:, project:
```

자동으로 되는 키를 먼저 처리하고, 브라우저 단계는 서비스별로 모아서 그다음에, DB 비밀번호는 맨 마지막에 진행합니다.

## 환경마다 볼트 하나, 프로젝트마다 키 하나

```bash
rekey arrange "Acme - {env}" --dry-run     # 계획 보기
rekey arrange "Acme - {env}"
```

- 키를 쓰는 환경의 볼트로 옮깁니다: `Acme - Prod`, `Acme - Dev`, `Acme - Local`.
- 여러 프로젝트나 환경이 같이 쓰던 키는 프로젝트·환경마다 하나씩 나누고 `<프로젝트>.<서비스>`로 이름을 붙입니다. 다음 `rotate` 전까지는 같은 값을 쓰고, 교체한 뒤에는 유출되면 어느 프로젝트인지 바로 압니다.
- 나누지 않는 키: 우리 서비스끼리 쓰는 토큰(`.self.`), DB 비밀번호, locked 키, 폐기를 기다리는 키.
- 1Password 항목은 옮기고 이름만 바꿉니다. 지우지 않습니다. `git diff`로 확인한 뒤 커밋하세요.
- rekey 0.3 이전의 팀 데이터는 키 이름이 `<서비스>.<프로젝트>`입니다. 한 번 `--old-names`를 붙여 실행하면 바뀝니다.

## 설정 바꾸기

플랫폼 템플릿에는 일반 설정도 들어 있습니다.

```bash
# targets/vercel/shop/production.tpl 에서 값을 고친 뒤
rekey diff targets/vercel/shop/production.tpl   # 지금 플랫폼 값과 비교
rekey sync targets/vercel/shop/production.tpl   # 반영. 재배포는 묻습니다
git commit -am "shop: APP_URL 변경"
```

`sync all`은 모든 플랫폼에 씁니다. 꼭 필요할 때만 쓰세요.

## 키 추가

1. 쓰일 템플릿에 줄을 추가합니다. 이름은 `<프로젝트>.<서비스>`, 앱끼리 쓰는 토큰은 `<프로젝트>.self.<용도>`입니다.
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/shop.stripe/credential }}
   ```
2. 값을 넣습니다. 이미 쓰고 있는 값이면 `rekey import shop.stripe`, 새로 발급하려면 `rekey rotate shop.stripe`.
3. `git commit`

어떤 곳에서 키를 그만 쓰려면 그 줄을 지우면 됩니다.

## 참고

**템플릿 경로 = 값이 들어갈 곳** (`targets/` 아래, `.tpl` 생략)

| 경로 | 대상 |
|---|---|
| `file/<경로>` | 로컬 파일 (팀 데이터 폴더의 상위 폴더 기준) |
| `vercel/<프로젝트>/<production·preview·development>` | Vercel |
| `railway/<프로젝트>/<환경>/<서비스>` | Railway |
| `supabase/<project ref>` | Supabase Edge Function secrets |
| `gcp/<프로젝트>` | GCP Secret Manager |
| `github/<owner>/<repo>[/<환경>]` | GitHub Actions secrets |
| `fly/<앱>`, `worker/<이름>` | Fly, Cloudflare Worker |

템플릿에 적힌 변수만 씁니다. 대상의 다른 변수는 건드리지 않습니다. 다른 서비스를 참조하는 Railway 변수(`${{ api.OPENAI_API_KEY }}`)는 덮어쓰지 않고 멈춰서 알려 줍니다.

**키 이름**: `<프로젝트>.<서비스>[.<용도>]`. 서비스가 발급 방법을 정합니다(`shop.openai` → OpenAI). `self`는 rekey가 직접 만드는 값, `other`는 사람이 브라우저에서 발급하는 키입니다.

**keys.toml**: 예외가 있는 키만 적습니다.

```toml
["shop.self.data-master-key"]
locked = "이유"                 # rotate가 건너뜀 (--force로만)
note = "교체 전에 볼 메모"       # rotate·where에 표시
tags = ["check", "retire"]      # check: rotate가 건너뜀 / retire: all에서 빠짐
page = "https://…"              # 브라우저 단계에서 열 페이지
```

**관리자 키**: `rekey.openai-admin`, `rekey.cloudflare-admin`, `rekey.resend-admin`, `rekey.anthropic-admin`(폐기용) 항목이 볼트 중 어디든(보통 Prod) 있으면 해당 서비스를 자동으로 처리합니다. `rekey setup`이 등록을 도와줍니다.

**환경변수**: `REKEY_HOME`(팀 데이터 폴더. 기본값은 현재 폴더에서 위로 올라가며 처음 만나는 `targets/`나 `keys.toml`이 있는 폴더), `REKEY_ROOT`(`file/` 기준 폴더, 기본값은 `REKEY_HOME`의 상위 폴더), `REKEY_STORE=file:<경로>`(1Password 대신 파일, 테스트용), `REKEY_NO_BROWSER=1`, `REKEY_LANG`(en, ko, zh, ja, es)
