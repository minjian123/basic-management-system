<#
.SYNOPSIS
  设计文档节点编号重排工具（reorder-design）

.DESCRIPTION
  按同目录 order.json 中定义的「阅读顺序」（每个节点的新编号），对设计文档体系做编号重排。
  支持两种体系类型（directories[].type）：

  - "single"：单级编号文档（架构设计 / 概要设计 / 布局设计）
      文件形如 {NN}_{体系}_{主题}.html，order.json 的 nodes 定义阅读顺序（新编号）。
  - "proto"：原型设计（两级编号）
      模块文件夹 {NN}_{模块名}/ + 模块内文件 {NN}_{文件名}.html。
      order.json 的 modules 定义模块阅读顺序（新编号），moduleFiles 按模块名配置
      模块内文件阅读顺序（可省略，省略则模块内文件不重排）。

  处理内容：
    1. 文件/文件夹重命名：两步法（先统一改为临时名，再改为目标名），规避编号循环
       导致的覆盖冲突；
    2. 全库引用替换：扫描 scanRoots 目录下全部 *.html，按「旧编号从后往前」的顺序
       逐个替换文件全名 / 文件夹路径段 / 无斜杠文字变体 / 模块内文件名，防止中间态
       把新名当旧名再次替换；
    3. 总览 01 节点表行排序：按链接文件名的编号对节点表 <tr> 排序（表头保持最前），
       使总览阅读顺序与文件编号一致；
    4. textReplace 附加文本替换（配置中的固定文案）。

  幂等：当所有节点已处于目标编号（目标文件存在且无旧编号文件）时，输出
  "已是最新状态"并跳过，重复执行安全。

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

# 全局替换对集合：@{ Old; New; Key }（Key 为旧编号，替换时按 Key 降序执行）
$allPairs = [System.Collections.Generic.List[object]]::new()
$overviewFiles = @()

