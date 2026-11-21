@echo off
chcp 65001 >nul
setlocal
REM ================================================================
REM  실행기 (Windows)
REM  - 최초 실행 시 가상환경 생성과 패키지 설치 자동 수행
REM  - 로컬 서버 127.0.0.1:8500 구동 후 기본 브라우저로 화면 열기
REM  - 이 창을 닫으면 서버 종료
REM ================================================================
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "OS_MARK=%~dp0.venv\requirements.installed.txt"

if exist "%VENV_PY%" goto :CHECK_DEPS
set "OS_PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "OS_PY=py -3"
if defined OS_PY goto :MAKE_VENV
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "OS_PY=python"
if not defined OS_PY goto :NO_PYTHON

:MAKE_VENV
echo [최초 1회] 가상환경 생성 및 패키지 설치 - 인터넷 속도에 따라 3~10분 소요
%OS_PY% -m venv "%~dp0.venv"
if not exist "%VENV_PY%" goto :VENV_FAILED

:CHECK_DEPS
fc /b "%~dp0requirements.txt" "%OS_MARK%" >nul 2>&1
if not errorlevel 1 goto :RUN
echo [설치] 필수 패키지 설치·갱신 중 - 수 분 소요
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 goto :PIP_FAILED
copy /y "%~dp0requirements.txt" "%OS_MARK%" >nul

:RUN
echo ================================================================
echo   통계 프로그램 + 자연어 명령 창 : http://127.0.0.1:8500/
echo   정책 대시보드                 : http://127.0.0.1:8500/dashboard
echo   이 창을 닫거나 Ctrl+C 를 누르면 서버 종료
echo ================================================================
"%VENV_PY%" -m app.run --open %*
pause
exit /b 0

:NO_PYTHON
echo [오류] Python 3.10 이상 미설치 또는 PATH 미등록
echo   설치 주소: https://www.python.org/downloads/windows/  (설치 시 "Add python.exe to PATH" 선택)
pause
exit /b 1

:VENV_FAILED
echo [오류] 가상환경 생성 실패
pause
exit /b 1

:PIP_FAILED
echo [오류] 패키지 설치 실패 - 인터넷 연결 확인 후 다시 실행
pause
exit /b 1
