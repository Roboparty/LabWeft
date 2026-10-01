# Shinka 自动研究后端

[完整英文接口与边界](AUTORESEARCH.md)

LabWeft 增加了可选的 `research` 命令：冻结研究合同、运行 Shinka、停止与恢复、
回收候选结果。现有扫描器和浏览器保持原有只读行为；未启用后端时不需要模型 SDK。

## 接入方式

在实际运行实验的机器上安装可选依赖：

```sh
python -m pip install ".[shinka]"
python labweft.py init /工作空间 --name "自动研究"
python labweft.py research prepare /工作空间 /研究合同.json
python labweft.py research start /工作空间 活动ID
```

最后一条只预览，不执行实验。合同参考
[合成示例](../examples/shinka/campaign.json)，必须自行指定模型、评价协议、代数、
超时和执行范围。`task_dir` 相对合同文件定位，`files` 显式列出 `initial.py`、
`evaluate.py` 及依赖的小型文件。冻结副本上限合计5 MiB，大数据留在执行主机。
同一活动ID和相同输入可以重复准备；修改合同须使用新ID。

已有用户授权覆盖模型与算力范围后，可以执行：

```sh
python labweft.py research start /工作空间 活动ID --execute
python labweft.py research status /工作空间 活动ID
python labweft.py research collect /工作空间 活动ID
python labweft.py research stop /工作空间 活动ID
python labweft.py research resume /工作空间 活动ID --execute
```

宿主 agent 可以在同一对话内使用这些命令，不需要额外用户操作的 agent 会话。
后端固定到上游提交 `9912af12d423504b8d580f4179fd15f5f88b8c50`，启动会核对安装来源。
这里只配置明确选择的变异模型，关闭额外 embedding、meta、novelty judge、提示词进化
模型调用及 W&B。Shinka 负责父代选择、岛屿搜索和本机实验派发。

## 停止、恢复与预算

- `stop` 等待当前有界批次结束后停止新派发，不杀实验进程。每批首次至少包含基线
  与一个提案，后续按 `batch_size` 推进。
- `max_generations` 包含基线第0代，是整个活动的绝对总额；恢复不会重新获得额度。
  代数不等于精确物理启动次数，Shinka 内部可能重试，原生尝试日志保留。
- 干净暂停后复用同一个数据库、候选ID、输入hash和原生费用记录恢复。
- 批次中途崩溃或启动结果不明时进入待核查状态，不自动重跑。需检查实际子进程和
  原始证据；当前未实现异常退出后的自动孤儿任务对账。
- API费用上限是上游估算口径，不是硬性账单上限，也不包含GPU租金。

第一版本机执行；若实验在远端，就在远端安装和调用 LabWeft。尚未接入 Luna 的
SSH 调度、固定物理启动账本或 GPU 资源准入。候选是单个 Python 程序，不支持整仓库变异。
哈希核验不等于执行沙箱，真实候选需要在适当隔离的环境里运行。

## 结果如何进入地图

一个研究活动对应研究问题，Shinka 候选对应 Cell、Run 和 Evaluation；源码继承
写入 `derived_from`。每个后端程序ID保持独立，失败、未知费用、代码hash和原生指标
都有记录；重复回收不会重复创建实验。缺失父版本保持未解析，不猜测继承关系。

这些是“后端报告”，不是人工确认或独立科学结论。不会伪造训练 seed，不会把搜索
分数送入已有训练均值统计；数据发布资格保持未通过。可以通过原有研究地图和离线
HTML查看候选、关系与证据，浏览器没有新增执行按钮或写入接口。

离线测试覆盖合成原生格式、生命周期、恢复、失败保留和证据导入；尚未以真实模型
调用证明搜索效果，也不代表 Luna 数采已通过物理或数据资格验证。