foreach ($dirCfg in $config.directories) {
  $dir = Join-Path $repoRoot $dirCfg.dir
  $type = if ($dirCfg.type) { [string]$dirCfg.type } else { 'single' }
  Write-Host "`n==== $($dirCfg.dir)（$type） ===="

  if ($type -eq 'single') {
    # ---------- 单级编号：架构/概要/布局 ----------
    $sysName = $dirCfg.name
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
    $dupNew = $mappings | Group-Object NewNo | Where-Object { $_.Count -gt 1 }
    if ($dupNew) { throw "新编号冲突: $($dupNew.Name -join ', ')（$($dirCfg.dir)）" }
    $overviewFiles += Join-Path $dir "01_$sysName`_总览.html"
    if ($inPlace -eq $dirCfg.nodes.Count -and $mappings.Count -eq 0) {
      Write-Host '  已是最新状态（所有节点编号符合 order.json），跳过'
      continue
    }
    $ordered = $mappings | Sort-Object { [int]$_.OldNo } -Descending
    Write-Host '  重命名计划（旧 → 新）：'
    foreach ($m in $ordered) {
      $mark = if ($m.OldNo -eq $m.NewNo) { '（不变）' } else { '' }
      Write-Host "    $($m.OldFile.Substring($repoRoot.Length + 1)) -> $($m.NewNo)`_$($m.Name).html $mark"
    }
    if (-not $DryRun) {
      foreach ($m in $mappings) {
        $tmpName = "$($m.OldNo)`_reorder_$($m.Name).html"
        Rename-Item -LiteralPath $m.OldFile -NewName $tmpName
        $m | Add-Member -NotePropertyName TmpFile -NotePropertyValue (Join-Path $dir $tmpName) -Force
      }
      foreach ($m in $mappings) {
        Rename-Item -LiteralPath $m.TmpFile -NewName "$($m.NewNo)`_$($m.Name).html"
      }
      Write-Host "  已重命名 $($mappings.Count) 个文件"
    }
    foreach ($m in $ordered) {
      $allPairs.Add([pscustomobject]@{ Old = $m.OldFull; New = $m.NewFull; Key = [int]$m.OldNo })
      $allPairs.Add([pscustomobject]@{ Old = $m.OldShort; New = $m.NewShort; Key = [int]$m.OldNo })
    }
  }
  else {
    # ---------- 原型设计：模块文件夹 + 模块内文件 两级 ----------
    $moduleMappings = [System.Collections.Generic.List[object]]::new()
    $inPlace = 0
    foreach ($mod in $dirCfg.modules) {
      $mname = $mod.name
      $to = [string]$mod.to
      $oldDir = Get-ChildItem -LiteralPath $dir -Directory |
        Where-Object { $_.Name -match '^\d{2}_' -and $_.Name -like "*_$mname" -and $_.Name -ne "$to`_$mname" } |
        Select-Object -First 1
      if (-not $oldDir) {
        if (Test-Path -LiteralPath (Join-Path $dir "$to`_$mname")) { $inPlace++; continue }
        Write-Host "  新增模块（文件夹未创建，按目标编号 $to 直接创建即可）: $mname"
        continue
      }
      $oldNo = ($oldDir.Name -split '_')[0]
      $moduleMappings.Add([pscustomobject]@{
        OldNo   = $oldNo
        NewNo   = $to
        Name    = $mname
        OldDir  = $oldDir.FullName
        OldSeg  = "$oldNo`_$mname/"
        NewSeg  = "$to`_$mname/"
        OldTxt  = "$oldNo`_$mname"
        NewTxt  = "$to`_$mname"
        TmpDir  = $null
        FileMappings = [System.Collections.Generic.List[object]]::new()
      })
    }
    $dupNew = $moduleMappings | Group-Object NewNo | Where-Object { $_.Count -gt 1 }
    if ($dupNew) { throw "模块新编号冲突: $($dupNew.Name -join ', ')（$($dirCfg.dir)）" }
    $overviewFiles += Join-Path $dir '01_原型设计_总览.html'
    if ($inPlace -eq $dirCfg.modules.Count -and $moduleMappings.Count -eq 0) {
      Write-Host '  已是最新状态（所有模块编号符合 order.json），跳过'
      continue
    }
    $orderedMods = $moduleMappings | Sort-Object { [int]$_.OldNo } -Descending

    # 模块内文件映射（moduleFiles 配置的模块）
    foreach ($m in $moduleMappings) {
      $fmCfg = @($dirCfg.moduleFiles | Where-Object { $_.name -eq $m.Name })
      if ($fmCfg.Count -eq 0) { continue }
      foreach ($fnode in $fmCfg[0].files) {
        $fname = $fnode.name
        $fto = [string]$fnode.to
        $fdir = $m.OldDir
        if (Test-Path -LiteralPath $fdir) {
          $oldFile = Get-ChildItem -LiteralPath $fdir -Filter "*_$fname.html" |
            Where-Object { $_.BaseName -match '^\d{2}_' -and $_.FullName -ne (Join-Path $fdir "$fto`_$fname.html") } |
            Select-Object -First 1
          if (-not $oldFile) {
            if (Test-Path -LiteralPath (Join-Path $fdir "$fto`_$fname.html")) { continue }
            Write-Host "      新增界面文件（未创建，按目标编号 $fto 直接创建即可）: $($m.Name)/$fname"
            continue
          }
          $foldNo = ($oldFile.BaseName -split '_')[0]
          $m.FileMappings.Add([pscustomobject]@{
            OldNo   = $foldNo
            NewNo   = $fto
            Name    = $fname
            OldFile = $oldFile.FullName
            OldFull = "$foldNo`_$fname.html"
            NewFull = "$fto`_$fname.html"
          })
        }
      }
    }

    Write-Host '  模块文件夹重命名计划（旧 → 新）：'
    foreach ($m in $orderedMods) {
      $mark = if ($m.OldNo -eq $m.NewNo) { '（不变）' } else { '' }
      Write-Host "    $($m.OldDir.Substring($repoRoot.Length + 1)) -> $($m.NewNo)`_$($m.Name)/ $mark"
      foreach ($fm in $m.FileMappings) {
        Write-Host "      模块内文件: $($fm.OldFull) -> $($fm.NewFull)"
      }
    }
    if (-not $DryRun) {
      # 第一步：模块文件夹与模块内文件全部改临时名
      foreach ($m in $moduleMappings) {
        $tmpDir = Join-Path $dir "$($m.OldNo)`_reorder_$($m.Name)"
        Rename-Item -LiteralPath $m.OldDir -NewName (Split-Path $tmpDir -Leaf)
        $m.TmpDir = $tmpDir
        # 文件夹已改名，模块内文件路径同步更新到临时目录
        foreach ($fm in $m.FileMappings) {
          $fm.OldFile = Join-Path $tmpDir (Split-Path $fm.OldFile -Leaf)
        }
      }
      foreach ($m in $moduleMappings) {
        foreach ($fm in $m.FileMappings) {
          $tmpName = "$($fm.OldNo)`_reorder_$($fm.Name).html"
          Rename-Item -LiteralPath $fm.OldFile -NewName $tmpName
          $fm | Add-Member -NotePropertyName TmpFile -NotePropertyValue (Join-Path $m.TmpDir $tmpName) -Force
        }
      }
      # 第二步：临时名 → 目标名
      foreach ($m in $moduleMappings) {
        $targetDir = Join-Path $dir "$($m.NewNo)`_$($m.Name)"
        Rename-Item -LiteralPath $m.TmpDir -NewName (Split-Path $targetDir -Leaf)
        # 文件夹已改目标名，模块内文件路径同步更新到目标目录并改为目标名
        foreach ($fm in $m.FileMappings) {
          $fm.TmpFile = Join-Path $targetDir (Split-Path $fm.TmpFile -Leaf)
          Rename-Item -LiteralPath $fm.TmpFile -NewName "$($fm.NewNo)`_$($fm.Name).html"
        }
      }
      Write-Host "  已重命名 $($moduleMappings.Count) 个模块文件夹（含模块内文件）"
    }
    foreach ($m in $orderedMods) {
      $key = [int]$m.OldNo
      $allPairs.Add([pscustomobject]@{ Old = $m.OldSeg; New = $m.NewSeg; Key = $key })
      $allPairs.Add([pscustomobject]@{ Old = $m.OldTxt; New = $m.NewTxt; Key = $key })
      foreach ($fm in $m.FileMappings) {
        $allPairs.Add([pscustomobject]@{ Old = $fm.OldFull; New = $fm.NewFull; Key = $key })
      }
    }
  }
}

