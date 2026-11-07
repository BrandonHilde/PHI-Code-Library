# Builds the libraries in dependency order into dist/, and runs their tests.
#
#   .\build.ps1             every library
#   .\build.ps1 image       one library, and what it depends on
#   .\build.ps1 -Test       and run the tests
#
# This only makes .philib files. Which systems they hold, and which systems a program built with
# them runs on, is up to PHI's compiler and the project using the library.
#
# It works this way because of how PHI finds libraries (plan.md has the details):
#  - `use` has no include path, so a library's dependencies are copied next to its main file
#  - a program needs everything it reaches, so tests get the whole set copied beside them
#  - a .philib only loads with the phi that built it, so everything is always rebuilt
#
# The compiler is $env:PHI_EXE, or else the build in a PHI repo next to this one.
[CmdletBinding()]
param(
	[Parameter(Position = 0)]
	[string[]]$Name = @(),

	[switch]$Test,

	[int]$Timeout = 60
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$dist = Join-Path $root 'dist'

$phi = $env:PHI_EXE
if (-not $phi) {
	$phi = Join-Path $root '..\PHI\Compiler\Phi.Cli\bin\Debug\net8.0\phi.exe'
}
if (-not (Test-Path $phi)) {
	throw "phi not found at $phi. Build the PHI repo (dotnet build PHI.sln), or set PHI_EXE."
}
$phi = (Resolve-Path $phi).Path

# NASM's default optimizer takes minutes on code this size; -O1 takes seconds and is about 3% bigger
if (-not $env:NASMENV) {
	$env:NASMENV = '-O1'
}

# Runs phi, showing its output as it comes, and gives back its lines and exit code.
function Invoke-Phi {
	param([string[]]$Arguments)

	# (in Windows PowerShell, stderr through 2>&1 would otherwise stop the script)
	$ErrorActionPreference = 'Continue'
	$lines = New-Object System.Collections.Generic.List[string]
	& $phi @Arguments 2>&1 | ForEach-Object {
		$line = "$_"
		$lines.Add($line)
		Write-Host $line
	}
	return [pscustomobject]@{ Code = $LASTEXITCODE; Lines = $lines }
}

$manifest = Import-PowerShellDataFile (Join-Path $root 'libraries.psd1')
$libraries = @($manifest.Libraries)

# Each library's dependencies must be listed before it, so one pass is the build order.
$known = @{}
foreach ($library in $libraries) {
	foreach ($used in $library.Uses) {
		if (-not $known.ContainsKey($used)) {
			throw "$($library.Name) uses $used, which must be listed before it in libraries.psd1."
		}
	}
	$known[$library.Name] = $library
}

# Every library something reaches, in build order.
function Get-Closure {
	param([string]$LibraryName)

	$found = New-Object System.Collections.Generic.List[string]
	foreach ($used in $known[$LibraryName].Uses) {
		foreach ($item in (Get-Closure $used)) {
			if (-not $found.Contains($item)) { $found.Add($item) }
		}
		if (-not $found.Contains($used)) { $found.Add($used) }
	}
	return $found
}

# What was asked for, by file name (imagelib) or folder (image), and what those need.
$wanted = New-Object System.Collections.Generic.HashSet[string]
if ($Name.Count -eq 0) {
	foreach ($library in $libraries) { [void]$wanted.Add($library.Name) }
}
else {
	foreach ($item in $Name) {
		$match = $libraries | Where-Object { $_.Name -eq $item -or (Split-Path $_.Folder -Leaf) -eq $item }
		if (-not $match) {
			throw "There's no library called $item in libraries.psd1."
		}
		[void]$wanted.Add($match.Name)
		foreach ($used in (Get-Closure $match.Name)) { [void]$wanted.Add($used) }
	}
}

if ($libraries.Count -eq 0) {
	Write-Host 'libraries.psd1 lists no libraries yet: nothing to build.'
	exit 0
}

New-Item -ItemType Directory -Force -Path $dist | Out-Null
$built = @($libraries | Where-Object { $wanted.Contains($_.Name) })

# ---------------------------------------------------------------- build

Push-Location $root
try {
	foreach ($library in $built) {
		$folder = Join-Path $root $library.Folder
		$source = Join-Path $library.Folder "$($library.Name).phi"
		if (-not (Test-Path (Join-Path $root $source))) {
			throw "$source doesn't exist."
		}

		foreach ($used in (Get-Closure $library.Name)) {
			Copy-Item (Join-Path $dist "$used.philib") $folder -Force
		}

		Write-Host "== building $($library.Name)"
		$result = Invoke-Phi @('build', $source, '--library', '-o', 'dist')
		if ($result.Code -ne 0) {
			Write-Host "FAILED: $($library.Name) didn't build." -ForegroundColor Red
			exit 1
		}

		$warnings = @($result.Lines | Where-Object { $_ -match '(^|: )warning: ' })
		if ($warnings.Count -gt 0) {
			Write-Host "FAILED: $($library.Name) has $($warnings.Count) warning(s), and warnings count as bugs here." -ForegroundColor Red
			exit 1
		}
	}
}
finally {
	Pop-Location
}

if (-not $Test) {
	Write-Host "Built $($built.Count) librar$(if ($built.Count -eq 1) { 'y' } else { 'ies' }) into dist/."
	exit 0
}

# ---------------------------------------------------------------- test

$results = New-Object System.Collections.Generic.List[object]

function Add-Run {
	param([string]$LibraryName, [string]$Kind, [string]$Folder)

	Write-Host "== $LibraryName, $Kind tests"
	Push-Location $Folder
	try {
		$run = Invoke-Phi @('test', '.', '-f', 'test_', '--timeout', "$Timeout")
	}
	finally {
		Pop-Location
	}
	$results.Add([pscustomobject]@{
			Library = $LibraryName
			Kind    = $Kind
			Result  = if ($run.Code -eq 0) { 'pass' } else { 'FAIL' }
		})
}

foreach ($library in $built) {
	$folder = Join-Path $root $library.Folder
	$useFolder = Join-Path $folder 'tests\use'
	$hasInternal = @(Get-ChildItem $folder -Filter 'test_*.phi').Count -gt 0
	$hasCompiled = (Test-Path $useFolder) -and @(Get-ChildItem $useFolder -Filter 'test_*.phi').Count -gt 0

	if (-not $hasInternal -and -not $hasCompiled) {
		Write-Host "note: $($library.Name) has no tests."
	}
	if ($hasInternal) {
		Add-Run $library.Name 'internal' $folder
	}
	if ($hasCompiled) {
		foreach ($item in @((Get-Closure $library.Name)) + $library.Name) {
			Copy-Item (Join-Path $dist "$item.philib") $useFolder -Force
		}
		Add-Run $library.Name 'compiled' $useFolder
	}
}

Write-Host ''
$results | Format-Table -AutoSize | Out-String | Write-Host

if ($results.Count -eq 0) {
	Write-Host 'No tests were run.'
	exit 0
}
$failed = @($results | Where-Object { $_.Result -eq 'FAIL' })
if ($failed.Count -gt 0) {
	Write-Host "FAILED: $($failed.Count) of $($results.Count) test runs." -ForegroundColor Red
	exit 1
}
Write-Host "All $($results.Count) test runs passed."
exit 0
