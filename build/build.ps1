# Ricostruisce Editra PDF Studio: collaudi, eseguibile, installer e versione portatile.
# Uso (dalla cartella PDF):  powershell -ExecutionPolicy Bypass -File build\build.ps1  [-SkipTests]
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"

if (-not $SkipTests) {
    $work = Join-Path $env:TEMP "editra_collaudo"
    if (Test-Path $work) { Remove-Item $work -Recurse -Force }
    New-Item -ItemType Directory $work | Out-Null
    & $py tests\make_sample.py "$work\prova.pdf"
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:EDITRA_LANG = "it"
    & $py tests\test_ops.py "$work\ops" "$work\prova.pdf" | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) { throw "Collaudo delle operazioni fallito" }
    foreach ($lang in "it", "en") {
        $env:EDITRA_LANG = $lang
        & $py tests\test_gui.py "$work\gui_$lang" "$work\prova.pdf" | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0) { throw "Collaudo dell'interfaccia fallito ($lang)" }
        & $py tests\test_print.py "$work\print_$lang" "$work\prova.pdf" | Select-Object -Last 1
        if ($LASTEXITCODE -ne 0) { throw "Collaudo della stampa fallito ($lang)" }
    }
    Remove-Item Env:\QT_QPA_PLATFORM
    Remove-Item Env:\EDITRA_LANG
}

& $py build\make_icon.py build\EditraPDFStudio.ico
& (Join-Path $root ".venv\Scripts\pyinstaller.exe") build\EditraPDFStudio.spec --noconfirm --distpath dist --workpath build\tmp --log-level ERROR
if (-not (Test-Path dist\EditraPDFStudio\EditraPDFStudio.exe)) { throw "PyInstaller non ha creato l'eseguibile" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "C:\Program Files (x86)\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 non trovato (winget install JRSoftware.InnoSetup)" }
& $iscc /Q build\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Compilazione dell'installer fallita" }

$version = (Select-String -Path editra\__init__.py -Pattern 'VERSION = "(.+)"').Matches[0].Groups[1].Value
$zip = "installer\EditraPDFStudio_portable_$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\EditraPDFStudio -DestinationPath $zip -CompressionLevel Optimal
Get-ChildItem installer | Select-Object Name, @{n = 'MB'; e = { [math]::Round($_.Length / 1MB, 1) } }
