# 쓰는 플랫폼이 해킹당했다

Vercel·Railway·Supabase 같은 플랫폼에서 "등록된 환경변수가 노출됐을 수 있다"는 공지를 받은 경우입니다.

**1. 그 플랫폼에 있는 키를 고릅니다.**

```bash
rekey ls 'in:railway/*'        # vercel/*, supabase/*, gcp/* … 플랫폼에 맞게
```

목록이 비어 있거나 빠진 게 있어 보이면, 플랫폼에서 다시 읽어 템플릿을 보충하세요. 기존 템플릿과 이름은 바뀌지 않습니다.

```bash
rekey init --vault "Acme - Prod" --source railway
```

그 플랫폼에 배포하려고 로컬 .env를 통째로 올린 적이 있다면 그 .env의 키도 대상입니다. 선택을 이어 쓰면 됩니다.

```bash
rekey ls 'in:railway/*' 'in:file/shop/api/*'
```

**2. 교체합니다.** 1에서 확인한 선택을 그대로 씁니다.

```bash
rekey rotate 'in:railway/*' 'in:file/shop/api/*'
```

자동 처리가 끝나면 브라우저 단계가 이어집니다. 배포가 정상으로 확인되면 바로 폐기하세요.

**3. 플랫폼 쪽 정리**
- 그 플랫폼의 계정 토큰·프로젝트 토큰(CI에서 쓰는 것)도 교체합니다. 보통 `github/…` 템플릿에 있습니다.
- 그 플랫폼에 연결된 GitHub 앱 권한을 확인합니다(GitHub → Settings → Applications).
- 안 쓰는 프로젝트는 지웁니다.
