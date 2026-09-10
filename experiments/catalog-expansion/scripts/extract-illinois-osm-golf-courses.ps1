param(
  [Parameter(Mandatory = $true)]
  [string]$InputPbf,

  [Parameter(Mandatory = $true)]
  [string]$OutputJsonl,

  [Parameter(Mandatory = $true)]
  [string]$OsmiumPath,

  [string]$SourceIdentifier = "illinois",

  [string]$ArtifactPrefix = "illinois"
)

$ErrorActionPreference = "Stop"

$inputPath = (Resolve-Path -LiteralPath $InputPbf).Path
$toolPath = (Resolve-Path -LiteralPath $OsmiumPath).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputJsonl)
$artifactDirectory = Split-Path -Parent $outputPath
if ($SourceIdentifier -notmatch '^[a-z0-9-]+$' -or $ArtifactPrefix -notmatch '^[a-z0-9-]+$') {
  throw "SourceIdentifier and ArtifactPrefix may contain only lowercase letters, numbers, and hyphens."
}
$filteredPath = Join-Path $artifactDirectory "$ArtifactPrefix-golf-filtered.osm.pbf"
$xmlPath = Join-Path $artifactDirectory "$ArtifactPrefix-golf-filtered.osm"

[System.IO.Directory]::CreateDirectory($artifactDirectory) | Out-Null

$started = [System.Diagnostics.Stopwatch]::StartNew()
$peakWorkingSetBytes = [long]0

function Invoke-Osmium {
  param([string[]]$CommandArguments)

  $quotedArguments = @(
    foreach ($argument in $CommandArguments) {
      '"' + $argument.Replace('"', '\"') + '"'
    }
  ) -join " "
  $startInfo = [System.Diagnostics.ProcessStartInfo]::new($toolPath, $quotedArguments)
  $startInfo.UseShellExecute = $false
  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $startInfo
  $process.Start() | Out-Null
  while (-not $process.WaitForExit(50)) {
    $process.Refresh()
    $script:peakWorkingSetBytes = [Math]::Max($script:peakWorkingSetBytes, $process.WorkingSet64)
  }
  $process.Refresh()
  if ($process.ExitCode -ne 0) {
    throw "osmium failed with exit code $($process.ExitCode): $($CommandArguments -join ' ')"
  }
  $script:peakWorkingSetBytes = [Math]::Max($script:peakWorkingSetBytes, $process.WorkingSet64)
  $process.Dispose()
}

Invoke-Osmium @(
  "tags-filter",
  $inputPath,
  "nwr/leisure=golf_course",
  "-o", $filteredPath,
  "--overwrite"
)

Invoke-Osmium @(
  "cat",
  $filteredPath,
  "-f", "osm,add_metadata=false",
  "-o", $xmlPath,
  "--overwrite"
)

$nodes = @{}
$ways = @{}
$relations = @{}
$sourceCourses = [System.Collections.Generic.List[object]]::new()
$missingGeometryReferences = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$courseObjectsWithMissingGeometryReferences = 0

function Save-OsmObject {
  param($SourceObject)

  $id = [string]$SourceObject.id
  if ($SourceObject.type -eq "node") {
    $script:nodes[$id] = @($SourceObject.latitude, $SourceObject.longitude)
  } elseif ($SourceObject.type -eq "way") {
    $script:ways[$id] = [pscustomobject]@{
      references = @($SourceObject.references)
      tags = $SourceObject.tags
    }
  } else {
    $script:relations[$id] = [pscustomobject]@{
      members = @($SourceObject.members)
      tags = $SourceObject.tags
    }
  }

  if ($SourceObject.tags.leisure -eq "golf_course") {
    $script:sourceCourses.Add(
      [pscustomobject]@{
        type = $SourceObject.type
        id = $SourceObject.id
        tags = $SourceObject.tags
        members = @($SourceObject.members)
      }
    )
  }
}

