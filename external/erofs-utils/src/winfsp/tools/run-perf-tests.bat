@echo off

setlocal
setlocal EnableDelayedExpansion

set Configuration=Release
if not X%1==X set Configuration=%1

pushd %~dp0..
set ProjRoot=%cd%
if not exist "%ProjRoot%\build\VStudio\build\%Configuration%" echo === No tests found >&2 & goto fail
popd

verifier /query | findstr winfsp >nul 2>nul
if !ERRORLEVEL! equ 0 echo warning: verifier for winfsp is ON >&2

set launchctl="%ProjRoot%\build\VStudio\build\%Configuration%\launchctl-x64.exe"
set fsbench="%ProjRoot%\build\VStudio\build\%Configuration%\fsbench-x64.exe"

if X%2==Xbaseline (
    %launchctl% start memfs64 testdsk "" M: >nul
    rem Cannot use timeout under cygwin/mintty: "Input redirection is not supported"
    waitfor 7BF47D72F6664550B03248ECFE77C7DD /t 3 2>nul
    cd M: >nul 2>nul || (echo === Unable to find drive M: >&2 & goto fail)
)

mkdir fsbench
pushd fsbench

set OptFiles=1000 2000 3000 4000 5000
if X%2==Xbaseline set OptFiles=10000
for %%a in (%OptFiles%) do (
    call :csv "" %%a "%fsbench% --empty-cache=C --files=%%a --open=1 file_*"
)

%fsbench% --empty-cache=C --files=1000 file_create_test >nul
set OptOpen=10 20 30 40 50
if X%2==Xbaseline set OptOpen=100
for %%a in (%OptOpen%) do (
    call :csv "iter." %%a "%fsbench% --empty-cache=C --files=1000 --open=%%a file_open_test file_attr_test file_list_single_test file_list_none_test"
)
%fsbench% --empty-cache=C --files=1000 file_delete_test >nul

set OptRdwrCc=100 200 300 400 500
if X%2==Xbaseline set OptRdwrCc=1000
for %%a in (%OptRdwrCc%) do (
    call :csv "" %%a "%fsbench% --empty-cache=C --rdwr-cc=%%a rdwr_cc_*"
)

set OptRdwrNc=100 200 300 400 500
if X%2==Xbaseline set OptRdwrNc=100
for %%a in (%OptRdwrNc%) do (
    call :csv "" %%a "%fsbench% --empty-cache=C --rdwr-nc=%%a rdwr_nc_*"
)

set OptMmap=100 200 300 400 500
if X%2==Xbaseline set OptMmap=1000
for %%a in (%OptMmap%) do (
    call :csv "" %%a "%fsbench% --empty-cache=C --mmap=%%a mmap_*"
)

popd
rmdir fsbench

if X%2==Xbaseline (
    %launchctl% stop memfs64 testdsk >nul
    rem Cannot use timeout under cygwin/mintty: "Input redirection is not supported"
    waitfor 7BF47D72F6664550B03248ECFE77C7DD /t 3 2>nul
)

exit /b 0

:fail
exit /b 1

:csv
set Prfx=%~1
set Iter=%2
for /F "tokens=1,2,3" %%i in ('%3') do (
    if %%j==OK (
        set Name=%%i
        set Name=!Name:.=!
        set Time=%%k
        set Time=!Time:s=!

        echo !Prfx!!Name!,!Iter!,!Time!
    )
)
exit /b 0
