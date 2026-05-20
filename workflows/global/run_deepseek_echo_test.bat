@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
set "WORKFLOW_FILE="

cd /d "%PROJECT_ROOT%"

if "%~1"=="3" goto end
if not "%~1"=="" set "WORKFLOW_FILE=%~1"
if "%~2"=="1" goto validate_arg_and_run_basic
if "%~2"=="2" goto validate_arg_and_run_preview
if "%~2"=="3" goto end

:choose_workflow
echo.
echo Enter workflow path relative to project root.
echo Example: workflows\global\deepseek_echo.workflow.yaml
echo.
set /p WORKFLOW_FILE=Workflow path: 

if "%WORKFLOW_FILE%"=="" (
    echo Workflow path cannot be empty.
    goto choose_workflow
)

if not exist "%WORKFLOW_FILE%" (
    echo Workflow file not found: %WORKFLOW_FILE%
    goto choose_workflow
)

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

if errorlevel 3 goto end
if errorlevel 2 goto run_preview
if errorlevel 1 goto run_basic

echo Please choose 1, 2, or 3.
goto menu

:validate_arg_and_run_basic
if not exist "%WORKFLOW_FILE%" (
    echo Workflow file not found: %WORKFLOW_FILE%
    goto end
)
goto run_basic

:validate_arg_and_run_preview
if not exist "%WORKFLOW_FILE%" (
    echo Workflow file not found: %WORKFLOW_FILE%
    goto end
)
goto run_preview

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

:end
endlocal
exit /b 0
