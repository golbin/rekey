# 처음 준비

rekey는 **도구**(이 저장소)와 **팀 데이터**(`targets/`, `keys.toml`이 든 팀 비공개 저장소)를 나눠 씁니다. 팀 데이터에는 키 값이 없지만 인프라 구성이 드러나므로 비공개로 둡니다.

## 모두 (10분)

**1. 도구 설치와 팀 데이터 받기.** 팀 데이터는 프로젝트 폴더들과 **같은 폴더**에 둡니다. `targets/<project>/file/…` 경로가 이 위치를 기준으로 합니다.

```bash
brew install pipx                                  # 없으면 (Linux: https://pipx.pypa.io)
pipx install git+https://github.com/golbin/rekey
git clone <팀 데이터 저장소> ~/code/keys
```

`rekey`는 그 폴더(또는 그 아래 어디서든) 실행하면 팀 데이터를 알아서 찾습니다. 도구 업데이트는 `pipx upgrade rekey`입니다.

**2. 1Password CLI.**

```bash
brew install 1password-cli        # Linux: https://developer.1password.com/docs/cli/get-started
```

1Password 앱 → 설정 → 개발자 → **"1Password CLI와 통합"** 을 켭니다. 팀 vault 권한이 없으면 관리자에게 요청하세요.

**3. 확인.**

```bash
cd ~/code/keys
rekey ls                       # 키 목록이 나오면 rekey OK
op vault get "Acme - Prod"     # vault 정보가 나오면 1Password OK
```

여기까지 하면 [로컬 .env 만들기](usage.md#로컬-env-만들기)를 할 수 있습니다.

## 키를 교체하는 사람이라면 (추가 5분)

```bash
rekey setup
```

빠진 것을 하나씩 알려 주고 그 자리에서 해결합니다.
- 사용하는 플랫폼 CLI(`vercel`, `railway`, `supabase`, `gcloud`, `gh` 등) 로그인: rekey가 로그인 명령을 실행하면 브라우저에서 승인만 합니다.
- 관리자 키 (선택): OpenAI·Cloudflare·Resend 키를 브라우저 없이 자동으로 발급합니다. 별도 볼트 `<팀> - Admin`에 보관합니다.

"준비 완료"로 끝나면 됩니다. 이후에도 `rotate`가 시작할 때마다 같은 점검을 합니다.

## 처음 도입하는 팀이라면

[예시](https://github.com/golbin/rekey-example)에서 시작하거나(**Use this template** → 비공개 저장소), 빈 팀 데이터 저장소에서 한 번 실행하세요.

```bash
mkdir ~/code/keys && cd ~/code/keys && git init
rekey init --vault "Acme - Prod" --source vercel --source supabase --source railway --source gcp:<project>
rekey arrange "Acme - {env}"   # 환경마다 볼트 하나, 프로젝트마다 키 하나
rekey import all               # 지금 쓰는 값을 1Password에 저장
git add . && git commit -m "rekey: initial templates"
```

- `init`은 `~/code` 아래의 .env 파일과 플랫폼을 읽어 템플릿을 만듭니다. 같은 값은 키 하나로 묶고, 가장 많이 쓰는 프로젝트를 따서 `<프로젝트>.<서비스>`로 이름을 붙입니다. 프로젝트는 git 저장소, Railway 서비스, Vercel 프로젝트입니다.
- `arrange`는 키를 환경별 볼트(`Acme - Prod`, `Acme - Dev`, `Acme - Local`)로 옮기고, 여러 프로젝트나 환경이 같이 쓰던 키를 나눕니다. 그래서 키가 유출되면 어디인지 바로 압니다. 팀원에게는 Dev와 Local을 주고, Prod는 필요한 사람에게만 주세요.
- `init`은 기존 템플릿과 키 이름을 바꾸지 않습니다. `--source`를 늘려 다시 실행해도 안전합니다.
- 결과는 `git diff`로 확인하세요. `# …: guessed` 주석 아래 줄은 Vercel에서 값을 읽을 수 없어 이름으로 짝지은 변수입니다.