# ---------- 引用替换 ----------
$scanFiles = @()
foreach ($root in $config.scanRoots) {
  $rootPath = Join-Path $repoRoot $root
  if (Test-Path -LiteralPath $rootPath) {
    $scanFiles += Get-ChildItem -LiteralPath $rootPath -Recurse -Filter *.html
  }
}

# 替换顺序：按旧编号 Key 从后往前（降序），同 Key 保持添加顺序（先全名/路径段，后文字变体）
$orderedPairs = @($allPairs | Sort-Object @{ Expression = { $_.Key }; Descending = $true }, @{ Expression = { [array]::IndexOf($allPairs, $_) } })

if (-not $DryRun) {
  $updatedCount = 0
  foreach ($file in $scanFiles) {
    $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
    $orig = $content
    foreach ($p in $orderedPairs) {
      $content = $content.Replace($p.Old, $p.New)
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
  Write-Host "`n[DryRun] 将扫描 $($scanFiles.Count) 个 html 文件进行引用替换：$($orderedPairs.Count) 对全名/路径段替换（按旧编号从后往前）"
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
    $sorted = @($nodes | Sort-Object No, Idx | ForEach-Object {
        $html = $_.Html
        # 同步行首纯数字编号列（如原型模块地图 <td>NN</td>），与 href 编号保持一致
        $leadTd = [regex]::Match($html, '(?s)^<tr>\s*<td[^>]*>\s*\d{2}\s*</td>')
        if ($leadTd.Success) {
          $num = '{0:d2}' -f $_.No
          $html = "<tr><td>$num</td>" + $html.Substring($leadTd.Length)
        }
        $html
      })
    $sep = "`n        "
    return "<table$attrs>" + $sep + (@($header) + $sorted + @($others) -join $sep) + "`n      </table>"
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
