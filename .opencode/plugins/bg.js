// bg.js - opencode 后台任务插件（启动即返回，秒级查状态）
// 提供三个工具：
//   bg_run     后台执行任意命令（立即返回 PID，日志落盘）
//   bg_status  秒级查询任务状态（运行中/已完成 + 输出尾部）
//   bg_wait    阻塞等待任务到终态（带超时上限），输出最终状态与日志尾部
//   gl_watch_pipeline  GitLab 流水线盯守（内部走 bg 链路，到终态返回结果）
//   bg_stop    停止后台任务
//
// 原理：命令经 python 后台运行，立即返回；状态查询读状态文件与进程存活，
// 彻底避免"命令卡住傻等"。适合下载、构建、ssh 远程、安装等长耗时操作。
// 登记：opencode.json plugin 数组加入 "plugins/bg.js"。
import { tool } from "@opencode-ai/plugin";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const execFileP = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));

function script(name) {
  // python 脚本在 scripts/bg/（插件文件位于 .opencode/plugins/，向上两级到项目根）
  return join(__dirname, "..", "..", "scripts", "bg", name);
}

function gitlabScript(name) {
  // GitLab 流水线盯守脚本在 scripts/gitlab/
  return join(__dirname, "..", "..", "scripts", "gitlab", name);
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

      bg_wait: tool({
        description:
          "阻塞等待指定后台任务到终态（FINISHED），输出最终状态与日志尾部；超时输出 BG_WAIT_TIMEOUT。" +
          "适合发起 bg_run 后需要拿到结果再继续的场景。",
        args: {
          name: tool.schema.string().describe("任务名（bg_run 时指定的 name）"),
          timeout: tool.schema.number().optional().describe("等待上限秒数（默认 600）"),
          interval: tool.schema.number().optional().describe("轮询间隔秒数（默认 5）"),
          tail: tool.schema.number().optional().describe("终态时输出的日志尾部行数（默认 8）"),
        },
        async execute(args) {
          try {
            if (!args.name)
              return { title: "bg_wait", output: JSON.stringify({ ok: false, error: "name 必填" }, null, 2) };
            const psArgs = ["--name", args.name];
            const waitSec = args.timeout ?? 600;
            if (args.timeout) psArgs.push("--timeout", String(args.timeout));
            if (args.interval) psArgs.push("--interval", String(args.interval));
            if (args.tail) psArgs.push("--tail", String(args.tail));
            // 阻塞等待可能超过默认 30s，按等待上限动态放宽进程超时（+15s 余量）
            const { stdout } = await execFileP("python", ["-u", script("bg-wait.py"), ...psArgs], {
              timeout: waitSec * 1000 + 15000,
              maxBuffer: 4 * 1024 * 1024,
              windowsHide: true,
            });
            return { title: "后台任务已结束", output: stdout.trim() };
          } catch (e) {
            return { title: "bg_wait", output: JSON.stringify({ ok: false, error: String((e && e.message) || e) }, null, 2) };
          }
        },
      }),

      gl_watch_pipeline: tool({
        description:
          "GitLab 流水线盯守：内部经 bg 链路后台运行 watch_pipeline.py 并等待到终态，" +
          "返回 success/failed/canceled 与流水线链接。凭据自动读 deploy/.env 的 GITLAB_API_*。",
        args: {
          pipeline_id: tool.schema.number().describe("流水线 ID"),
          project: tool.schema.number().optional().describe("项目 ID（默认 2 = bms/bms）"),
          timeout: tool.schema.number().optional().describe("盯守上限秒数（默认 600）"),
          interval: tool.schema.number().optional().describe("轮询间隔秒数（默认 15）"),
          name: tool.schema.string().optional().describe("bg 任务名（默认自动生成）"),
        },
        async execute(args) {
          if (!args.pipeline_id)
            return { title: "gl_watch_pipeline", output: JSON.stringify({ ok: false, error: "pipeline_id 必填" }, null, 2) };
          const taskName = args.name || `glpipe_${args.pipeline_id}_${Date.now()}`;
          const waitSec = (args.timeout ?? 600) + 30;
          try {
            // 1) 经 bg_run 后台启动盯守脚本（命令经 pwsh 执行）
            const cmdParts = [`python -u "${gitlabScript("watch_pipeline.py")}" --pipeline-id ${args.pipeline_id}`];
            if (args.project) cmdParts.push("--project", String(args.project));
            if (args.timeout) cmdParts.push("--timeout", String(args.timeout));
            if (args.interval) cmdParts.push("--interval", String(args.interval));
            await runPy("bg-run.py", ["--name", taskName, "--command", cmdParts.join(" "), "--timeout", String(waitSec)]);
            // 2) 经 bg_wait 阻塞到终态（+30s 余量防误杀），非零退出码时取 stdout
            let out;
            try {
              out = await execFileP("python", ["-u", script("bg-wait.py"), "--name", taskName, "--timeout", String(waitSec), "--tail", "20"], {
                timeout: waitSec * 1000 + 15000,
                maxBuffer: 4 * 1024 * 1024,
                windowsHide: true,
              });
              out = out.stdout.trim();
            } catch (e) {
              out = [e.stdout?.trim(), e.stderr?.trim()].filter(Boolean).join("\n") || String((e && e.message) || e);
            }
            return { title: "流水线盯守结束", output: `任务名 ${taskName}\n${out}` };
          } catch (e) {
            return { title: "gl_watch_pipeline", output: JSON.stringify({ ok: false, error: String((e && e.message) || e) }, null, 2) };
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
