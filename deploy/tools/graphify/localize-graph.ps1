# graphify 图谱产物一键收尾脚本
# 用法：每次 graphify update --force . 重建图谱后运行本脚本，完成两件事：
#   1. 汉化 graph.html 界面文案（英文 -> 中文，幂等可反复执行）
#   2. 生成中文界面的架构流程图 graphify-out/CALLFLOW.html（graphify export callflow-html --lang zh-CN）
#   powershell -File deploy/tools/graphify/localize-graph.ps1
param(
    [string]$GraphHtml = "graphify-out/graph.html",
    [string]$CallFlowOutput = "graphify-out/CALLFLOW.html",
    [switch]$SkipCallFlow
)

if (-not (Test-Path $GraphHtml)) {
    Write-Error "未找到 $GraphHtml，请先在项目根目录执行 graphify update --force . 生成图谱"
    exit 1
}

# ---- 1. 汉化 graph.html ----
$html = Get-Content $GraphHtml -Raw -Encoding UTF8
$already = $html -match "搜索节点"

$replacements = [ordered]@{
    '<html lang="en">' = '<html lang="zh-CN">'
    '<title>graphify - graphify-out/graph.html</title>' = '<title>知识图谱 - BMS</title>'
    'placeholder="Search nodes..."' = 'placeholder="搜索节点..."'
    '<h3>Node Info</h3>' = '<h3>节点信息</h3>'
    'Click a node to inspect it' = '点击节点查看详情'
    '<h3>Communities</h3>' = '<h3>社区</h3>'
    '>Select All<' = '>全选<'
}

foreach ($key in $replacements.Keys) {
    if ($html.Contains($key)) {
        $html = $html.Replace($key, $replacements[$key])
    }
}

# 底部统计行：数字动态，用正则替换
$html = [regex]::Replace($html, '(\d+) nodes &middot; (\d+) edges &middot; (\d+) communities', '$1 节点 · $2 关系 · $3 社区')

if (-not $already) {
    Set-Content $GraphHtml -Value $html -Encoding UTF8 -NoNewline
    Write-Host "已汉化: $GraphHtml"
} else {
    Write-Host "已汉化过（幂等跳过）: $GraphHtml"
}

# ---- 2. 生成中文 callflow 架构图 ----
if (-not $SkipCallFlow) {
    graphify export callflow-html --lang zh-CN --output $CallFlowOutput 2>&1 | Select-Object -Last 3
    if (Test-Path $CallFlowOutput) {
        Write-Host "已生成中文架构图: $CallFlowOutput"
    } else {
        Write-Warning "callflow-html 生成失败，请检查 graphify export callflow-html --help"
    }
}
