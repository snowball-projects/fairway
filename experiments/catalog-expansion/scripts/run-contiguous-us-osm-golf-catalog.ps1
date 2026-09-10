param(
  [string]$ManifestPath = (Join-Path $PSScriptRoot "contiguous-us-osm-sources.json"),

  [string]$ArtifactRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) ".local\contiguous-us-osm-rehearsal"),

  [string]$OsmiumPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".local\illinois-osm-rehearsal\osmium-env\Library\bin\osmium.exe"),

  [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
$manifestFullPath = (Resolve-Path -LiteralPath $ManifestPath).Path
$artifactRootPath = [System.IO.Path]::GetFullPath($ArtifactRoot)
$localRootPath = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot ".local"))
$localPrefix = $localRootPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if (-not $artifactRootPath.StartsWith($localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
  throw "ArtifactRoot must be below the repository's ignored .local directory."
}

$artifactRelativeToLocal = $artifactRootPath.Substring($localPrefix.Length).Replace("\", "/")
& git -C $repositoryRoot check-ignore -q -- ".local/$artifactRelativeToLocal/ignore-check"
if ($LASTEXITCODE -ne 0) {
  throw "The national rehearsal artifact directory is not ignored by git."
}

$manifest = Get-Content -Raw -LiteralPath $manifestFullPath | ConvertFrom-Json
$sources = @($manifest.jurisdictions)
if ($sources.Count -ne 49) {
  throw "The manifest must contain the 48 contiguous states plus Washington, DC (49 jurisdictions)."
}

$slugs = @($sources | ForEach-Object { [string]$_.slug })
$sortedSlugs = @($slugs)
[Array]::Sort($sortedSlugs, [StringComparer]::Ordinal)
if (($slugs -join "`n") -cne ($sortedSlugs -join "`n")) {
  throw "Manifest jurisdictions must be in deterministic ordinal slug order."
}
if (@($slugs | Select-Object -Unique).Count -ne $slugs.Count) {
  throw "Manifest jurisdiction slugs must be unique."
}
foreach ($excluded in @("alaska", "hawaii", "puerto-rico")) {
  if ($slugs -contains $excluded) {
    throw "The contiguous-US manifest must not include $excluded."
  }
}

$totalCompressedBytes = [long]0
$largestSourceBytes = [long]0
foreach ($source in $sources) {
  if ($source.file -ne "$($source.slug)-260731.osm.pbf") {
    throw "Unexpected fixed source filename for $($source.slug)."
  }
  if ($source.md5 -notmatch '^[0-9a-f]{32}$' -or [long]$source.expectedBytes -le 0) {
    throw "Invalid size or MD5 in the manifest for $($source.slug)."
  }
  $totalCompressedBytes += [long]$source.expectedBytes
  $largestSourceBytes = [Math]::Max($largestSourceBytes, [long]$source.expectedBytes)
}

$drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($artifactRootPath))
$estimatedIntermediateBytes = [long][Math]::Ceiling($totalCompressedBytes * 0.02)
$estimatedCatalogAndLogBytes = 50MB
$estimatedWorkingBytes = $totalCompressedBytes + $estimatedIntermediateBytes + $estimatedCatalogAndLogBytes
$preflight = [ordered]@{
  includedJurisdictions = $sources.Count
  extractDate = [string]$manifest.extractDate
  totalCompressedSourceBytes = $totalCompressedBytes
  largestSourceBytes = $largestSourceBytes
  estimatedIntermediateBytes = $estimatedIntermediateBytes
  estimatedCatalogAndLogBytes = $estimatedCatalogAndLogBytes
  estimatedWorkingBytes = $estimatedWorkingBytes
  availableBytes = [long]$drive.AvailableFreeSpace
  sufficientSpace = [long]$drive.AvailableFreeSpace -ge $estimatedWorkingBytes
  artifactRoot = $artifactRootPath
  artifactRootIgnored = $true
  resumablePerJurisdiction = $true
  ordering = "manifest ordinal slug order"
}
if (-not $preflight.sufficientSpace) {
  throw "Insufficient working space: estimated $estimatedWorkingBytes bytes, available $($drive.AvailableFreeSpace) bytes."
}
if ($PreflightOnly) {
  $preflight | ConvertTo-Json -Compress
  exit 0
}

$toolPath = (Resolve-Path -LiteralPath $OsmiumPath).Path
$extractorPath = Join-Path $PSScriptRoot "extract-illinois-osm-golf-courses.ps1"
$generatorPath = Join-Path $PSScriptRoot "generate-golf-course-catalog.ts"
[System.IO.Directory]::CreateDirectory($artifactRootPath) | Out-Null
$statesRoot = Join-Path $artifactRootPath "states"
[System.IO.Directory]::CreateDirectory($statesRoot) | Out-Null
$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
$pipelineStarted = [System.Diagnostics.Stopwatch]::StartNew()
$resumedJurisdictions = 0
$downloadedJurisdictions = 0
$stateResults = [System.Collections.Generic.List[object]]::new()

function Write-JsonFile {
  param([string]$Path, $Value)

  [System.IO.File]::WriteAllText(
    $Path,
    (($Value | ConvertTo-Json -Compress -Depth 20) + "`n"),
    $utf8WithoutBom
  )
}

function Invoke-Download {
  param([string]$Url, [string]$Destination)

  if (Test-Path -LiteralPath $Destination) {
    return [pscustomobject]@{ downloaded = $false; durationMs = 0.0 }
  }
  $partialPath = "$Destination.part"
  $started = [System.Diagnostics.Stopwatch]::StartNew()
  & curl.exe --silent --show-error -L --fail --retry 5 --retry-all-errors --continue-at - --output $partialPath $Url
  if ($LASTEXITCODE -ne 0) {
    throw "Download failed for $Url with curl exit code $LASTEXITCODE."
  }
  Move-Item -LiteralPath $partialPath -Destination $Destination
  $started.Stop()
  return [pscustomobject]@{ downloaded = $true; durationMs = $started.Elapsed.TotalMilliseconds }
}

function Read-CompletedState {
  param($Source, [string]$StateDirectory, [string]$PbfPath, [string]$JsonlPath)

  $markerPath = Join-Path $StateDirectory "complete.json"
  if (-not (Test-Path -LiteralPath $markerPath) -or
      -not (Test-Path -LiteralPath $PbfPath) -or
      -not (Test-Path -LiteralPath $JsonlPath)) {
    return $null
  }
  $marker = Get-Content -Raw -LiteralPath $markerPath | ConvertFrom-Json
  if ([int]$marker.markerSchemaVersion -ne 1 -or
      $marker.slug -cne $Source.slug -or
      $marker.sourceFile -cne $Source.file -or
      $marker.publishedMd5 -cne $Source.md5 -or
      [long]$marker.sourceBytes -ne [long]$Source.expectedBytes -or
      (Get-Item -LiteralPath $PbfPath).Length -ne [long]$Source.expectedBytes) {
    return $null
  }
  $jsonlSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $JsonlPath).Hash.ToLowerInvariant()
  if ($jsonlSha256 -cne $marker.outputJsonlSha256) {
    return $null
  }
  return $marker
}

