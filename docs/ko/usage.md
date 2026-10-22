# 사용법

명령은 팀 데이터 폴더 안에서 실행합니다. 바꾸는 명령(`rotate`, `revoke`, `sync`, `import`)은 `--dry-run`을 붙이면 미리 보기만 합니다.

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
- 그다음 `rekey import`로 새 값을 1Password에 저장합니다.

## 키 찾기

```bash
rekey ls                     # 전체: 서비스, 발급 방식, 사용처 수, 태그
rekey ls 'openai.*'          # 일부만
rekey where openai.shop      # 이 키가 들어간 템플릿과 변수
```

## 키 교체

```bash
rekey rotate openai.shop
```

1. 준비 점검을 합니다. 빠진 로그인 등은 그 자리에서 해결합니다.
2. 할 일을 요약해 보여 주고 시작할지 묻습니다.
3. 새 키를 받습니다.
   - **자동:** API로 발급하거나 로컬에서 생성합니다. 권한이 없는 등으로 안 되면 이유를 보여 주고 브라우저로 넘어갑니다.
   - **브라우저:** 페이지가 열리면 이름 칸에 ⌘V(이름은 미리 복사돼 있음) → 만들기 → 새 키 **복사**. 복사하는 순간 다음으로 넘어갑니다. `s`는 건너뛰기, `q`는 그만하기입니다.
   - 옛 키나 다른 서비스의 키를 복사하면 알려 줍니다. 새 키가 동작하지 않으면 다시 복사할 수 있습니다.
   - 중간에 멈췄다면 같은 명령을 다시 실행하세요. 끝난 키는 건너뜁니다. 새 키가 잘못 들어갔다면 `rekey rotate <키> --redo`.
   - 폐기 전에 되돌리고 싶다면 `rekey undo <키>`. 모든 곳을 옛 키로 되돌리고 새 키를 삭제합니다.
4. 1Password에 저장합니다. 옛 값은 폐기할 때까지 보관합니다.
5. 모든 사용처를 바꿉니다. 그다음 Vercel production과 Railway 서비스마다 지금 재배포할지 하나씩 묻고(기본값 N), y라고 한 것만 배포해 정상인지 확인합니다.
   - 재시작하면 진행 중인 세션이 끊기는 서비스라면 N을 누르고, 나중에 평소 배포 방식이나 `rekey deploy <템플릿>`으로 배포하세요.
   - Supabase Edge Function, Fly, Worker는 바로 적용됩니다. GitHub Actions는 다음 실행부터 적용됩니다.
   - **GCP Secret Manager를 읽는 서비스는 직접 재시작**해야 새 키를 씁니다.
6. "옛 키를 지금 폐기할까요?"라고 묻습니다. 더 지켜보려면 N을 누르고 나중에 폐기합니다.

```bash
rekey revoke openai.shop
```

- 옛 값을 아직 쓰는 곳이 있으면 폐기를 멈추고, 실행할 명령을 알려 줍니다.
- API로 지울 수 없는 서비스는 지울 키를 끝 4자리로 알려 주고 페이지를 엽니다.
- 중간에 끊겨도 같은 명령을 다시 실행하면 남은 것만 진행합니다. 이미 교체한 키는 옛 키를 폐기하기 전까지 다시 교체하지 않습니다.
- 일부 사용처에 쓰지 못하면 나머지는 계속 진행하고, 마지막에 다시 반영할 명령을 알려 줍니다.

## 여러 키를 한 번에

```bash
rekey rotate 'cartesia.*'              # 이름 패턴
rekey rotate tag:breach-2026           # keys.toml 태그
rekey rotate 'in:vercel/shop/*'        # 이 템플릿들이 쓰는 키 전부
rekey rotate project:shop          # 프로젝트 하나가 쓰는 키 전부 (저장소, Railway 서비스, Vercel 프로젝트…)
rekey rotate tag:breach-2026 --only openai   # 좁히기: 서비스, 프로젝트(in:…), 태그
```

자동으로 되는 키를 먼저 처리하고, 브라우저 단계는 마지막에 서비스별로 모아서 진행합니다.

### 프로젝트마다 키 하나

여러 프로젝트가 키 하나를 같이 쓰면, 유출됐을 때 어디서 샜는지 알 수 없고 모든 프로젝트를 바꿔야 합니다. 나누세요.

```bash
rekey split 'cartesia.*'      # cartesia.shop → cartesia.shop, cartesia.blog, …
rekey rotate 'cartesia.*'     # 프로젝트마다 자기 키를 받습니다
```

값이 하나여야 하는 키는 그대로 둡니다: 우리 서비스끼리 쓰는 토큰, DB 비밀번호, locked 키.

## 설정 바꾸기

플랫폼 템플릿에는 일반 설정도 들어 있습니다.

```bash
# targets/vercel/shop/production.tpl 에서 값을 고친 뒤
rekey diff targets/vercel/shop/production.tpl            # 실제 값과 비교
rekey sync targets/vercel/shop/production.tpl --deploy   # 반영하고 재배포
git commit -am "shop: APP_URL 변경"
```

`sync all`은 모든 플랫폼에 씁니다. 꼭 필요할 때만 쓰세요.

## 새 키 추가

1. 쓰일 템플릿에 줄을 추가합니다. 이름은 `<서비스>.<프로젝트>`, 앱끼리 쓰는 토큰은 `self.<프로젝트>.<용도>`로 짓습니다.
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/stripe.shop/credential }}
   ```
2. 값을 넣습니다. 이미 쓰고 있는 값이면 `rekey import stripe.shop`, 새로 발급하려면 `rekey rotate stripe.shop`
3. `git commit`

사용처를 빼려면 템플릿에서 줄을 지우면 됩니다.

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

템플릿에 적힌 변수만 씁니다. 대상의 다른 변수는 건드리지 않습니다.

**keys.toml**: 예외가 있는 키만 적습니다.

```toml
["self.shop.data-master-key"]
locked = "이유"                 # rotate가 건너뜀 (--force로만)
note = "교체 전에 볼 메모"       # rotate·where에 표시
tags = ["check", "retire"]      # check: rotate가 건너뜀 / retire: all에서 빠짐
page = "https://…"              # 브라우저 단계에서 열 페이지
```

**관리자 키**: 1Password의 키와 같은 vault에 `rekey.openai-admin`, `rekey.cloudflare-admin`, `rekey.resend-admin`, `rekey.anthropic-admin`(폐기용) 항목이 있으면 해당 서비스를 자동으로 처리합니다. `rekey setup`이 등록을 도와줍니다.

**환경변수**: `REKEY_HOME`(팀 데이터 폴더. 기본값은 현재 폴더에서 위로 올라가며 처음 만나는 `targets/`나 `keys.toml`이 있는 폴더), `REKEY_ROOT`(`file/` 기준 폴더, 기본값은 `REKEY_HOME`의 상위 폴더), `REKEY_STORE=file:<경로>`(1Password 대신 파일, 테스트용), `REKEY_NO_BROWSER=1`, `REKEY_LANG`(en, ko, zh, ja, es)
