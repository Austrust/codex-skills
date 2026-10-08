param(
    [Parameter(Mandatory = $true)]
    [string]$PdfPath,

    [string]$OutputJson = "outputs\mineru_result.json",

    [string]$Endpoint = "http://localhost:18000/file_parse",

    [string]$Backend = "pipeline",

    [string]$ParseMethod = "auto",

    [bool]$FormulaEnable = $true,

    [bool]$TableEnable = $true,

    [bool]$ImageAnalysis = $false
)

$ErrorActionPreference = "Stop"

$resolvedPdf = Resolve-Path -LiteralPath $PdfPath
$outputParent = Split-Path -Parent $OutputJson
if ($outputParent) {
    New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
}

$formula = $FormulaEnable.ToString().ToLowerInvariant()
$table = $TableEnable.ToString().ToLowerInvariant()
$image = $ImageAnalysis.ToString().ToLowerInvariant()

curl.exe -sS -X POST $Endpoint `
    -F "files=@$resolvedPdf" `
    -F "backend=$Backend" `
    -F "parse_method=$ParseMethod" `
    -F "return_md=true" `
    -F "return_content_list=true" `
    -F "return_images=true" `
    -F "formula_enable=$formula" `
    -F "table_enable=$table" `
    -F "image_analysis=$image" `
    -o $OutputJson

if ($LASTEXITCODE -ne 0) {
    throw "MinerU local parse failed with curl exit code $LASTEXITCODE"
}

$raw = Get-Content -LiteralPath $OutputJson -Raw -Encoding UTF8
$json = $raw | ConvertFrom-Json

if ($json.status -ne "completed") {
    throw "MinerU local parse did not complete. status=$($json.status) error=$($json.error)"
}

Write-Output $OutputJson
