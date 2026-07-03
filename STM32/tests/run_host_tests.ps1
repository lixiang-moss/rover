$ErrorActionPreference = "Stop"

$testDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$stm32Directory = Split-Path -Parent $testDirectory
$buildDirectory = Join-Path $testDirectory "build"
New-Item -ItemType Directory -Force -Path $buildDirectory | Out-Null

$compiler = (Get-Command gcc -ErrorAction Stop).Source
$output = Join-Path $buildDirectory "test_protocol.exe"
$includeDirectory = Join-Path $stm32Directory "Core/Inc"

& $compiler `
  -std=c11 -Wall -Wextra -Wpedantic `
  "-I$includeDirectory" `
  (Join-Path $stm32Directory "Core/Src/cJSON.c") `
  (Join-Path $stm32Directory "Core/Src/mwrs_protocol.c") `
  (Join-Path $stm32Directory "Core/Src/mwrs_units.c") `
  (Join-Path $testDirectory "test_protocol.c") `
  -lm -o $output

if ($LASTEXITCODE -ne 0) {
  throw "Host test compilation failed with exit code $LASTEXITCODE"
}

& $output
if ($LASTEXITCODE -ne 0) {
  throw "Host tests failed with exit code $LASTEXITCODE"
}
