# 在 mjw（Windows）上拉起 LM Studio 的 OpenAI 兼容服务并加载识图模型
# 由 mjbk 的模型代理经「mjbk -> mjpc(SSH) -> WinRM -> mjw」链路调用：
#   ~/tools/winrm-venv/bin/python <repo>/scripts/tools/winrm/pwsh_mjw.py --file <本文件>
# 注意：必须 --bind 0.0.0.0，否则服务只监听 127.0.0.1，mjbk 无法访问。
$ErrorActionPreference = "Continue"
$lms = "$env:USERPROFILE\.lmstudio\bin\lms.exe"

Write-Output "重启 LM Studio 服务（绑定 0.0.0.0:1234）..."
& $lms server stop 2>$null
Start-Sleep -Seconds 2
& $lms server start --bind 0.0.0.0 --port 1234

Write-Output "加载模型 qwen3-vl-8b-instruct-abliterated-v2 ..."
& $lms load qwen3-vl-8b-instruct-abliterated-v2 --gpu max -c 32768 -y

Write-Output "服务状态："
& $lms server status
