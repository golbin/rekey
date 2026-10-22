# 팀원이 나갔다

**1. 접근 권한을 회수합니다.** 키를 바꾸기 전에 먼저 합니다.
- 1Password vault, GitHub org, 각 플랫폼(Vercel·Railway·Supabase·GCP 등) 팀에서 제거

**2. 그 사람이 볼 수 있었던 키를 교체합니다.**

```bash
rekey rotate all                                  # vault 전체 권한이 있었다면
rekey rotate 'in:vercel/shop/*' 'in:file/shop/*'  # 특정 프로젝트만 다뤘다면
```

키가 많으면 자동 처리 분만 먼저 끝내고 브라우저 단계에서 `q`로 멈춰도 됩니다. 남은 키는 결과에 나오는 명령으로 이어서 진행합니다.

**3. 그 사람이 만든 키를 정리합니다.** 각 서비스의 키 목록에 그 사람이 만든 키가 남아 있으면 지웁니다. rekey가 만든 키는 이름이 `rekey-`로 시작합니다.