foreach ($source in $sources) {
  $stateDirectory = Join-Path $statesRoot $source.slug
  [System.IO.Directory]::CreateDirectory($stateDirectory) | Out-Null
  $pbfPath = Join-Path $stateDirectory $source.file
  $checksumPath = "$pbfPath.md5"
  $jsonlPath = Join-Path $stateDirectory "$($source.slug)-golf-courses.jsonl"
  $completed = Read-CompletedState $source $stateDirectory $pbfPath $jsonlPath
  if ($null -ne $completed) {
    Write-Host "Reusing verified $($source.slug) artifacts."
    $resumedJurisdictions += 1
    $stateResults.Add($completed)
    continue
  }

  Write-Host "Downloading and extracting $($source.slug)..."
  $sourceUrl = "$($manifest.baseUrl)/$($source.file)"
  $download = Invoke-Download $sourceUrl $pbfPath
  $checksumDownload = Invoke-Download "$sourceUrl.md5" $checksumPath
  if ($download.downloaded) {
    $downloadedJurisdictions += 1
  }
  if ((Get-Item -LiteralPath $pbfPath).Length -ne [long]$source.expectedBytes) {
    throw "Downloaded size does not match the manifest for $($source.slug)."
  }
  $publishedMd5 = ((Get-Content -Raw -LiteralPath $checksumPath).Trim() -split '\s+')[0].ToLowerInvariant()
  if ($publishedMd5 -cne $source.md5) {
    throw "Published MD5 does not match the fixed manifest for $($source.slug)."
  }
  $verifiedMd5 = (Get-FileHash -Algorithm MD5 -LiteralPath $pbfPath).Hash.ToLowerInvariant()
  if ($verifiedMd5 -cne $publishedMd5) {
    throw "Source checksum verification failed for $($source.slug)."
  }

  $extractionOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File $extractorPath `
    -InputPbf $pbfPath `
    -OutputJsonl $jsonlPath `
    -OsmiumPath $toolPath `
    -SourceIdentifier $source.slug `
    -ArtifactPrefix $source.slug
  if ($LASTEXITCODE -ne 0) {
    throw "Extraction failed for $($source.slug) with exit code $LASTEXITCODE."
  }
  $extraction = ($extractionOutput | Select-Object -Last 1) | ConvertFrom-Json
  $result = [ordered]@{
    markerSchemaVersion = 1
    name = [string]$source.name
    slug = [string]$source.slug
    sourceFile = [string]$source.file
    sourceUrl = $sourceUrl
    checksumUrl = "$sourceUrl.md5"
    sourceBytes = [long]$source.expectedBytes
    publishedMd5 = $publishedMd5
    verifiedMd5 = $verifiedMd5
    sourceSha256 = [string]$extraction.sourceSha256
    snapshotTimestamp = [string]$extraction.snapshotTimestamp
    checksumVerified = $true
    downloadDurationMs = [double]$download.durationMs + [double]$checksumDownload.durationMs
    sourceCourseObjects = [long]$extraction.sourceCourseObjects
    sourceCourseNodes = [long]$extraction.sourceCourseNodes
    sourceCourseWays = [long]$extraction.sourceCourseWays
    sourceCourseRelations = [long]$extraction.sourceCourseRelations
    missingGeometryReferences = [long]$extraction.missingGeometryReferences
    courseObjectsWithMissingGeometryReferences = [long]$extraction.courseObjectsWithMissingGeometryReferences
    containedOrAssociatedEvidenceObjects = [long]$extraction.containedOrAssociatedEvidenceObjects
    filteredPbfBytes = [long]$extraction.filteredPbfBytes
    exportedXmlBytes = [long]$extraction.exportedXmlBytes
    outputJsonlBytes = [long]$extraction.outputJsonlBytes
    extractionDurationMs = [double]$extraction.durationMs
    peakWorkingSetBytes = [long]$extraction.peakWorkingSetBytes
    osmiumPeakWorkingSetBytes = [long]$extraction.osmiumPeakWorkingSetBytes
    adapterPeakWorkingSetBytes = [long]$extraction.adapterPeakWorkingSetBytes
    outputJsonlSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $jsonlPath).Hash.ToLowerInvariant()
  }
  Write-JsonFile (Join-Path $stateDirectory "complete.json") $result
  $stateResults.Add([pscustomobject]$result)
}

$combinedPath = Join-Path $artifactRootPath "contiguous-us-golf-courses.jsonl"
function Get-TextSha256 {
  param([string]$Value)

  $algorithm = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = $utf8WithoutBom.GetBytes($Value)
    return ([BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
  } finally {
    $algorithm.Dispose()
  }
}

$manifestFingerprintRows = @(
  [string]$manifest.provider
  [string]$manifest.dataset
  [string]$manifest.extractDate
  [string]$manifest.baseUrl
  foreach ($source in $sources) {
    "$($source.name)|$($source.slug)|$($source.file)|$($source.expectedBytes)|$($source.md5)"
  }
)
$manifestSha256 = Get-TextSha256 ($manifestFingerprintRows -join "`n")
$nationalSnapshot = "geofabrik-contiguous-us-$($manifest.extractDate)-manifest-sha256-$manifestSha256"
$combinedWriter = [System.IO.StreamWriter]::new($combinedPath, $false, $utf8WithoutBom)
$seenIdentities = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$combinedSourceRecords = 0
$repeatedExactIdentities = 0
try {
  $combinedWriter.WriteLine((([ordered]@{ kind = "source"; snapshot = $nationalSnapshot }) | ConvertTo-Json -Compress))
  foreach ($source in $sources) {
    $jsonlPath = Join-Path (Join-Path $statesRoot $source.slug) "$($source.slug)-golf-courses.jsonl"
    $reader = [System.IO.StreamReader]::new($jsonlPath, $utf8WithoutBom, $true)
    $sourceHeaders = 0
    try {
      while (($line = $reader.ReadLine()) -ne $null) {
        if (-not $line.Trim()) {
          continue
        }
        $row = $line | ConvertFrom-Json
        if ($row.kind -eq "source") {
          $sourceHeaders += 1
          continue
        }
        if ($row.kind -ne "course") {
          throw "Unexpected row kind in $jsonlPath."
        }
        $combinedSourceRecords += 1
        $identity = "$($row.course.type)/$($row.course.id)"
        if (-not $seenIdentities.Add($identity)) {
          $repeatedExactIdentities += 1
        }
        $combinedWriter.WriteLine($line)
      }
    } finally {
      $reader.Dispose()
    }
    if ($sourceHeaders -ne 1) {
      throw "Expected one source header in $jsonlPath."
    }
  }
} finally {
  $combinedWriter.Dispose()
}

function Quote-ProcessArgument {
  param([string]$Value)
  return '"' + $Value.Replace('"', '\"') + '"'
}

function Invoke-CatalogGenerator {
  param([string]$OutputPath)

  $nodePath = (Get-Command node.exe).Source
  $arguments = @($generatorPath, $combinedPath, $OutputPath) | ForEach-Object { Quote-ProcessArgument $_ }
  $startInfo = [System.Diagnostics.ProcessStartInfo]::new($nodePath, ($arguments -join " "))
  $startInfo.UseShellExecute = $false
  $startInfo.RedirectStandardOutput = $true
  $startInfo.RedirectStandardError = $true
  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $startInfo
  $wallClock = [System.Diagnostics.Stopwatch]::StartNew()
  $process.Start() | Out-Null
  $peakWorkingSetBytes = [long]0
  while (-not $process.WaitForExit(25)) {
    $process.Refresh()
    $peakWorkingSetBytes = [Math]::Max($peakWorkingSetBytes, $process.WorkingSet64)
  }
  $wallClock.Stop()
  $stdout = $process.StandardOutput.ReadToEnd().Trim()
  $stderr = $process.StandardError.ReadToEnd().Trim()
  $process.Refresh()
  $peakWorkingSetBytes = [Math]::Max($peakWorkingSetBytes, $process.PeakWorkingSet64)
  if ($process.ExitCode -ne 0) {
    throw "Catalog generation failed with exit code $($process.ExitCode): $stderr"
  }
  $pattern = '(\d+) source records; (\d+) courses; (\d+) skipped; (\d+) duplicates folded; (\d+) conflicts; (\d+) invalid fields; (\d+) unknown fields; (\d+) bytes; ([0-9.]+) ms'
  if ($stdout -notmatch $pattern) {
    throw "Could not parse catalog generator summary: $stdout"
  }
  return [pscustomobject]@{
    sourceRecordCount = [long]$Matches[1]
    emittedCourseCount = [long]$Matches[2]
    skippedRecordCount = [long]$Matches[3]
    duplicateRecordCount = [long]$Matches[4]
    conflictCount = [long]$Matches[5]
    invalidCount = [long]$Matches[6]
    unknownFieldTotal = [long]$Matches[7]
    outputBytes = [long]$Matches[8]
    generatorDurationMs = [double]$Matches[9]
    wallClockDurationMs = $wallClock.Elapsed.TotalMilliseconds
    peakWorkingSetBytes = $peakWorkingSetBytes
  }
}

$firstCatalogPath = Join-Path $artifactRootPath "contiguous-us-catalog-first.json"
$secondCatalogPath = Join-Path $artifactRootPath "contiguous-us-catalog-second.json"
$firstGeneration = Invoke-CatalogGenerator $firstCatalogPath
$secondGeneration = Invoke-CatalogGenerator $secondCatalogPath
$firstCatalogSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $firstCatalogPath).Hash.ToLowerInvariant()
$secondCatalogSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $secondCatalogPath).Hash.ToLowerInvariant()
$catalogsByteIdentical = [System.Linq.Enumerable]::SequenceEqual(
  [byte[]][System.IO.File]::ReadAllBytes($firstCatalogPath),
  [byte[]][System.IO.File]::ReadAllBytes($secondCatalogPath)
)
if (-not $catalogsByteIdentical) {
  throw "The two national catalog generations were not byte-identical."
}

