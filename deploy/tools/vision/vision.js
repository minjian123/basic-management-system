// vision.js - opencode 通用识图插件
// 提供三个工具：
//   vision_analyze      单图识图分析（调用外部视觉模型 API）
//   vision_screenshot   Edge/Chrome 无头截图（Windows）
//   vision_review_proto 原型视觉评审（多档分辨率截图 + 逐图评审 + 汇总）
//
// 依赖：Python 3（识图客户端）、Edge/Chrome（截图）
// 配置优先级：环境变量 VISION_API_ENDPOINT / VISION_API_KEY / VISION_API_MODEL
//             > opencode.json 插件 options（tuple 形式登记，见 opencode.json）
// 容错：缺配置或子进程异常时工具返回 {ok:false,error} JSON，不影响 opencode 启动。
// 登记：opencode.json plugin 数组加入 ["./deploy/tools/vision/vision.js", {...}]
import { tool } from "@opencode-ai/plugin";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";

const execFileP = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));

function script(name) {
  return join(__dirname, name);
}

function errJson(title, msg) {
  return { title, output: JSON.stringify({ ok: false, error: msg }, null, 2) };
}

export const VisionPlugin = async ({ directory }, options = {}) => {
  const endpoint = process.env.VISION_API_ENDPOINT || options.endpoint || "";
  const apiKey = process.env.VISION_API_KEY || options.apiKey || "";
  const model = process.env.VISION_API_MODEL || options.model || "";
  const timeout = Number(process.env.VISION_API_TIMEOUT || options.timeout || 300000);
  const pyEnv = {
    ...process.env,
    VISION_API_ENDPOINT: endpoint,
    VISION_API_KEY: apiKey,
    VISION_API_MODEL: model,
  };

  const missingCfg = [];
  if (!endpoint) missingCfg.push("VISION_API_ENDPOINT");
  if (!apiKey) missingCfg.push("VISION_API_KEY");
  if (!model) missingCfg.push("VISION_API_MODEL");
  const cfgHint =
    "识图 API 未配置：" + missingCfg.join("、") +
    "。请在系统环境变量或 opencode.json 插件 options（endpoint/apiKey/model）中设置后重启 opencode。";

  const abs = (p) => (p ? resolve(directory, p) : p);
  const toFileUrl = (p) => "file:///" + abs(p).replace(/\\/g, "/");

  async function run(prog, args) {
    const { stdout } = await execFileP(prog, args, {
      timeout,
      maxBuffer: 16 * 1024 * 1024,
      windowsHide: true,
      env: pyEnv,
    });
    return stdout;
  }

  async function screenshot(url, out, width, height, budget) {
    const psArgs = [
      "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script("screenshot.ps1"),
      "-Url", url,
      "-Out", out,
      "-Width", String(width),
      "-Height", String(height),
      "-Budget", String(budget),
    ];
    await run("powershell", psArgs);
  }

  const visionAnalyze = tool({
    description:
      "通用识图：调用外部视觉模型 API 分析本地图片，返回结构化结果。可用于任意图片理解（界面截图、文档图、流程图、图表、对比图等）。配置见 opencode.json 插件 options 或环境变量 VISION_API_*。提示词模板放 deploy/tools/vision/prompts/，新增模板即新增场景。",
    args: {
      image: tool.schema.string().optional().describe("本地图片路径（相对项目根或绝对路径），与 images 二选一"),
      images: tool.schema.string().optional().describe("多张图片路径，逗号分隔，一次调用供模型对比/综合（与 image 二选一）"),
      prompt: tool.schema.string().optional().describe("提示词模板名（prompts/ 目录下，如 prototype-review / general-review）或模板文件路径"),
      text: tool.schema.string().optional().describe("直接提示词文本（与 prompt 二选一）"),
      out: tool.schema.string().optional().describe("结果 JSON 输出路径（可选）"),
    },
    async execute(args) {
      try {
        if (!args.image && !args.images)
          return errJson("识图分析", "必须提供 image 或 images");
        if (missingCfg.length)
          return errJson("识图分析", cfgHint);
        const pyArgs = ["-u", script("vision_analyze.py")];
        if (args.image) pyArgs.push("--image", abs(args.image));
        if (args.images) pyArgs.push("--images", args.images);
        if (args.prompt) pyArgs.push("--prompt", args.prompt);
        if (args.text) pyArgs.push("--text", args.text);
        if (args.out) pyArgs.push("--out", abs(args.out));
        const out = await run("python", pyArgs);
        return { title: "识图分析", output: out };
      } catch (e) {
        return errJson("识图分析", String((e && e.message) || e));
      }
    },
  });

  const visionScreenshot = tool({
    description: "用 Edge/Chrome 无头模式将 HTML 文件或 URL 渲染为 PNG 截图（Windows），不依赖识图 API 配置。",
    args: {
      url: tool.schema.string().describe("HTML 文件路径（相对项目根或绝对路径）或 http(s) URL"),
      out: tool.schema.string().describe("PNG 输出路径（相对项目根或绝对路径）"),
      width: tool.schema.number().optional().describe("窗口宽度，默认 1440"),
      height: tool.schema.number().optional().describe("窗口高度，默认 900"),
      budget: tool.schema.number().optional().describe("渲染等待毫秒数，默认 3000"),
    },
    async execute(args) {
      try {
        const isHttp = /^https?:\/\//i.test(args.url);
        const url = isHttp ? args.url : toFileUrl(args.url);
        const out = abs(args.out);
        await screenshot(url, out, args.width || 1440, args.height || 900, args.budget || 3000);
        return { title: "截图完成", output: "截图已保存: " + out };
      } catch (e) {
        return errJson("截图失败", String((e && e.message) || e));
      }
    },
  });

  const visionReviewProto = tool({
    description:
      "页面视觉评审（通用组合动作）：对指定 HTML/URL 按多档分辨率截图，逐图调用识图 API（默认 prototype-review 模板，可换任意模板），汇总问题清单供修正。用于原型评审、页面走查、移动端评审等。",
    args: {
      target: tool.schema.string().describe("目标页面：HTML 文件路径（相对项目根或绝对路径）或 http(s) URL"),
      template: tool.schema.string().optional().describe("提示词模板名（prompts/ 目录下），默认 prototype-review"),
      sizes: tool.schema.string().optional().describe("分辨率列表，逗号分隔（宽x高），默认 1440x900,1366x768,1024x768"),
      report: tool.schema.string().optional().describe("汇总报告 md 输出路径（可选）"),
    },
    async execute(args) {
      try {
        if (!args.target)
          return errJson("视觉评审", "必须提供 target");
        if (missingCfg.length)
          return errJson("视觉评审", cfgHint);
        const sizes = (args.sizes || "1440x900,1366x768,1024x768").split(",").map((s) => s.trim());
        const template = args.template || "prototype-review";
        const tmpDir = join(directory, "temp", "vision");
        mkdirSync(tmpDir, { recursive: true });
        const base = "p-" + args.target.replace(/[\\/.]/g, "_").replace(/^_+/, "").slice(0, 40);

        const blocks = [];
        for (const size of sizes) {
          const [w, h] = size.split("x");
          const png = join(tmpDir, base + "-" + w + "x" + h + ".png");
          const isHttp = /^https?:\/\//i.test(args.target);
          await screenshot(isHttp ? args.target : toFileUrl(args.target), png, Number(w), Number(h), 3000);
          const pyArgs = ["-u", script("vision_analyze.py"), "--image", png, "--prompt", template];
          const out = await run("python", pyArgs);
          blocks.push("### " + size + "\n\n" + out);
        }
        const summary = blocks.join("\n\n");

        if (args.report) {
          const reportPath = abs(args.report);
          mkdirSync(dirname(reportPath), { recursive: true });
          writeFileSync(reportPath, "# 页面视觉评审：" + args.target + "\n\n" + summary, "utf-8");
          return { title: "视觉评审完成", output: "完成 " + sizes.length + " 档截图评审\n报告: " + reportPath + "\n\n" + summary };
        }
        return { title: "视觉评审完成", output: "完成 " + sizes.length + " 档截图评审\n\n" + summary };
      } catch (e) {
        return errJson("视觉评审失败", String((e && e.message) || e));
      }
    },
  });

  return {
    tool: {
      vision_analyze: visionAnalyze,
      vision_screenshot: visionScreenshot,
      vision_review_proto: visionReviewProto,
    },
  };
};
