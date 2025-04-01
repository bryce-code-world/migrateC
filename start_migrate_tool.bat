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
echo 正在启动程序...
echo.

:: 直接运行Python程序并捕获输出
python main.py

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