@echo off
chcp 65001 >nul
setlocal
REM ================================================================
REM  삭제 (Windows) - 이 폴더 안에 설치·생성된 것만 지움. Python 자체는 건드리지 않음
REM   1단계  실행 중인 서버 종료 + 실행 환경(.venv)과 실행 기록 삭제 = 내려받은 직후 상태
REM   2단계  (선택) 폴더 전체 삭제 = 통계 프로그램·대시보드·가상데이터까지 모두 제거
REM ================================================================
cd /d "%~dp0"
set "CD_ROOT=%~dp0"
if not exist "%~dp0app\run.py" goto :NOT_HERE
if not exist "%~dp0START.bat" goto :NOT_HERE

echo 삭제 대상(이 폴더 안): .venv, workspace_nl, openstat\workspace, openstat\reports, __pycache__
set "OS_GO=N"
set /p "OS_GO=진행 [Y/N, 기본 N]: "
if /i not "%OS_GO%"=="Y" goto :CANCEL

REM 이 폴더의 실행 환경(.venv)으로 뜬 python 프로세스만 종료
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.ExecutablePath -like ($env:CD_ROOT + '.venv\*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
call :RMDIR ".venv"
call :RMDIR "workspace_nl"
call :RMDIR "openstat\workspace"
call :RMDIR "openstat\reports"
for /d /r "%~dp0" %%D in (__pycache__) do if exist "%%D" rd /s /q "%%D" >nul 2>&1
echo [완료] 설치 이전 상태로 되돌림. START.bat 을 다시 실행하면 재설치됨
echo.
set "OS_ALL=N"
set /p "OS_ALL=폴더 전체(%~dp0)도 삭제 [Y/N, 기본 N]: "
if /i not "%OS_ALL%"=="Y" goto :DONE
set "OS_ROOT=%~dp0"
cd /d "%TEMP%"
REM 실행 중인 이 파일까지 지우기 위해 별도 창에서 잠시 뒤 삭제
start "" /min cmd /c "timeout /t 2 /nobreak >nul & rd /s /q "%OS_ROOT%""
echo [완료] 폴더 전체 삭제 요청함: %OS_ROOT%
exit /b 0

:RMDIR
if exist "%~dp0%~1" rd /s /q "%~dp0%~1" & echo [삭제] %~1
goto :EOF

:CANCEL
echo 취소함
:DONE
pause
exit /b 0

:NOT_HERE
echo [오류] 프로그램 폴더가 아님: %~dp0
pause
exit /b 1