$catalog = Get-Content -Raw -LiteralPath $firstCatalogPath | ConvertFrom-Json
$unknownCounts = [ordered]@{
  name = @($catalog.courses | Where-Object { $null -eq $_.name }).Count
  holes = @($catalog.courses | Where-Object { $null -eq $_.holes }).Count
  par = @($catalog.courses | Where-Object { $null -eq $_.par }).Count
  access = @($catalog.courses | Where-Object { $_.access -eq "unknown" }).Count
  format = @($catalog.courses | Where-Object { $null -eq $_.format }).Count
  operator = @($catalog.courses | Where-Object { $null -eq $_.operator }).Count
  website = @($catalog.courses | Where-Object { $null -eq $_.website }).Count
  address = @($catalog.courses | Where-Object { $null -eq $_.address }).Count
}
$coordinateCounts = [ordered]@{
  exact = @($catalog.courses | Where-Object { -not $_.coordinate.approximate }).Count
  approximate = @($catalog.courses | Where-Object { $_.coordinate.approximate }).Count
  lackingShortlistCoordinates = @($catalog.courses | Where-Object {
    $null -eq $_.latitude -or $null -eq $_.longitude -or
    [double]::IsNaN([double]$_.latitude) -or [double]::IsNaN([double]$_.longitude)
  }).Count
}
$accessCounts = [ordered]@{}
foreach ($access in @("public", "private", "municipal", "unknown")) {
  $accessCounts[$access] = @($catalog.courses | Where-Object { $_.access -eq $access }).Count
}

