# LabWeft · 科研工作台

**让你已有的 coding agent 整理研究，而不是每次重新解释整个项目。**

[English](README.md) · [架构](docs/ARCHITECTURE.zh-CN.md) · [已知边界](docs/LIMITATIONS.zh-CN.md) · [发布门槛](docs/RELEASE_GATES.zh-CN.md) · [开发交接](docs/HANDOFF.zh-CN.md)

LabWeft 是已确认的项目名；当前是 `0.1.0` 本地原型，尚未达到 ClearML 的成熟度。源码仓库是 [Roboparty/LabWeft](https://github.com/Roboparty/LabWeft)；尚未发布到 PyPI。

## 它既有 Skill，也是一套 harness

Skill 是对话入口：让 Codex、Claude Code 等宿主知道何时、怎样使用。
Harness 是底层工作框架：保存研究事实、约束修改、维护历史判断、计算结果、生成地图。

模型只由你自己的 coding agent 提供。本工具不要求另一份模型账号、额外 agent 窗口、图数据库、Node.js 或公网网站。核心运行只需要 Python 3.11+。

“一个对话完成”指你不必人工拆分并转发任务。内部仍然会有多次工具调用，也不能保证任意模型、任意大小或任意混乱的科研仓库一次就得到完全正确的科学解释。

## 先体验完整示例

解压后进入本目录：

```sh
python labweft.py demo ./research-demo
python labweft.py serve ./research-demo --open
```

在浏览器里可以展开项目、模块、问题、cell、run 和评估，切换关系视图，比较配置，查看均值与样本标准差，打开证据快照和更新记录时间线。页面提供 `中文 / English` 切换；内测页面默认中文。节点可选填 `attrs.i18n.zh` 和 `attrs.i18n.en` 的标题/说明；未提供的语言回退到原始记录。切换不会翻译来源证据，也不会改变科研数据。

`research-demo/.research/map.html` 也可以作为离线交互页面打开。
**全部示例数据和确认记录都是合成的，未执行真实训练，不对应任何真实科研项目。**

更新时间线按每次 revision 列出文件、节点和关系变更，可按变更类型与研究模块筛选。节点变更保留事件发生时的模块归属；文件的模块筛选使用当前记录的证据引用。事件时间是 LabWeft 观察或写入变化的时间，不是历史实验发生时间。页面只统计当前配置的来源目录及扫描限额；“扫描完成”也仅指这个范围，不能代表整个科研项目已被完整盘点。

状态词各有明确含义：界面的 `已记录 / Recorded` 表示对象进入索引；`记录为完成 / Reported complete` 仅表示来源记载某次运行或评估完成；`待核实 / Needs review` 应指出证据或身份问题。`据来源整理 / Source-based` 表示从来源整理出解释，不等于用户确认。`人工已确认 / Human confirmed` 需要明确确认及适用范围。LabWeft **节点状态** `历史归档 / Archived` 保留旧记录和证据，不删除文件。归档 Cell 退出当前地图层级和数值比较；归档的 claim、decision 仍可在历史决策列表查看及追溯来源。这个状态只描述 LabWeft 节点，不会删除、冻结或核验底层科研项目及其文件。
为减少重复警示，暂未确认的模块、问题和 Cell 不在每张树图卡片重复显示状态徽标；详情仍保留原状态。

## 对真实项目只做一次接入

```sh
python bootstrap.py --project /你的/项目目录 --results /你的/结果目录 --agent codex
```

如果项目目录只读，或想把记录集中放在本机，增加 `--workspace /可写的/LabWeft工作空间`。
Skill 和 `.research` 会写在该工作空间；项目与结果目录只作为只读来源。

Claude Code 使用 `--agent claude`。`--agent auto` 只检查本机已有目录来选择安装位置，不能替你获得目录权限或登录账号。

这条命令完成：安装一个 Skill、创建 `.research` 工作空间、只读扫描授权目录、生成初始事实地图。不会覆盖你的 `AGENTS.md`、修改训练代码、启动训练或上传数据。初始扫描地图不等于已经推理出所有研究动机。

接着，在原本的 agent 对话里说：

> 使用 LabWeft 整理当前项目。读取已有记录，核对代码和结果，关联 ablation 的研究目的、cell 差异与结论，复用仍然适用的历史判断，更新地图。不要启动新实验或上传数据。

后续步骤由这个 agent 使用本工具完成。你不必另开规划 agent、分析 agent 和画图 agent。
旧的 `rh` 命令、`research_harness` Python 包和 `research-harness` Skill ID 保留兼容；从源码运行的新入口是 `labweft.py`。

**兼容目标是具备读文件和运行命令能力的 agent，不是任意裸模型。** 两个私有项目已在当前 Codex 客户端对话按 Skill 程序做有限范围、分阶段内测；新聊天的 Skill 自动发现与其他宿主尚未独立认证。

## 可选的包安装

在隔离的 Python 环境中运行：

```sh
python -m pip install .
labweft --help
labweft install-skill --agent codex --project /你的/项目目录
```

用户级安装需显式指定 `--user`。安装器拒绝覆盖被编辑的 Skill，可升级未修改的受管理文件，也不会覆盖 `AGENTS.md` 或 `CLAUDE.md`。

## 本次已经实现

研究工作空间具有稳定 ID，不把项目等同于 Git branch。小型文本按内容哈希保存快照；Python 代码只静态提取符号，不执行。原生读入 JSON/TOML 配置以及固定文件名的 JSON/CSV 指标；YAML 和自定义日志先建立索引，由宿主 agent 检查解释。

结构化记录包含模块、研究问题、cell、run、评估、结论与决策。共享 baseline 用关系连接，不复制实验身份。Agent 的修改经过引用与版本检查后原子写入，旧事实保留在版本事件中；已人工确认的节点不能被普通 agent patch 覆盖。

历史判断使用明确适用范围。例如，合成示例中的硬件结论只覆盖指定实现、精度、数据、预算、协议与硬件取值。增加新 seed 不会自动变成“需要重做硬件消融”；改变评估协议会提示重新核对适用范围，而不是直接启动实验。

本地界面和离线 HTML 不调用模型。展开、搜索、看矩阵、读证据都不产生额外模型请求。

| 已实现 | 重要边界 |
|---|---|
| 稳定工作空间 ID，与分支名分开 | 不自动合并不同仓库的科研项目。 |
| 保守扫描、文本快照、Python 静态符号索引 | 不执行来源代码，也不重建未知历史代码。 |
| JSON/TOML 配置及 JSON/CSV 指标读入 | YAML 和自定义日志由宿主 agent 阅读、手动规范化。 |
| 候选 Cell 分组与 Run 身份 | 同名或配置相同不能证明科研等价。 |
| 带版本的原子语义更新 | 本地单写入者，不提供分布式冲突合并。 |
| 保护人工修正、检查历史判断的适用范围 | 需要明确确认及完整记录的条件。 |
| 对可比的训练 seed 计算均值与样本标准差 | 不自动判断胜负、因果或统计等价。 |
| 本地交互界面与离线 HTML | 页面只读，不调用模型。 |
| Codex、Claude Code、通用位置的 Skill 安装 | 未认证所有客户端版本。 |

## 常用命令

```sh
labweft init /你的/项目目录 --name "我的研究" --source code=/代码目录 --source results=/结果目录
labweft sync /你的/项目目录
labweft context /你的/项目目录
labweft files /你的/项目目录 --offset 0 --limit 50
labweft context /你的/项目目录 --full
labweft apply /你的/项目目录 /语义补丁.json
labweft validate /你的/项目目录
labweft compare /你的/项目目录 --metric success_rate
labweft export /你的/项目目录 --output /你的/项目目录/.research/map.html
labweft export /你的/项目目录 --include-evidence --output /你的/项目目录/.research/map-with-text.html
labweft serve /你的/项目目录 --open
```

这些步骤通常由宿主 agent 执行。源码运行时，可用 `python /LabWeft/所在位置/labweft.py` 替代 `labweft`。`sync` 仅读取来源，不独立推断研究动机；`apply` 写入宿主 agent 核对证据后形成的结构化分析。详见[补丁协议](research_harness/skill/research-harness/references/PROTOCOL.md)。离线导出默认不附来源原文；`--include-evidence` 显式嵌入索引内的小型文本快照，包括尚未被语义节点引用的索引文件，合计上限 **5 MiB**。超过上限或没有文本快照的文件会在离线来源列表准确标为省略/仅位置，无法从该离线页面打开。本地实时界面仍可读取已知快照。

## 历史判断示例

```sh
labweft assess research-demo research-demo/.research/proposal-covered.json
labweft assess research-demo research-demo/.research/proposal-changed-protocol.json
```

第一例在既定范围内复用硬件判断，把新 seed 识别为重复验证；第二例识别评估协议变化并要求复核范围。两条命令都不会启动实验。能否复用取决于明确记录的适用范围与人工确认，而不是配置表面相似。

## 记录保存在哪里

```text
你的项目/.research/
  manifest.json           # 稳定的科研项目身份
  local.json              # 本机来源映射；不纳入 Git
  events/00000001.json    # 带版本的权威事件
  blobs/<sha256>          # 小型文本的不可变证据快照；不纳入 Git
  map.html                # 派生的私有离线页面
```

来源数据不会移动。大型权重、数据集和视频不会被载入或备份；索引不是备份。迁移工作空间时需要重新绑定本机来源映射，必要时另外转移原始证据 blob。本原型的 Git 同步由用户自行管理，不能把私有实验记录直接推送到公开仓库。面对大型项目，先列清所选目录、格式、未读内容及实际扫描文件数；地图节点数不代表整个项目的覆盖率。

一次有限范围的私有试用通过分阶段选取文本文件暴露了覆盖缺口。对每个来源目录，应分别报告观察到的文件清单、可读文本候选、已选择并校验的文件、索引记录、映射的 Run 和独立重放的实验。自动生成的逐运行文件不能当作独立实验；选取样本形成的地图不能暗示全项目覆盖。旧版与修正版结果须保留不同证据身份，较早实验的完成范围也不能套到后续新增工作上。

## 已知边界

**“为什么做”和“是否值得补实验”仍由宿主模型根据证据分析，不是扫描器独立完成的能力。** 当前 Codex 客户端对两个私有项目的有限范围已按 Skill 流程完成内测，包括分批加入实验文件夹；新聊天中的自动 Skill 发现与其他宿主仍需分别验证。

缺少历史 commit 的运行不会被指派为“使用了今天的代码”。自定义日志没有全格式解析器。没有 GPU 调度、远程自动采集、多用户权限、自动 GitHub 同步或无需审查的科学判断。首版仅管理一个工作空间；该空间可连接多个来源目录，多项目总览需后续添加。

记录层使用本地文件锁和原子写入，不是分布式数据库。证据索引也不是产物备份。`.research/events` 可能包含私有科研信息；即使配置了 Git ignore，也需要人工检查再提交。

云端模型仍可能收到你交给宿主 agent 的代码。已跳过常见敏感文件名，不等于能识别代码里所有密钥。

## 安全与隐私

本地服务绑定 `127.0.0.1`，使用会话 token，只开放指定静态路径和已知证据快照，没有 shell 或写入 API。它不是加固的多用户服务，不应直接暴露公网。经授权的 SSH/VS Code 端口转发可用于查看远端服务。来源文本可能包含嵌入代码的密钥；分享离线页面前应检查内容，并使用宿主 agent 的沙盒和权限机制。详见 [SECURITY.md](SECURITY.md)。

## 测试与发布准备

```sh
python -m unittest discover -s tests -v
```

完整架构、协议、已知边界、验证结果和后续验收见 `docs/`，尤其是 [发布验收门槛](docs/RELEASE_GATES.zh-CN.md)。
后续核心目标是“在真实混乱项目上持续可靠”，不是增加多个必须由用户操作的 agent。

这些测试主要核对记录身份、保守读入、冲突、证据完整性、适用范围、seed 汇总、HTML 转义和本地 HTTP 访问控制。浏览器内测见 [验证记录](docs/VALIDATION.zh-CN.md)。它们不能证明科研解释正确、生产级安全或所有模型客户端都兼容。公开 beta 前仍需公开可复现的复杂项目基准、多个系统和客户端的干净安装、更多来源适配与安全审查。ClearML 级可靠性是目标，不是当前结论。

## 思想来源与许可证

这是独立实现；借鉴了已有系统的架构思想，没有捆绑多个 agent 框架。参考与署名见 [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。当前原创原型包含 MIT 许可证。正式公开发布前仍需确认维护权属及第三方说明；当前仓库并不等于已发布 PyPI 包或已改变仓库可见性。
