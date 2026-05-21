@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
set "DEFAULT_WORKFLOW=workflows\global\deepseek_echo.workflow.yaml"
set "WORKFLOW_FILE="
set "MODE=basic"

cd /d "%PROJECT_ROOT%" || goto end_failure

if /i "%~1"=="--help" goto usage
if /i "%~1"=="-h" goto usage
if /i "%~1"=="--auto" goto parse_auto
if /i "%~1"=="-a" goto parse_auto
if /i "%~1"=="--menu" goto choose_workflow
if /i "%~1"=="-m" goto choose_workflow
if "%~1"=="3" goto end_success
if "%~1"=="" goto choose_workflow
if not "%~1"=="" set "WORKFLOW_FILE=%~1"
if "%~2"=="1" goto validate_arg_and_run_basic
if "%~2"=="2" goto validate_arg_and_run_preview
if "%~2"=="3" goto end_success
if /i "%~2"=="--preview" goto validate_arg_and_run_preview
goto validate_arg_and_show_menu

:parse_auto
set "WORKFLOW_FILE=%DEFAULT_WORKFLOW%"
if /i "%~2"=="--preview" (
    set "MODE=preview"
    goto parsed_auto_args
)
if not "%~2"=="" set "WORKFLOW_FILE=%~2"
if /i "%~3"=="--preview" set "MODE=preview"
if "%~3"=="2" set "MODE=preview"
if "%~3"=="3" goto end_success
:parsed_auto_args
if /i "%MODE%"=="preview" goto validate_auto_and_run_preview
goto validate_auto_and_run_basic

:usage
echo Usage:
echo   workflows\global\run_deepseek_echo_test.bat
echo   workflows\global\run_deepseek_echo_test.bat [workflow_path] [1^|2]
echo   workflows\global\run_deepseek_echo_test.bat --auto [workflow_path] [1^|2^|--preview]
echo   workflows\global\run_deepseek_echo_test.bat --menu
echo.
echo Default mode opens the guided interactive menu and waits for user input.
echo Use --auto for one-shot validation with default answers.
goto end_success

:validate_workflow
if "%WORKFLOW_FILE%"=="" (
    echo Workflow path cannot be empty.
    exit /b 1
)

if not exist "%WORKFLOW_FILE%" (
    echo Workflow file not found: %WORKFLOW_FILE%
    exit /b 1
)
exit /b 0

:choose_workflow
echo.
echo Enter workflow path relative to project root.
echo Example: workflows\global\deepseek_echo.workflow.yaml
echo.
set /p "WORKFLOW_FILE=Workflow path: "

call :validate_workflow
if errorlevel 1 goto choose_workflow

:menu
echo.
echo XiAgent workflow test
echo =====================
echo Workflow: %WORKFLOW_FILE%
echo.
echo 1. Guided question test
echo 2. Guided question test with HTML preview
echo 3. Exit
echo.
choice /c 123 /n /m "Choose 1/2/3: "

if errorlevel 3 goto end_success
if errorlevel 2 goto run_preview
if errorlevel 1 goto run_basic

echo Please choose 1, 2, or 3.
goto menu

:validate_arg_and_run_basic
call :validate_workflow
if errorlevel 1 goto end_failure
goto run_basic

:validate_arg_and_run_preview
call :validate_workflow
if errorlevel 1 goto end_failure
goto run_preview

:validate_arg_and_show_menu
call :validate_workflow
if errorlevel 1 goto end_failure
goto menu

:validate_auto_and_run_basic
call :validate_workflow
if errorlevel 1 goto end_failure
goto run_basic_auto

:validate_auto_and_run_preview
call :validate_workflow
if errorlevel 1 goto end_failure
goto run_preview_auto

:run_basic_auto
(
    echo blue
    echo noodles
    echo running
) | python -m xiagent.workflows.testing_cli "%WORKFLOW_FILE%" --interactive --input "{}"
goto end_with_errorlevel

:run_preview_auto
(
    echo blue
    echo noodles
    echo running
) | python -m xiagent.workflows.testing_cli "%WORKFLOW_FILE%" --interactive --input "{}" --preview html
goto end_with_errorlevel

:run_basic
python -m xiagent.workflows.testing_cli "%WORKFLOW_FILE%" --interactive --input "{}"
goto after_run

:run_preview
python -m xiagent.workflows.testing_cli "%WORKFLOW_FILE%" --interactive --input "{}" --preview html
goto after_run

:after_run
echo.
pause
goto menu

:end_with_errorlevel
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%

:end_failure
endlocal & exit /b 1

:end_success
endlocal
exit /b 0