function Get-HaversineKilometers {
  param($Left, $Right)

  $radians = [Math]::PI / 180
  $latitudeDifference = ([double]$Right.latitude - [double]$Left.latitude) * $radians
  $longitudeDifference = ([double]$Right.longitude - [double]$Left.longitude) * $radians
  $a = [Math]::Sin($latitudeDifference / 2) * [Math]::Sin($latitudeDifference / 2) +
    [Math]::Cos([double]$Left.latitude * $radians) * [Math]::Cos([double]$Right.latitude * $radians) *
    [Math]::Sin($longitudeDifference / 2) * [Math]::Sin($longitudeDifference / 2)
  return 6371.0088 * 2 * [Math]::Atan2([Math]::Sqrt($a), [Math]::Sqrt(1 - $a))
}

$potentialDuplicatePairsWithinOneKm = 0
$namedGroups = @($catalog.courses | Where-Object { $null -ne $_.name } | Group-Object { $_.name.Trim().ToLowerInvariant() })
foreach ($group in $namedGroups) {
  $items = @($group.Group)
  for ($left = 0; $left -lt $items.Count; $left += 1) {
    for ($right = $left + 1; $right -lt $items.Count; $right += 1) {
      if ((Get-HaversineKilometers $items[$left] $items[$right]) -le 1) {
        $potentialDuplicatePairsWithinOneKm += 1
      }
    }
  }
}

