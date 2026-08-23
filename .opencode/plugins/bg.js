// bg.js - opencode 后台任务插件（启动即返回，秒级查状态）
// 提供三个工具：
//   bg_run     后台执行任意命令（立即返回 PID，日志落盘）
//   bg_status  秒级查询任务状态（运行中/已完成 + 输出尾部）
//   bg_stop    停止后台任务
//
// 原理：命令经 python 后台运行，立即返回；状态查询读状态文件与进程存活，
// 彻底避免"命令卡住傻等"。适合下载、构建、ssh 远程、安装等长耗时操作。
// 登记：opencode.json plugin 数组加入 "./deploy/tools/bg/bg.js"。
import { tool } from "@opencode-ai/plugin";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));

function script(name) {
  // python 脚本仍在 deploy/tools/bg/（插件文件位于 .opencode/plugins/，向上两级到项目根）
  return join(__dirname, "..", "..", "deploy", "tools", "bg", name);
}

async function runPy(name, args) {
  const { stdout } = await execFileP("python", ["-u", script(name), ...args], {
    timeout: 30000,
    maxBuffer: 4 * 1024 * 1024,
    windowsHide: true,
  });
  return stdout.trim();
}

export const BgPlugin = async ({ directory }) => {
  return {
    tool: {
      bg_run: tool({
        description:
          "后台执行任意命令：立即返回任务 ID，不等待命令结束（适合下载/构建/ssh/安装等长操作）。" +
          "之后用 bg_status 秒级查询结果。状态文件默认 %USERPROFILE%\\.bg。",
        args: {
          name: tool.schema.string().describe("任务名（唯一标识，查询/停止时使用）"),
          command: tool.schema.string().describe("要执行的命令（如 pnpm install、ssh user@host df -h、git pull）"),
          workdir: tool.schema.string().optional().describe("工作目录（默认当前项目根）"),
          timeout: tool.schema.number().optional().describe("命令超时秒数（0=不限，默认 0）"),
        },
        async execute(args) {
          try {
            if (!args.name || !args.command)
              return { title: "bg_run", output: JSON.stringify({ ok: false, error: "name 与 command 必填" }, null, 2) };
            const psArgs = ["--name", args.name, "--command", args.command];
            if (args.workdir) psArgs.push("--workdir", args.workdir);
            if (args.timeout) psArgs.push("--timeout", String(args.timeout));
            const out = await runPy("bg-run.py", psArgs);
            return { title: "后台任务已启动", output: out };
          } catch (e) {
            return { title: "bg_run", output: JSON.stringify({ ok: false, error: String((e && e.message) || e) }, null, 2) };
          }
        },
      }),

      bg_status: tool({
        description: "秒级查询后台任务状态：运行中（运行秒数 + 输出尾部）或已完成（输出尾部 + stderr）。",
        args: {
          name: tool.schema.string().describe("任务名（bg_run 时指定的 name）"),
        },
        async execute(args) {
          try {
            if (!args.name)
              return { title: "bg_status", output: JSON.stringify({ ok: false, error: "name 必填" }, null, 2) };
            const out = await runPy("bg-status.py", ["--name", args.name]);
            return { title: "后台任务状态", output: out };
          } catch (e) {
            return { title: "bg_status", output: JSON.stringify({ ok: false, error: String((e && e.message) || e) }, null, 2) };
          }
        },
      }),

      bg_stop: tool({
        description: "停止后台任务（按名称查状态文件后杀进程）。",
        args: {
          name: tool.schema.string().describe("任务名（bg_run 时指定的 name）"),
        },
        async execute(args) {
          try {
            if (!args.name)
              return { title: "bg_stop", output: JSON.stringify({ ok: false, error: "name 必填" }, null, 2) };
            const out = await runPy("bg-stop.py", ["--name", args.name]);
            return { title: "后台任务已停止", output: out };
          } catch (e) {
            return { title: "bg_stop", output: JSON.stringify({ ok: false, error: String((e && e.message) || e) }, null, 2) };
          }
        },
      }),
    },
  };
};
