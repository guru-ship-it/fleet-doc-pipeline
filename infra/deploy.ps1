# Deploy the demo stack to ap-south-1 (Mumbai): artifacts bucket, the secret, the Lambda package and the stack.
# Run from anywhere:  powershell -NoProfile -File infra\deploy.ps1 [-RegistryFile demo/registry.live.json]
#
# The secret is created once, with PASTE_HERE placeholders, a random WA_VERIFY_TOKEN and a random DASHBOARD_KEY (the
# dashboard access code, meant to be shared with viewers). The account owner pastes the real values in the AWS console;
# they never go in code, files or chat. Re-running this script never touches them. An existing secret gets its
# DASHBOARD_KEY from infra\ensure_dashboard_key.py.
param(
  [string]$RegistryFile = 'demo/registry.example.json',
  [ValidateSet('muse', 'standin')][string]$ModelMode = 'muse'
)

$Region = 'ap-south-1'
$Account = $env:FLEET_AWS_ACCOUNT   # the account id this stack belongs in; set in the shell, not kept in the repository
if (-not $Account) { throw "Set FLEET_AWS_ACCOUNT to the 12-digit AWS account id this stack belongs in" }
$Stack = 'fleet-doc-pipeline-demo'
$Artifacts = 'cdai-fleet-pipeline-artifacts-mumbai'
$SecretName = 'fleet-doc-pipeline/demo'
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Aws {
  & aws.exe @args
  if ($LASTEXITCODE -ne 0) { throw "aws $($args[0]) $($args[1]) failed (exit code $LASTEXITCODE)" }
}

if ((Invoke-Aws sts get-caller-identity --query Account --output text) -ne $Account) {
  throw "Signed in to the wrong AWS account: this stack belongs in CDAI ($Account)"
}

& aws.exe s3api head-bucket --bucket $Artifacts 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Invoke-Aws s3api create-bucket --bucket $Artifacts --region $Region --create-bucket-configuration "LocationConstraint=$Region" | Out-Null
  Invoke-Aws s3api put-public-access-block --bucket $Artifacts --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
  Write-Host "Created artifacts bucket $Artifacts"
}

& aws.exe secretsmanager describe-secret --secret-id $SecretName --region $Region 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $verify = Invoke-Aws secretsmanager get-random-password --password-length 32 --exclude-punctuation --query RandomPassword --output text --region $Region
  $dash = 'fleet-' + (Invoke-Aws secretsmanager get-random-password --password-length 10 --exclude-punctuation --exclude-uppercase --query RandomPassword --output text --region $Region)
  $value = [ordered]@{
    META_API_KEY = 'PASTE_HERE'; WA_ACCESS_TOKEN = 'PASTE_HERE'; WA_APP_SECRET = 'PASTE_HERE'
    WA_PHONE_NUMBER_ID = 'PASTE_HERE'; WA_VERIFY_TOKEN = $verify; DASHBOARD_KEY = $dash
  } | ConvertTo-Json -Compress
  $tmp = [IO.Path]::GetTempFileName()
  try {
    [IO.File]::WriteAllText($tmp, $value)     # UTF-8 without BOM; a file avoids PowerShell's quoting of JSON
    Invoke-Aws secretsmanager create-secret --name $SecretName --region $Region --secret-string "file://$tmp" `
      --description 'Fleet document pipeline demo: Meta Model API key and WhatsApp Cloud API values' | Out-Null
  } finally {
    Remove-Item $tmp -Force
  }
  Write-Host "Created secret $SecretName with placeholders. Dashboard access code: $dash"
}

Push-Location $Root
try {
  python infra\build_lambda.py
  if ($LASTEXITCODE -ne 0) { throw 'Lambda package build failed' }
  Invoke-Aws cloudformation package --template-file infra\template.yaml --s3-bucket $Artifacts --s3-prefix lambda `
    --output-template-file build\packaged.yaml --region $Region | Out-Null
  Invoke-Aws cloudformation deploy --template-file build\packaged.yaml --stack-name $Stack --capabilities CAPABILITY_IAM `
    --region $Region --no-fail-on-empty-changeset --parameter-overrides "RegistryFile=$RegistryFile" "ModelMode=$ModelMode"
  Invoke-Aws cloudformation describe-stacks --stack-name $Stack --region $Region `
    --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table
} finally {
  Pop-Location
}
