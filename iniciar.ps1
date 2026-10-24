$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

try {
    $status = Invoke-RestMethod 'http://127.0.0.1:8090/api/status' -TimeoutSec 3
    $painelAtivo = $true
} catch {
    $painelAtivo = $false
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker nao encontrado. Instale e abra o Docker Desktop antes de continuar.'
}
docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Abra o Docker Desktop, aguarde o motor iniciar e execute este arquivo novamente.'
}
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar o motor de buscas.' }

if ($painelAtivo) {
    Start-Process 'http://localhost:8090'
    Write-Host 'O painel ja esta rodando em http://localhost:8090'
    exit 0
}

$pythonExe = $null
function Test-PythonRuntime([string]$caminho) {
    # No Windows PowerShell, stderr de um executavel pode virar erro terminante.
    # Um alias da Microsoft Store ou launcher sem Python deve apenas falhar no teste.
    $preferenciaAnterior = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $caminho -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $preferenciaAnterior
    }
}
foreach ($nome in @('python', 'py')) {
    $candidato = Get-Command $nome -CommandType Application -ErrorAction SilentlyContinue
    if ($candidato) {
        if (Test-PythonRuntime $candidato.Source) { $pythonExe = $candidato.Source; break }
    }
}
if (-not $pythonExe) {
    $runtimeLocal = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if ((Test-Path -LiteralPath $runtimeLocal) -and (Test-PythonRuntime $runtimeLocal)) {
        $pythonExe = $runtimeLocal
    }
}
if (-not $pythonExe) {
    throw 'Instale Python 3.9 ou superior com a opcao Add Python to PATH e tente novamente.'
}

Write-Host 'Painel: http://localhost:8090. Mantenha esta janela aberta. Ctrl+C encerra o painel.'
& $pythonExe -X utf8 -u painel/server.py
exit $LASTEXITCODE
