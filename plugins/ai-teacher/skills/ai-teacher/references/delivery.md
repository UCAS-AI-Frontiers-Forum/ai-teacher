# 交付与可续接状态

## 最小状态目录

每个用户/项目一个 `ai-teacher-work/`；不跨目录猜测用户身份。状态脚本默认本地日期，也可用 `--as-of YYYY-MM-DD` 指定本次日期。模板在本技能 assets/；先复制为草稿再填，不把模板当已核验材料。

```text
ai-teacher-work/
  profiles/<id>/r0001.json
  capabilities/<id>/r0001.json
  workflows/<id>/r0001.json
  feedback/<id>/r0001.json
  evidence/                 # 公开/模拟试验记录与来源摘记
  notes/                    # 目标发现记录、本次决策、短操作说明与执行任务书
```

使用本技能 `scripts/teacher_state.py`（Python 3.10+，仅标准库）：

```bash
python3 <本技能目录>/scripts/teacher_state.py init --workspace /项目/ai-teacher-work
python3 <本技能目录>/scripts/teacher_state.py status --workspace /项目/ai-teacher-work --as-of 2026-11-08
python3 <本技能目录>/scripts/teacher_state.py check --workspace /项目/ai-teacher-work --file /项目/draft.json --as-of 2026-11-08
python3 <本技能目录>/scripts/teacher_state.py save --workspace /项目/ai-teacher-work --file /项目/draft.json --as-of 2026-11-08
```

save 会先校验再追加连续修订，拒绝覆盖；不会执行工作流、访问网络或替用户授权。按真实日期替换示例，不把它写死进日常调用。artifact 路径相对 workspace，不能指向外部/软链接。

## 档案与能力

init 创建匿名 local-user 档案，领域、工程、AI 熟练度和任务待本次诊断更新；未知保留 unknown，不凭身份推测。模板见 assets/profile.template.json。更新档案写下一修订，不覆盖历史。

用 `notes/<task-id>-discovery-r0001.md` 等追加记录目标发现：原始表达、已确认信息、假设/待确认项、提问或样稿如何改变理解。`profile.task` 保存当前理解，`profile.notes` 可指向发现记录；未经确认的推断仍注明假设。这些 Markdown 是人工/Teacher 维护的补充，状态脚本不校验其语义或自动续接，续接时由 Teacher 主动读取。不要为了记录要求用户提交完整聊天。

能力卡必须有来源、日期、适用环境、验证成熟度与证据；模板见 assets/capability.template.json。只有本次研究得到的能力才写入真实库，不自动导入示例知识。

## 工作流合同

assets/workflow.template.json 不是某个固定工作流，只规定以后生成的方案需要交代什么：

- 绑定档案修订、真实目标和 current_process；写出相对现状的改变、必要备选、学习/迁移/运行成本与未知。
- 每步有 owner、输入/输出、依赖、动作、检查、失败处理、所需授权；capability 引用绑定具体卡修订与适用理由。普通内置功能不必为了填表造能力卡。
- 可自动执行的步骤默认交给 agent；人工步骤注明需要人的具体意图、授权或领域判断。先自行核对来源、完整性和可复现性，再提供需要人判断的最小证据；技术操作和查错不能默认转给用户。
- human_guide 为人提供最少必要步骤；executor_brief 自包含地写目标、输入范围、环境、步骤引用、验收、授权及停止/交回条件。若只为人操作，brief 保留可交接信息即可。
- draft 是方案草稿；pilot-ready 表示小试依赖已核验且授权边界已明确，不代表有效；validated 表示所有约定标准有实际产物支持；in-use 表示还记录了后续复用证据。没有实测则留 draft/pilot-ready。
- conclusion 为 keep/pilot/adopt/defer。adopt 只用于 validated/in-use；keep 可记录现有方案，无需强行新增工具。更新由 AI teacher 判断；脚本只拒绝结构与状态上的矛盾。

交付给用户时不倾倒 JSON。简要说明“现在做什么、理由与证据、如何验收、未知”；执行 AI 才需要完整合同。让用户承担最少必需学习，别把完整工程文档变成必修课。

## 反馈

assets/feedback.template.json 记录 workflow_ref、success/partial/failed/not-used、具体问题、自述或产物证据。保存反馈不自动替换工作流，也不自动发给维护者。status 会标出当前版的 partial/failed 反馈，供下次诊断处理。

有试用记录授权时，澄清、操作、监督、纠错/接管及最终验收的人工时间和事件证据可保存在 `evidence/`，反馈 detail 摘记并引用文件。缺少计时写未知，不从聊天长度推算。案例研究与共享另行确认；日常运行不自动开启数据采集。

脚本无法验证网页是否真实阅读、证据是否充分、权限是否真的获得、工作流是否最优；必须由当前 AI teacher 与用户核对，不能称为权限沙箱或科研正确性证明。
