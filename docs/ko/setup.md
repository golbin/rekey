# 처음 준비

rekey는 **도구**(이 저장소)와 **팀 데이터**(`targets/`, `keys.toml`이 든 팀 비공개 저장소)를 나눠 씁니다. 팀 데이터에는 키 값이 없지만 인프라 구성이 드러나므로 비공개로 둡니다.

## 모두 (10분)

**1. 도구와 팀 데이터 받기.** 팀 데이터는 프로젝트 폴더들과 **같은 폴더**에 둡니다. `targets/file/…` 경로가 이 위치를 기준으로 합니다.

```bash
git clone https://github.com/golbin/rekey.git ~/tools/rekey
git clone <팀 데이터 저장소> ~/code/keys
```

`~/.zshrc`(또는 `~/.bashrc`)에 추가하고 새 터미널을 엽니다.

```bash
export REKEY_HOME=~/code/keys
alias rekey=~/tools/rekey/rekey
```

**2. 1Password CLI.**

```bash
brew install 1password-cli        # Linux: https://developer.1password.com/docs/cli/get-started
```

1Password 앱 → 설정 → 개발자 → **"1Password CLI와 통합"** 을 켭니다. 팀 vault 권한이 없으면 관리자에게 요청하세요.

**3. 확인.**

```bash
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
- 관리자 키 (선택): OpenAI·Cloudflare·Resend 키를 브라우저 없이 자동으로 발급합니다.

"준비 완료"로 끝나면 됩니다. 이후에도 `rotate`가 시작할 때마다 같은 점검을 합니다.

## 처음 도입하는 팀이라면

빈 팀 데이터 저장소에서 한 번 실행합니다.

```bash
mkdir ~/code/keys && cd ~/code/keys && git init
rekey init --vault "Acme - Prod" --source vercel --source supabase --source railway --source gcp:<프로젝트>
rekey import all        # 지금 쓰는 값을 1Password에 저장
git add . && git commit -m "rekey: initial templates"
```

- `init`은 `~/code` 아래 .env 파일들과 플랫폼을 읽어 템플릿을 만듭니다. 같은 값은 키 하나로 묶습니다.
- 여러 프로젝트를 담은 폴더(예: `~/code/clients/a`, `~/code/clients/b`)가 있으면 `--group-dirs clients`를 붙이세요. 키 이름이 그 아래 폴더 이름으로 지어집니다.
- 이미 있는 템플릿과 키 이름은 바꾸지 않으므로, `--source`를 나중에 추가해 다시 실행해도 안전합니다.
- 만든 뒤에는 `git diff`로 훑어보세요. `# …: guessed` 주석이 붙은 줄은 Vercel에서 값을 읽을 수 없어서 이름으로 짝지은 곳입니다.
