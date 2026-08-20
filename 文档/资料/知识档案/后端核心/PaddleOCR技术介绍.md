# PaddleOCR 技术介绍

> 光学字符识别 · BMS 扫描件文字识别

[文档首页](../../../文档首页.html) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › PaddleOCR 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**PaddleOCR** 是百度飞桨（PaddlePaddle）团队开源的 **OCR（光学字符识别）工具套件**：
从图片、扫描件里把文字「认」出来，中文识别能力在开源方案里属于第一梯队，
除文字识别外还提供文档版面分析、表格识别、公式识别（PP-Structure 系列）。
BMS 用它做扫描件的文字识别（阶段十五），让扫描件里的内容也能被全文检索和语义检索命中。

- **定位**：BMS 阶段十五「OCR 与文件自动分类」能力的默认本地识别引擎，可切换多模态模型 API。
- **版本**：3.x 系列（截至 2026.8 最新 3.7.0，2026.6 发布；含 PP-OCRv5/v6 模型系列）。
- **许可**：Apache-2.0，OSI 认证开源，无合规顾虑。
- **生态**：基于 PaddlePaddle 深度学习框架推理；`pip install paddleocr` 即可用，也支持服务化部署（HTTP API）。
- **部署**：本地 CPU/GPU 推理（《[开发部署规划](../../../规划/开发部署规划.html)》第五批，按需本地部署，可选）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| OCR | 光学字符识别：从图片/扫描件中识别出文字，让「图里的字」变成可搜索的文本 |
| 文字检测（Det） | OCR 第一步：找出图片里文字的位置（画框），输出每个文本行的坐标 |
| 文字识别（Rec） | OCR 第二步：把检测出的每个文本行认成文字内容，输出文本 |
| PP-OCR 系列 | PaddleOCR 的通用文字识别模型系列（v4/v5/v6 逐代演进），覆盖简中、繁中、英文、日文等多语种 |
| PP-Structure | 文档结构分析：版面检测、表格识别、公式识别，把整页文档解析成结构化结果（Markdown/JSON） |
| PaddlePaddle（飞桨） | 百度开源的深度学习框架，PaddleOCR 的推理引擎；3.x 版本要求飞桨 3.0+ |
| 推理（Inference） | 用训练好的模型跑输入、出结果（区别于「训练」）；BMS 只做推理，不训练模型 |
| CPU / GPU 推理 | CPU 通用但慢，GPU（CUDA）快；BMS MVP 走 CPU，量大时再评估 GPU |
| 模型档位（mobile / server） | 小模型（mobile，快、省资源）与大模型（server，精度更高）两档，按精度/速度需求选 |
| 服务化部署 | PaddleOCR 支持把识别能力跑成 HTTP 服务，客户端用任意语言调用；BMS 也可进程内直接调用 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **扫描件文字识别**（阶段十五）：PDF 扫描件/图片 → OCR 提取文本 → 文本落库并进 ElasticSearch 索引（文件内容检索）、向量化进 Milvus（语义检索），扫描件从此「搜得到、问得了」。
- **与文件检索结合**：OCR 是文件内容检索链路对扫描件的支持环节——可解析格式（PDF/Word/Excel/TXT）直接解析文本，扫描件走 OCR（见《[ElasticSearch 技术介绍](ElasticSearch技术介绍.md)》第 3 节）。
- **与 AI 能力结合**：「OCR 与文件自动分类」是八项 AI 能力之一（见《[LLM 适配层技术介绍](LLM适配层技术介绍.md)》）；默认本地 PaddleOCR，复杂场景可切换多模态模型 API（规划 3.1 节）。
- **异步执行**：识别耗时（CPU 下大文档可达数十秒），走 Celery 任务异步处理，不阻塞业务接口（见《[Celery 技术介绍](Celery技术介绍.md)》）。
- **数据安全**：本地推理，文档内容不出机器，符合敏感场景要求；许可 Apache-2.0 无合规风险。

