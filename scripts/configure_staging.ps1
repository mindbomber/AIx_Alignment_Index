[CmdletBinding()]
param(
    [string]$EnvFile = ".env.staging",
    [string]$KubeContext,
    [string]$Repository = "mindbomber/AIx_Alignment_Index"
)

$ErrorActionPreference = "Stop"

function Read-EnvironmentFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Environment file not found: $Path"
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) {
            throw "Invalid environment line: $line"
        }
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $values
}

function Require-Value {
    param(
        [hashtable]$Values,
        [string]$Name
    )

    if (-not $Values.ContainsKey($Name) -or [string]::IsNullOrWhiteSpace($Values[$Name])) {
        throw "$Name is required in the staging environment file."
    }
}

function Set-GitHubEnvironmentSecret {
    param(
        [string]$Name,
        [string]$Value
    )

    $Value | gh secret set $Name --repo $Repository --env staging
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to set GitHub staging secret: $Name"
    }
}

function Invoke-KubectlApply {
    param([string[]]$Arguments)

    & kubectl @Arguments | kubectl apply -f - | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "kubectl apply failed."
    }
}

function New-StagingDeployerKubeconfig {
    Invoke-KubectlApply -Arguments @(
        "create", "serviceaccount", "aix-deployer",
        "--namespace", "aix-staging",
        "--dry-run=client", "-o", "yaml"
    )
    Invoke-KubectlApply -Arguments @(
        "create", "rolebinding", "aix-deployer-admin",
        "--namespace", "aix-staging",
        "--clusterrole", "admin",
        "--serviceaccount", "aix-staging:aix-deployer",
        "--dry-run=client", "-o", "yaml"
    )
    Invoke-KubectlApply -Arguments @(
        "create", "clusterrole", "aix-staging-namespace-reader",
        "--verb", "get",
        "--resource", "namespaces",
        "--dry-run=client", "-o", "yaml"
    )
    Invoke-KubectlApply -Arguments @(
        "create", "clusterrolebinding", "aix-staging-namespace-reader",
        "--clusterrole", "aix-staging-namespace-reader",
        "--serviceaccount", "aix-staging:aix-deployer",
        "--dry-run=client", "-o", "yaml"
    )

    @"
apiVersion: v1
kind: Secret
metadata:
  name: aix-deployer-token
  namespace: aix-staging
  annotations:
    kubernetes.io/service-account.name: aix-deployer
type: kubernetes.io/service-account-token
"@ | kubectl apply -f - | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the staging deployer token."
    }

    $token = ""
    for ($attempt = 0; $attempt -lt 30 -and -not $token; $attempt++) {
        $token = kubectl get secret aix-deployer-token `
            --namespace aix-staging `
            -o jsonpath='{.data.token}'
        if (-not $token) {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $token) {
        throw "The staging deployer token was not populated."
    }
    $decodedToken = [Text.Encoding]::UTF8.GetString(
        [Convert]::FromBase64String($token)
    )
    $certificateAuthority = kubectl get secret aix-deployer-token `
        --namespace aix-staging `
        -o jsonpath='{.data.ca\.crt}'
    $server = kubectl config view --minify `
        -o jsonpath='{.clusters[0].cluster.server}'
    if (-not $certificateAuthority -or -not $server) {
        throw "Unable to read the cluster endpoint or certificate authority."
    }

    return @"
apiVersion: v1
kind: Config
clusters:
  - name: aix-staging
    cluster:
      server: $server
      certificate-authority-data: $certificateAuthority
users:
  - name: aix-deployer
    user:
      token: $decodedToken
contexts:
  - name: aix-staging
    context:
      cluster: aix-staging
      namespace: aix-staging
      user: aix-deployer
current-context: aix-staging
"@
}

$values = Read-EnvironmentFile -Path $EnvFile
$requiredApplicationValues = @(
    "AIX_DATABASE_URL",
    "AIX_REDIS_URL",
    "AIX_TOKEN_PEPPER",
    "AIX_WEBHOOK_SECRET_PEPPER",
    "AIX_S3_BUCKET",
    "AIX_S3_REGION",
    "AIX_CORS_ORIGINS",
    "POSTGRES_PASSWORD"
)
$requiredAcceptanceValues = @(
    "AIX_E2E_ORG",
    "AIX_E2E_EMAIL",
    "AIX_E2E_PASSWORD"
)
foreach ($name in $requiredApplicationValues + $requiredAcceptanceValues) {
    Require-Value -Values $values -Name $name
}

if ($KubeContext) {
    kubectl config use-context $KubeContext | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to select Kubernetes context: $KubeContext"
    }
}
$currentContext = kubectl config current-context
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($currentContext)) {
    throw "No Kubernetes context is configured."
}

kubectl create namespace aix-staging --dry-run=client -o yaml |
    kubectl apply -f - | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Unable to create or update the aix-staging namespace."
}

$secretArguments = @(
    "create", "secret", "generic", "aix-secrets",
    "--namespace", "aix-staging"
)
$applicationNames = @(
    $requiredApplicationValues,
    "AIX_S3_ENDPOINT_URL",
    "AIX_S3_ACCESS_KEY_ID",
    "AIX_S3_SECRET_ACCESS_KEY",
    "AIX_S3_SERVER_SIDE_ENCRYPTION",
    "AIX_S3_KMS_KEY_ID",
    "AIX_OTLP_ENDPOINT",
    "AIX_OIDC_ISSUER",
    "AIX_OIDC_CLIENT_ID",
    "AIX_OIDC_CLIENT_SECRET",
    "AIX_OIDC_REDIRECT_URI",
    "AIX_OIDC_WEB_APP_URL"
)
foreach ($name in $applicationNames) {
    if ($values.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($values[$name])) {
        $secretArguments += "--from-literal=${name}=$($values[$name])"
    }
}
$secretArguments += @("--dry-run=client", "-o", "yaml")
& kubectl @secretArguments | kubectl apply -f - | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Unable to create or update aix-secrets."
}

$deployerKubeconfig = New-StagingDeployerKubeconfig
$kubeconfigBytes = [Text.Encoding]::UTF8.GetBytes($deployerKubeconfig)
$kubeconfigBase64 = [Convert]::ToBase64String($kubeconfigBytes)

Set-GitHubEnvironmentSecret -Name "KUBECONFIG_B64" -Value $kubeconfigBase64
foreach ($name in $requiredAcceptanceValues) {
    Set-GitHubEnvironmentSecret -Name $name -Value $values[$name]
}

Write-Host "Configured Kubernetes namespace and secret for context '$currentContext'."
Write-Host "Configured GitHub staging environment secrets for '$Repository'."
Write-Host "Secret values were not printed."
