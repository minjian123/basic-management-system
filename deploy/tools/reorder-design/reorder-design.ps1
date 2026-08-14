<#
.SYNOPSIS
  设计文档节点编号重排工具（reorder-design）

.DESCRIPTION
  按同目录 order.json 中定义的「阅读顺序」（每个节点的新编号），对架构设计 / 概要设计
  节点做如下处理：
    1. 文件重命名：两步法（先统一改为临时名，再改为目标名），规避编号循环（如 31→07
       与 07→08 同时存在）导致的覆盖冲突；
    2. 全库引用替换：扫描配置的 scanRoots 目录下全部 *.html，将旧文件全名替换为新文件
       全名（带主题的完整文件名，避免误替换），并按旧编号「从后往前」逐个替换，防止
       中间态把新名当旧名再次替换；
    3. 短名导航同步：链接文本中的 {旧编号}-{主题} 短名同步替换为 {新编号}-{主题}，
       与文件全名保持一致；主题短名默认从文件名派生，若文本中带空格（如
       "Webhook 管理"、"AI 能力"），可在 order.json 的节点上配置 short 别名；
    4. 总览 01 节点表行排序：按链接文件名的编号对节点表 <tr> 排序（表头保持最前），
       使总览阅读顺序与文件编号一致；
    5. textReplace 附加文本替换（配置中的固定文案，如"模块注册（38 号）"）。

  幂等：当所有节点文件已处于目标编号（新编号文件存在且无旧编号文件）时，输出
  "已是最新状态"并退出，重复执行安全。

  新增节点后的重排流程：在 order.json 的 nodes 中按阅读顺序插入新节点（name 为不含
  编号的文件名，to 为期望编号），执行本脚本即完成全量重排。

.PARAMETER ConfigPath
  order.json 路径，默认脚本同目录。

.PARAMETER DryRun
  预览模式：只打印重命名计划与替换规则，不执行任何修改。

.EXAMPLE
  .\reorder-design.ps1 -DryRun
  .\reorder-design.ps1
