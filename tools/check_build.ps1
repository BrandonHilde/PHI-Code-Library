# Checks build.ps1 itself, on a throwaway chain of two libraries in a temporary folder: that it works
# from a clean checkout, and that it fails when it should. Run this after changing build.ps1, or when
# PHI changes how libraries work. It leaves nothing behind.
$ErrorActionPreference = 'Stop'

$repo = Split-Path $PSScriptRoot -Parent
if (-not $env:PHI_EXE) {
	$env:PHI_EXE = (Resolve-Path (Join-Path $repo '..\PHI\Compiler\Phi.Cli\bin\Debug\net8.0\phi.exe')).Path
}

$work = Join-Path ([IO.Path]::GetTempPath()) ('phi-buildcheck-' + [guid]::NewGuid().ToString('N'))
$checks = New-Object System.Collections.Generic.List[object]

# A fresh copy of the chain and build.ps1, as a clean checkout would have them.
function New-Checkout {
	if (Test-Path $work) { Remove-Item $work -Recurse -Force }
	New-Item -ItemType Directory -Path $work | Out-Null
	Copy-Item (Join-Path $repo 'build.ps1') $work
	Copy-Item (Join-Path $PSScriptRoot 'buildcheck\*') $work -Recurse
}

function Invoke-Check {
	param([string]$Title, [bool]$ShouldPass, [string[]]$BuildArguments)

	Write-Host "`n#### $Title"
	$ErrorActionPreference = 'Continue'
	& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $work 'build.ps1') @BuildArguments 2>&1 |
		ForEach-Object { Write-Host "$_" }
	$passed = $LASTEXITCODE -eq 0
	$checks.Add([pscustomobject]@{
			Check  = $Title
			Wanted = if ($ShouldPass) { 'pass' } else { 'fail' }
			Got    = if ($passed) { 'pass' } else { 'fail' }
			OK     = $passed -eq $ShouldPass
		})
}

function Add-Text {
	param([string]$Path, [string]$Text)

	$full = Join-Path $work $Path
	[IO.File]::WriteAllText($full, [IO.File]::ReadAllText($full) + $Text)
}

try {
	New-Checkout
	Invoke-Check 'Everything, with tests, from a clean checkout' $true @('-Test')

	New-Checkout
	Invoke-Check 'One library by folder name brings its dependency' $true @('mid')

	New-Checkout
	Add-Text 'libs\mid\tests\use\test_cbmid.expected' "wrong`n"
	Invoke-Check 'A wrong answer in a compiled test fails' $false @('-Test')

	New-Checkout
	Add-Text 'libs\mid\test_cbmid_source.expected' "wrong`n"
	Invoke-Check 'A wrong answer in an internal test fails' $false @('-Test')

	New-Checkout
	Add-Text 'libs\mid\cbmid.phi' "`nthis isn't PHI`n"
	Invoke-Check 'A library that does not compile fails' $false @()

	New-Checkout
	Add-Text 'libs\base\cbbase.phi' "`nphi.CbWarns:Library`n{`n`t[Warns]`n`t`tint a: 1;`n`t`tint b: 2;`n`t`tint c: 3;`n`t`ta is b is c;`n`t[end: a]`n}`n"
	Invoke-Check 'A warning fails' $false @()

	New-Checkout
	Set-Content (Join-Path $work 'libraries.psd1') -Encoding Ascii -Value "@{ Libraries = @( @{ Name = 'cbmid'; Folder = 'libs\mid'; Uses = @('cbbase') }; @{ Name = 'cbbase'; Folder = 'libs\base'; Uses = @() } ) }"
	Invoke-Check 'A library listed before what it uses fails' $false @()
}
finally {
	if (Test-Path $work) { Remove-Item $work -Recurse -Force }
}

Write-Host ''
$checks | Format-Table -AutoSize | Out-String | Write-Host
$wrong = @($checks | Where-Object { -not $_.OK })
if ($wrong.Count -gt 0) {
	Write-Host "$($wrong.Count) of $($checks.Count) checks went the wrong way." -ForegroundColor Red
	exit 1
}
Write-Host "All $($checks.Count) checks went the right way."
exit 0