$settings = [System.Xml.XmlReaderSettings]::new()
$settings.IgnoreComments = $true
$settings.IgnoreWhitespace = $true
$reader = [System.Xml.XmlReader]::Create($xmlPath, $settings)
$current = $null
try {
  while ($reader.Read()) {
    if ($reader.NodeType -eq [System.Xml.XmlNodeType]::Element) {
      if ($reader.Name -in @("node", "way", "relation")) {
        $current = [pscustomobject]@{
          type = $reader.Name
          id = [long]$reader.GetAttribute("id")
          latitude = if ($reader.Name -eq "node") { [double]$reader.GetAttribute("lat") } else { $null }
          longitude = if ($reader.Name -eq "node") { [double]$reader.GetAttribute("lon") } else { $null }
          tags = @{}
          references = [System.Collections.Generic.List[long]]::new()
          members = [System.Collections.Generic.List[object]]::new()
        }
        if ($reader.IsEmptyElement) {
          Save-OsmObject $current
          $current = $null
        }
      } elseif ($reader.Name -eq "tag" -and $null -ne $current) {
        $current.tags[$reader.GetAttribute("k")] = $reader.GetAttribute("v")
      } elseif ($reader.Name -eq "nd" -and $null -ne $current) {
        $current.references.Add([long]$reader.GetAttribute("ref"))
      } elseif ($reader.Name -eq "member" -and $null -ne $current) {
        $current.members.Add(
          [pscustomobject]@{
            type = $reader.GetAttribute("type")
            id = [long]$reader.GetAttribute("ref")
            role = $reader.GetAttribute("role")
          }
        )
      }
    } elseif (
      $reader.NodeType -eq [System.Xml.XmlNodeType]::EndElement -and
      $reader.Name -in @("node", "way", "relation") -and
      $null -ne $current
    ) {
      Save-OsmObject $current
      $current = $null
    }
  }
} finally {
  $reader.Dispose()
}

function Add-NodeBounds {
  param(
    $Node,
    [hashtable]$Bounds
  )

  $latitude = [double]$Node[0]
  $longitude = [double]$Node[1]
  $Bounds.minLatitude = [Math]::Min($Bounds.minLatitude, $latitude)
  $Bounds.maxLatitude = [Math]::Max($Bounds.maxLatitude, $latitude)
  $Bounds.minLongitude = [Math]::Min($Bounds.minLongitude, $longitude)
  $Bounds.maxLongitude = [Math]::Max($Bounds.maxLongitude, $longitude)
}

function Add-ObjectBounds {
  param(
    [string]$Type,
    [string]$Id,
    [hashtable]$Bounds,
    [hashtable]$VisitedRelations,
    [System.Collections.Generic.HashSet[string]]$MissingReferences
  )

  if ($Type -eq "node") {
    $node = $nodes[$Id]
    if ($null -eq $node) {
      $MissingReferences.Add("node/$Id") | Out-Null
      return
    }
    Add-NodeBounds $node $Bounds
    return
  }

  if ($Type -eq "way") {
    $way = $ways[$Id]
    if ($null -eq $way) {
      $MissingReferences.Add("way/$Id") | Out-Null
      return
    }
    foreach ($nodeReference in @($way.references)) {
      Add-ObjectBounds "node" ([string]$nodeReference) $Bounds $VisitedRelations $MissingReferences
    }
    return
  }

  if ($VisitedRelations[$Id]) {
    return
  }
  $VisitedRelations[$Id] = $true
  $relation = $relations[$Id]
  if ($null -eq $relation) {
    $MissingReferences.Add("relation/$Id") | Out-Null
    return
  }
  foreach ($member in @($relation.members)) {
    Add-ObjectBounds ([string]$member.type) ([string]$member.id) $Bounds $VisitedRelations $MissingReferences
  }
}

function Get-RepresentativeCoordinates {
  param($SourceCourse)

  $bounds = @{
    minLatitude = [double]::PositiveInfinity
    maxLatitude = [double]::NegativeInfinity
    minLongitude = [double]::PositiveInfinity
    maxLongitude = [double]::NegativeInfinity
  }
  $missingReferences = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
  Add-ObjectBounds $SourceCourse.type ([string]$SourceCourse.id) $bounds @{} $missingReferences
  if ($missingReferences.Count -gt 0) {
    $script:courseObjectsWithMissingGeometryReferences += 1
    foreach ($missingReference in $missingReferences) {
      $script:missingGeometryReferences.Add($missingReference) | Out-Null
    }
  }
  if ([double]::IsInfinity($bounds.minLatitude)) {
    throw "OSM $($SourceCourse.type)/$($SourceCourse.id) has no available geometry coordinates in the source extract."
  }

  return @(
    ($bounds.minLatitude + $bounds.maxLatitude) / 2
    ($bounds.minLongitude + $bounds.maxLongitude) / 2
  )
}

