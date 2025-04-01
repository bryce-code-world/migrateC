@echo off
chcp 65001 > nul
title C盘大文件迁移工具启动器

echo C盘大文件迁移工具启动器
echo ====================================
echo 正在检查环境并启动程序...
echo.

:: 检查是否以管理员身份运行
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo 需要管理员权限，正在请求...
    goto UACPrompt
) else (
    goto GotAdmin
)

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B

:GotAdmin
    if exist "%temp%\getadmin.vbs" del /f /q "%temp%\getadmin.vbs"
    pushd "%CD%"
    cd /d "%~dp0"

:: 检查Python环境
echo 检查Python环境...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未检测到Python环境！
    echo 请先安装Python 3.6+，然后再运行此程序。
    echo 您可以从 https://www.python.org/downloads/ 下载Python。
    pause
    exit /B
)

:: 检查Python版本
echo 检查Python版本...
for /f "tokens=2" %%i in ('python -c "import sys; print(sys.version_info[0])"') do set PYTHON_MAJOR=%%i
for /f "tokens=2" %%i in ('python -c "import sys; print(sys.version_info[1])"') do set PYTHON_MINOR=%%i

if %PYTHON_MAJOR% LSS 3 (
    echo 错误: Python版本过低，需要Python 3.6+
    pause
    exit /B
)

if %PYTHON_MAJOR% EQU 3 (
    if %PYTHON_MINOR% LSS 6 (
        echo 错误: Python版本过低，需要Python 3.6+
        pause
        exit /B
    )
)

:: 检查并创建必要的目录
echo 检查并创建必要的目录...
if not exist "logs" mkdir logs
if not exist "output" mkdir output
if not exist "temp" mkdir temp

:: 检查配置文件
echo 检查配置文件...
if not exist "config.yaml" (
    echo 警告: 配置文件不存在，将在程序启动后自动创建默认配置文件。
)

:: 检查必要的依赖包
echo 检查必要的依赖包...

:: 检查PyQt5
python -c "import PyQt5" >nul 2>nul
if %errorlevel% neq 0 (
    echo 正在安装PyQt5...
    pip install PyQt5>=5.15.0
    if %errorlevel% neq 0 (
        echo 安装PyQt5失败，请手动运行: pip install PyQt5>=5.15.0
        pause
        exit /B
    )
)

:: 检查pyyaml
python -c "import yaml" >nul 2>nul
if %errorlevel% neq 0 (
    echo 正在安装pyyaml...
    pip install pyyaml>=6.0
    if %errorlevel% neq 0 (
        echo 安装pyyaml失败，请手动运行: pip install pyyaml>=6.0
        pause
        exit /B
    )
)

:: 检查psutil
python -c "import psutil" >nul 2>nul
if %errorlevel% neq 0 (
    echo 正在安装psutil...
    pip install psutil>=5.9.0
    if %errorlevel% neq 0 (
        echo 安装psutil失败，请手动运行: pip install psutil>=5.9.0
        pause
        exit /B
    )
)

:: 检查tqdm
python -c "import tqdm" >nul 2>nul
if %errorlevel% neq 0 (
    echo 正在安装tqdm...
    pip install tqdm>=4.64.0
    if %errorlevel% neq 0 (
        echo 安装tqdm失败，请手动运行: pip install tqdm>=4.64.0
        pause
        exit /B
    )
)

:: 或者一次性安装所有依赖（如果requirements.txt存在）
if exist "requirements.txt" (
    echo 检查是否需要安装依赖包...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo 警告: 安装依赖包可能不完整，程序可能无法正常运行。
    )
)

:: 启动主程序
echo 所有检查完成，正在启动C盘大文件迁移工具...
echo.
echo 如果程序无法正常启动，请检查日志文件(logs目录)获取详细信息。
echo.

:: 设置环境变量，表示从启动器启动
set MIGRATE_C_LAUNCHER=1

:: 启动主程序
python main.py

:: 程序结束
echo.
echo 程序已退出。
pause
exit /B