function Sum-StateMetric {
  param([string]$Name)
  return [long](($stateResults | Measure-Object -Property $Name -Sum).Sum)
}

$pipelineStarted.Stop()
$osmiumVersion = (& $toolPath --version | Select-Object -First 2) -join "; "
$structuralFolds = $seenIdentities.Count - [long]$firstGeneration.emittedCourseCount
$summary = [ordered]@{
  preflight = $preflight
  provider = [string]$manifest.provider
  dataset = [string]$manifest.dataset
  manifestSha256 = $manifestSha256
  nationalSnapshot = $nationalSnapshot
  osmiumVersion = $osmiumVersion
  jurisdictions = @($stateResults)
  execution = [ordered]@{
    pipelineWallClockMs = $pipelineStarted.Elapsed.TotalMilliseconds
    downloadedJurisdictions = $downloadedJurisdictions
    resumedJurisdictions = $resumedJurisdictions
    failedJurisdictions = 0
    extractionDurationMs = [double](($stateResults | Measure-Object -Property extractionDurationMs -Sum).Sum)
    extractionPeakWorkingSetBytes = [long](($stateResults | Measure-Object -Property peakWorkingSetBytes -Maximum).Maximum)
  }
  extraction = [ordered]@{
    sourceCourseObjects = (Sum-StateMetric "sourceCourseObjects")
    sourceCourseNodes = (Sum-StateMetric "sourceCourseNodes")
    sourceCourseWays = (Sum-StateMetric "sourceCourseWays")
    sourceCourseRelations = (Sum-StateMetric "sourceCourseRelations")
    missingGeometryReferences = (Sum-StateMetric "missingGeometryReferences")
    courseObjectsWithMissingGeometryReferences = (Sum-StateMetric "courseObjectsWithMissingGeometryReferences")
    containedOrAssociatedEvidenceObjects = (Sum-StateMetric "containedOrAssociatedEvidenceObjects")
    filteredPbfBytes = (Sum-StateMetric "filteredPbfBytes")
    exportedXmlBytes = (Sum-StateMetric "exportedXmlBytes")
    stateJsonlBytes = (Sum-StateMetric "outputJsonlBytes")
    combinedJsonlBytes = (Get-Item -LiteralPath $combinedPath).Length
    combinedJsonlSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $combinedPath).Hash.ToLowerInvariant()
    combinedSourceRecords = $combinedSourceRecords
    repeatedExactIdentities = $repeatedExactIdentities
    uniqueSourceIdentities = $seenIdentities.Count
  }
  generation = [ordered]@{
    first = $firstGeneration
    second = $secondGeneration
    structuralFolds = $structuralFolds
    potentialDuplicateNamePairsWithinOneKmPreserved = $potentialDuplicatePairsWithinOneKm
    unknownCounts = $unknownCounts
    accessCounts = $accessCounts
    coordinateCounts = $coordinateCounts
    catalogsByteIdentical = $catalogsByteIdentical
    catalogSha256 = $firstCatalogSha256
  }
}
$summaryPath = Join-Path $artifactRootPath "run-summary.json"
Write-JsonFile $summaryPath $summary
$summary.localWorkingBytes = [long](Get-ChildItem -LiteralPath $artifactRootPath -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-JsonFile $summaryPath $summary
$summary | ConvertTo-Json -Compress -Depth 20