#>
param(
  [string]$ConfigPath = (Join-Path $PSScriptRoot 'order.json'),
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding utf8 | ConvertFrom-Json

function Get-ShortSubject {
  param([string]$Name, [string]$SysName)
  $s = $Name
  if ($s.StartsWith("$SysName`_")) { $s = $s.Substring($SysName.Length + 1) }
  if ($s.StartsWith('子系统_')) { $s = $s.Substring(4) }
  return $s
}

$allMappings = @()
$overviewFiles = @()

foreach ($dirCfg in $config.directories) {
  $dir = Join-Path $repoRoot $dirCfg.dir
  $sysName = $dirCfg.name
  Write-Host "`n==== $($dirCfg.dir) ===="

  $mappings = [System.Collections.Generic.List[object]]::new()
  $inPlace = 0
  foreach ($node in $dirCfg.nodes) {
    $name = $node.name
    $to = [string]$node.to
    $newFileFull = Join-Path $dir "$to`_$name.html"
    $oldFile = Get-ChildItem -LiteralPath $dir -Filter "*_$name.html" |
      Where-Object { $_.BaseName -match '^\d{2}_' -and $_.FullName -ne $newFileFull } |
      Select-Object -First 1
    if (-not $oldFile) {
      if (Test-Path -LiteralPath $newFileFull) { $inPlace++; continue }
      throw "未找到节点文件: $name（$($dirCfg.dir)）"
    }
    $oldNo = ($oldFile.BaseName -split '_')[0]
    $short = if ($node.short) { [string]$node.short } else { Get-ShortSubject -Name $name -SysName $sysName }
    $mappings.Add([pscustomobject]@{
      OldNo    = $oldNo
      NewNo    = $to
      Name     = $name
      OldFile  = $oldFile.FullName
      OldFull  = "$oldNo`_$name.html"
      NewFull  = "$to`_$name.html"
      OldShort = "$oldNo-$short"
      NewShort = "$to-$short"
    })
  }

  # 校验：新编号唯一
  $dupNew = $mappings | Group-Object NewNo | Where-Object { $_.Count -gt 1 }
  if ($dupNew) { throw "新编号冲突: $($dupNew.Name -join ', ')（$($dirCfg.dir)）" }

  # 幂等检测：全部节点已处于目标编号 → 跳过本目录
  if ($inPlace -eq $dirCfg.nodes.Count -and $mappings.Count -eq 0) {
    Write-Host "  已是最新状态（所有节点编号符合 order.json），跳过"
    continue
  }

  # 按旧编号从后往前排序（大编号先替换/先重命名）
  $ordered = $mappings | Sort-Object { [int]$_.OldNo } -Descending

  Write-Host '  重命名计划（旧 → 新）：'
  foreach ($m in $ordered) {
    $mark = if ($m.OldNo -eq $m.NewNo) { '（不变）' } else { '' }
    Write-Host "    $($m.OldFile.Substring($repoRoot.Length + 1)) -> $($m.NewNo)`_$($m.Name).html $mark"
  }

  if (-not $DryRun) {
    # 第一步：全部改为临时名（规避编号环）
    foreach ($m in $mappings) {
      $tmpName = "$($m.OldNo)`_reorder_$($m.Name).html"
      Rename-Item -LiteralPath $m.OldFile -NewName $tmpName
      $m | Add-Member -NotePropertyName TmpFile -NotePropertyValue (Join-Path $dir $tmpName) -Force
    }
    # 第二步：临时名 → 目标名
    foreach ($m in $mappings) {
      Rename-Item -LiteralPath $m.TmpFile -NewName "$($m.NewNo)`_$($m.Name).html"
    }
    Write-Host "  已重命名 $($mappings.Count) 个文件"
  }

  $allMappings += [pscustomobject]@{ Dir = $dirCfg.dir; Ordered = $ordered }
  $overviewFiles += Join-Path $dir "01_$sysName`_总览.html"
}

# ---------- 引用替换 ----------
$scanFiles = @()
foreach ($root in $config.scanRoots) {
  $rootPath = Join-Path $repoRoot $root
  if (Test-Path -LiteralPath $rootPath) {
    $scanFiles += Get-ChildItem -LiteralPath $rootPath -Recurse -Filter *.html
  }
}

if (-not $DryRun) {
  $updatedCount = 0
  foreach ($file in $scanFiles) {
    $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
    $orig = $content
    foreach ($g in $allMappings) {
      foreach ($m in $g.Ordered) {
        $content = $content.Replace($m.OldFull, $m.NewFull)
        $content = $content.Replace($m.OldShort, $m.NewShort)
      }
    }
    foreach ($t in $config.textReplace) {
      $content = $content.Replace([string]$t.from, [string]$t.to)
    }
    if ($content -ne $orig) {
      [System.IO.File]::WriteAllText($file.FullName, $content, (New-Object System.Text.UTF8Encoding($false)))
      $updatedCount++
      Write-Host "  更新引用: $($file.FullName.Substring($repoRoot.Length + 1))"
    }
  }
  Write-Host "`n引用替换完成：更新 $updatedCount / $($scanFiles.Count) 个文件"
} else {
  Write-Host "`n[DryRun] 将扫描 $($scanFiles.Count) 个 html 文件进行引用替换："
  foreach ($g in $allMappings) {
    Write-Host "  $($g.Dir)：$($g.Ordered.Count) 个文件全名 + 短名替换（按旧编号从后往前）"
  }
  foreach ($t in $config.textReplace) {
    Write-Host "  附加文本: `"$($t.from)`" -> `"$($t.to)`""
  }
}

# ---------- 总览 01 节点表行排序 ----------
function Sort-OverviewTables {
  param([string]$Html)
  $tablePattern = '<table(?<attrs>[^>]*)>(?<body>.*?)</table>'
  $evaluator = {
    param($m)
    $attrs = $m.Groups['attrs'].Value
    $body = $m.Groups['body'].Value
    $trs = [regex]::Matches($body, '<tr>.*?</tr>', 'Singleline')
    $header = [System.Collections.Generic.List[string]]::new()
    $nodes = [System.Collections.Generic.List[object]]::new()
    $others = [System.Collections.Generic.List[string]]::new()
    $idx = 0
    foreach ($tr in $trs) {
      if ($tr.Value -match '<th') { $header.Add($tr.Value) }
      elseif ($tr.Value -match 'href="(?<no>\d{2})_') {
        $nodes.Add([pscustomobject]@{ No = [int]$Matches['no']; Html = $tr.Value; Idx = $idx })
      }
      else { $others.Add($tr.Value) }
      $idx++
    }
    $sorted = @($nodes | Sort-Object No, Idx | ForEach-Object { $_.Html })
    return "<table$attrs>" + (@($header) + $sorted + @($others) -join '') + '</table>'
  }
  return [regex]::Replace($Html, $tablePattern, $evaluator, 'Singleline')
}

foreach ($ov in $overviewFiles) {
  if (-not (Test-Path -LiteralPath $ov)) { Write-Warning "未找到总览文件: $ov"; continue }
  $content = [System.IO.File]::ReadAllText($ov, [System.Text.Encoding]::UTF8)
  $sorted = Sort-OverviewTables -Html $content
  if ($sorted -ne $content) {
    if ($DryRun) {
      Write-Host "  [DryRun] 总览表将排序: $($ov.Substring($repoRoot.Length + 1))"
    } else {
      [System.IO.File]::WriteAllText($ov, $sorted, (New-Object System.Text.UTF8Encoding($false)))
      Write-Host "  总览表已排序: $($ov.Substring($repoRoot.Length + 1))"
    }
  }
}

Write-Host '`n完成。'