function Get-Tags {
  param([hashtable]$Values)

  $tags = [ordered]@{}
  $names = @($Values.Keys)
  [Array]::Sort($names, [StringComparer]::Ordinal)
  foreach ($name in $names) {
    $tags[$name] = $Values[$name]
  }
  return $tags
}

function Get-Members {
  param($Members)

  return @(
    foreach ($member in @($Members)) {
      [ordered]@{
        type = [string]$member.type
        id = [long]$member.id
        role = [string]$member.role
      }
    }
  )
}

$snapshotTimestamp = (& $toolPath fileinfo -e -g header.option.osmosis_replication_timestamp $inputPath).Trim()
if ($LASTEXITCODE -ne 0 -or -not $snapshotTimestamp) {
  throw "Could not read the source snapshot timestamp with osmium fileinfo."
}
$sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $inputPath).Hash.ToLowerInvariant()
$snapshot = "geofabrik-$SourceIdentifier-$snapshotTimestamp-sha256-$sha256"

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
$writer = [System.IO.StreamWriter]::new($outputPath, $false, $utf8WithoutBom)
try {
  $source = [ordered]@{ kind = "source"; snapshot = $snapshot }
  $writer.WriteLine(($source | ConvertTo-Json -Compress))

  $orderedCourses = @($sourceCourses | Sort-Object @{ Expression = { $_.type } }, @{ Expression = { $_.id } })
  foreach ($sourceCourse in $orderedCourses) {
    $coordinates = Get-RepresentativeCoordinates $sourceCourse
    $members = [object[]]::new(0)
    if ($sourceCourse.type -eq "relation") {
      $members = [object[]](Get-Members $sourceCourse.members)
    }
    $course = [ordered]@{
      type = $sourceCourse.type
      id = $sourceCourse.id
      tags = Get-Tags $sourceCourse.tags
      coordinates = @($coordinates[0], $coordinates[1])
      coordinateSource = if ($sourceCourse.type -eq "node") { "node" } else { "center" }
      members = $members
    }
    $row = [ordered]@{
      kind = "course"
      course = $course
      # Osmium follows OSM references but does not establish geometry containment.
      contained = @()
    }
    $writer.WriteLine(($row | ConvertTo-Json -Compress -Depth 20))
  }
} finally {
  $writer.Dispose()
}

$started.Stop()
$osmiumPeakWorkingSetBytes = $peakWorkingSetBytes
$adapterPeakWorkingSetBytes = [System.Diagnostics.Process]::GetCurrentProcess().PeakWorkingSet64
$peakWorkingSetBytes = [Math]::Max(
  $osmiumPeakWorkingSetBytes,
  $adapterPeakWorkingSetBytes
)

[ordered]@{
  sourceCourseObjects = $sourceCourses.Count
  sourceCourseNodes = @($sourceCourses | Where-Object { $_.type -eq "node" }).Count
  sourceCourseWays = @($sourceCourses | Where-Object { $_.type -eq "way" }).Count
  sourceCourseRelations = @($sourceCourses | Where-Object { $_.type -eq "relation" }).Count
  missingGeometryReferences = $missingGeometryReferences.Count
  courseObjectsWithMissingGeometryReferences = $courseObjectsWithMissingGeometryReferences
  containedOrAssociatedEvidenceObjects = 0
  snapshotTimestamp = $snapshotTimestamp
  sourceSha256 = $sha256
  filteredPbfBytes = (Get-Item -LiteralPath $filteredPath).Length
  exportedXmlBytes = (Get-Item -LiteralPath $xmlPath).Length
  outputJsonlBytes = (Get-Item -LiteralPath $outputPath).Length
  durationMs = $started.Elapsed.TotalMilliseconds
  peakWorkingSetBytes = $peakWorkingSetBytes
  osmiumPeakWorkingSetBytes = $osmiumPeakWorkingSetBytes
  adapterPeakWorkingSetBytes = $adapterPeakWorkingSetBytes
} | ConvertTo-Json -Compress