```python
# 安装（国内镜像源）
# python -m pip install paddlepaddle -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
# python -m pip install paddleocr

from paddleocr import PaddleOCR

ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
result = ocr.predict("scan.pdf")
for page in result:
    print(page["rec_texts"])  # 识别出的文本行列表
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| **PaddleOCR（选中）** | Apache-2.0、中文识别强、本地部署数据不出机器、模型档位全、文档解析能力齐 | 依赖飞桨框架，安装体积较大 | 本地 + 中文 + 私有化三要求全满足 |
| Tesseract | 老牌开源、部署轻 | 中文识别弱、版面/表格分析弱、迭代慢 | 不采用 |
| 商业 OCR API（云厂商） | 精度高、免部署 | 数据出云，与私有化要求冲突；按量计费 | 作为「多模态模型 API 可切换」的备选路径，不作默认 |
| 多模态大模型（如 Qwen-VL 类） | 文档理解能力强，复杂版面/公式更好 | 成本高、速度慢，本地部署硬件要求高 | 复杂场景的可切换选项，不作默认 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **安装体积大**：paddleocr + paddlepaddle 依赖不小，务必在独立虚拟环境安装，pip 走国内镜像源（飞桨官方源或清华/阿里源）。
- **CPU 推理慢**：大文档识别耗时可达数十秒，必须走 Celery 异步任务 + 进度反馈，严禁在接口内同步调用。
- **模型预下载**：首次运行会自动下载模型文件，内网/离线环境要提前在可联网机器下载好模型包再部署，别等运行时才发现拉不下来。
- **扫描件质量决定效果**：倾斜、模糊、低分辨率的扫描件识别率明显下降；必要时加预处理（纠偏、二值化），验收时按真实扫描件测，别只用清晰样图。
- **版本 API 差异**：3.x 与 2.x 调用方式不同（3.x 用 `predict()`），锁定版本并对照对应版本文档写代码，升级前跑回归。
- **资源隔离**：识别任务吃 CPU/内存，生产环境限制并发数或独立容器运行，避免与主业务抢资源。
- **结果要落审计**：OCR 处理记录（文件、耗时、文本量）纳入任务日志，配合 `ai_chat_log` 与文件检索链路可追溯。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| PaddleOCR 官网（中文文档） | https://www.paddleocr.ai/ | 安装、使用、模型说明权威入口 |
| PaddleOCR 快速开始 | https://www.paddleocr.ai/main/quick_start.html | 安装 + 命令行/Python 上手 |
| PaddleOCR GitHub | https://github.com/PaddlePaddle/PaddleOCR | 源码、版本发布记录与 issue |
| PaddlePaddle 官网 | https://www.paddlepaddle.org.cn/ | 推理引擎（飞桨）安装与框架文档 |
| PaddleOCR 码云镜像 | https://gitee.com/paddlepaddle/PaddleOCR | 国内克隆源码的备用仓库 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.html#stack-backend)》2.1 节 | 后端技术栈：AI（阶段十五）条目 |
| 《[项目规划说明](../../../规划/项目规划说明.html#sel-backend)》3.1 节 | OCR 默认本地 PaddleOCR、可切换多模态 API 的选型说明 |
| 《[项目规划说明](../../../规划/项目规划说明.html#plan)》20 节 | 阶段十五「AI 能力」验收标准（含 OCR 与文件自动分类） |
| 《[LLM 适配层技术介绍](LLM适配层技术介绍.md)》 | OCR 与文件自动分类能力、多模态 API 切换 |
| 《[ElasticSearch 技术介绍](ElasticSearch技术介绍.md)》 | OCR 文本进文件内容检索索引 |
| 《[Milvus 技术介绍](Milvus技术介绍.md)》 | OCR 文本向量化进语义检索 |
| 《[Celery 技术介绍](Celery技术介绍.md)》 | OCR 异步任务执行 |
| 《[MinIO 技术介绍](MinIO技术介绍.md)》 | 扫描件文件的存储来源 |
| 《[开发部署规划](../../../规划/开发部署规划.html)》 | 第五批：PaddleOCR 按需本地部署（可选） |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.html)》编写 · 生成日期：2026-08-19