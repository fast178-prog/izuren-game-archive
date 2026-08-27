# 이즈렌 영상 등록 관리

2026-08-28 00:00(KST) 이후 공개된 이즈렌TV 영상과 새 재생목록을 감지하고,
승인한 항목만 저장소의 `videos.json` 맨 위에 추가하는 Windows용 관리 프로그램입니다.

## 최초 설정에 필요한 값

- YouTube Data API v3 키
- GitHub fine-grained access token (`fast178-prog/izuren-game-archive`의 Contents 읽기/쓰기 권한)

토큰과 API 키는 Windows 사용자 계정의 DPAPI로 암호화하여 PC에 저장합니다.

## 개발 실행

```powershell
python app.py
```

## Windows EXE 빌드

```powershell
pip install -r requirements-build.txt
pyinstaller --noconfirm --onefile --windowed --name IzurenVideoManager app.py
```

`dist/IzurenVideoManager.exe`를 실행하면 됩니다.

완성된 EXE와 `install-autostart.ps1`을 같은 폴더에 둔 뒤 설치 스크립트를 한 번
실행하면 로그인 시 백그라운드 자동 확인과 바탕화면 바로가기가 설정됩니다.
