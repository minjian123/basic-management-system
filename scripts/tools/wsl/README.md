# 说明：本目录存放 WSL 相关辅助脚本（开发机 mjpc：Windows 侧）
#
# 目录内容
#   挂载Ubuntu盘.py    把双系统 Ubuntu 的数据盘（磁盘 3 分区 2，ext4）以只读方式挂进 WSL；
#                      同名 .bat 为双击薄包装（需管理员）
#
# 背景与完整说明见 bms 文档《WSL 部署使用说明》：
#   bms文档/资料/开发机/WSL部署使用说明.md
#
# 关键约束（改动脚本时务必遵守）
#   1. 挂物理盘需管理员权限（wsl --mount）：桌面快捷方式「挂载 Ubuntu 盘」已勾「以管理员身份运行」。
#   2. 一律只读挂载（--options ro）：目的只是读文件，避免在 Windows 侧误写损坏双系统 Linux。
#   3. 挂载在 Windows 重启 / wsl --shutdown 后失效，需要时重跑本脚本（脚本幂等，已挂载则只校验）。
#   4. 磁盘整盘挂给 WSL 期间，Windows 访问不到该盘的任何分区（含 ESP）：要动 ESP 先 --
#      wsl --unmount \\\\.\PHYSICALDRIVE3。
