# LabWeft · 科研工作台

**让你已有的 coding agent 整理研究，而不是每次重新解释整个项目。**

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

在浏览器里可以展开项目、模块、问题、cell、run 和评估，切换关系视图，比较配置，查看均值与样本标准差，打开证据快照和历史决策。

`research-demo/.research/map.html` 也可以作为离线交互页面打开。
**全部示例数据和确认记录都是合成的，未执行真实训练，不对应任何真实科研项目。**

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

## 本次已经实现

研究工作空间具有稳定 ID，不把项目等同于 Git branch。小型文本按内容哈希保存快照；Python 代码只静态提取符号，不执行。原生读入 JSON/TOML 配置以及固定文件名的 JSON/CSV 指标；YAML 和自定义日志先建立索引，由宿主 agent 检查解释。

结构化记录包含模块、研究问题、cell、run、评估、结论与决策。共享 baseline 用关系连接，不复制实验身份。Agent 的修改经过引用与版本检查后原子写入，旧事实保留在版本事件中；已人工确认的节点不能被普通 agent patch 覆盖。

历史判断使用明确适用范围。例如，合成示例中的硬件结论只覆盖指定实现、精度、数据、预算、协议与硬件取值。增加新 seed 不会自动变成“需要重做硬件消融”；改变评估协议会提示重新核对适用范围，而不是直接启动实验。

本地界面和离线 HTML 不调用模型。展开、搜索、看矩阵、读证据都不产生额外模型请求。

## 已知边界

**“为什么做”和“是否值得补实验”仍由宿主模型根据证据分析，不是扫描器独立完成的能力。** 当前 Codex 客户端对两个私有项目的有限范围已按 Skill 流程完成内测，包括分批加入实验文件夹；新聊天中的自动 Skill 发现与其他宿主仍需分别验证。

缺少历史 commit 的运行不会被指派为“使用了今天的代码”。自定义日志没有全格式解析器。没有 GPU 调度、远程自动采集、多用户权限、自动 GitHub 同步或无需审查的科学判断。首版仅管理一个工作空间；该空间可连接多个来源目录，多项目总览需后续添加。

记录层使用本地文件锁和原子写入，不是分布式数据库。证据索引也不是产物备份。`.research/events` 可能包含私有科研信息；即使配置了 Git ignore，也需要人工检查再提交。

云端模型仍可能收到你交给宿主 agent 的代码。已跳过常见敏感文件名，不等于能识别代码里所有密钥。

## 开发与交接

```sh
python -m unittest discover -s tests -v
```

完整架构、协议、已知边界、验证结果和后续验收见 `docs/`，尤其是 [发布验收门槛](docs/RELEASE_GATES.md)。
后续核心目标是“在真实混乱项目上持续可靠”，不是增加多个必须由用户操作的 agent。

英文技术入口：[README.md](README.md)。思想来源与署名：[ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。
