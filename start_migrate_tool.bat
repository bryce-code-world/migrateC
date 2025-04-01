@echo off
:: 强制使用UTF-8编码
chcp 65001 > nul
title C盘大文件迁移工具启动器

:: 检查管理员权限并自动提权
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo 请求管理员权限...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    pushd "%CD%"
    CD /D "%~dp0"

:: 确保窗口不会关闭
echo C盘大文件迁移工具启动器
echo ====================================
     
:: 检查Python环境和依赖包
echo 检查Python环境和依赖包...

:: 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% NEQ 0 (
    echo [错误] 未检测到Python环境，请先安装Python 3.6或更高版本。
    echo 您可以从 https://www.python.org/downloads/ 下载并安装Python。
    goto :error
)

:: 检查pip是否可用
python -m pip --version >nul 2>&1
if %errorlevel% NEQ 0 (
    echo [错误] 未检测到pip工具，请确保Python安装正确。
    goto :error
)

:: 检查并安装依赖包
echo 检查必要的依赖包...
set requirements_file=%~dp0requirements.txt

if not exist "%requirements_file%" (
    echo [错误] 未找到依赖文件：%requirements_file%
    goto :error
)

:: 检查是否已安装所有依赖
set missing_deps=0

:: 检查PyQt5
python -c "import PyQt5" >nul 2>&1
if %errorlevel% NEQ 0 set missing_deps=1

:: 检查yaml
python -c "import yaml" >nul 2>&1
if %errorlevel% NEQ 0 set missing_deps=1

:: 检查psutil
python -c "import psutil" >nul 2>&1
if %errorlevel% NEQ 0 set missing_deps=1

:: 检查tqdm
python -c "import tqdm" >nul 2>&1
if %errorlevel% NEQ 0 set missing_deps=1

:: 如果缺少依赖，则安装
if %missing_deps% EQU 1 (
    echo 正在安装必要的依赖包...
    python -m pip install -r "%requirements_file%"
    if %errorlevel% NEQ 0 (
        echo [错误] 安装依赖包失败，请检查网络连接或手动安装。
        goto :error
    )
    echo 依赖包安装完成。
) else (
    echo 所有依赖包已安装。
)

echo 正在启动程序...
echo.

:: 直接运行Python程序并捕获输出
python main.py
goto :end

:error
echo.
echo [错误] 程序启动失败。
echo 请参考README.md文件中的手动安装说明。

:end

:: 无论程序是否成功，都保持窗口打开
echo.
echo 程序已退出，错误代码: %errorlevel%
echo.
echo 按任意键退出...
pause > nul

:: 如果用户按了键，再次确认
echo 再次按任意键确认退出...
pause > nul

:: 最后的保险措施
cmd /k