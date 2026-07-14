param([switch]$SkipTests)

$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $root
try {
  $env:PYTHONPATH = 'backend'
  python scripts/build_retrieval_evidence_dataset.py
  python scripts/build_fact_evidence_dataset.py
  python scripts/run_retrieval_evidence.py
  python scripts/run_fact_extraction_evidence.py
  if (-not $SkipTests) {
    python -m coverage run --branch --data-file=evidence/raw/.coverage -m pytest backend/tests -q -p no:cacheprovider --junitxml=evidence/raw/pytest.xml
    python -m coverage json --data-file=evidence/raw/.coverage -o evidence/raw/coverage.json
  }
  python scripts/collect_evidence_environment.py
}
finally {
  Pop-Location
}
