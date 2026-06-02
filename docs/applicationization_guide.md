# 从 Notebook 到项目级 PhreeqPy 应用

本文档以 `CFAS_therm_240C_Ccp_SCM_multistage.ipynb` 为原型，给出将单个 Notebook 拓展为可维护、可测试、可复用 PhreeqPy 应用的路线。

## 1. 拆分 Notebook 的职责

原 Notebook 至少包含五类职责，应拆成独立模块：

1. **场景配置**：IPhreeqc DLL、数据库路径、初始孔隙水、边界流体、阶段数、transport 参数和绘图目标单元。
2. **阶段插值**：把 `boundary_base` 与 `boundary_interpolation` 转换为每一阶段的边界流体组成。
3. **PHREEQC 输入生成**：构造 `SOLUTION`、`RATES`、`KINETICS`、`EQUILIBRIUM_PHASES`、`SELECTED_OUTPUT` 等通用块；`TRANSPORT` 只是当前 workflow 的一种实现，不应写死为总框架。
4. **运行时执行**：加载数据库、运行 IPhreeqc、读取 selected output。
5. **后处理与可视化**：解析列名、归一化、保存 CSV、绘制最终分布图与追踪曲线。

本仓库当前已经将前四类职责落地为 `src/phreeqpyne` 包，并加入 simulation workflow 注册机制；后处理和可视化可以继续按同样方式迁移。

## 2. 推荐项目结构

```text
PhreeqPyne/
├── CFAS_therm_240C_Ccp_SCM_multistage.ipynb  # 原型和探索记录
├── pyproject.toml                            # 包元数据、依赖、CLI 入口
├── src/phreeqpyne/
│   ├── config.py                             # 可序列化场景配置
│   ├── interpolation.py                      # 阶段边界流体插值
│   ├── phreeqc_blocks.py                     # 通用 PHREEQC 块
│   ├── phreeqc_builder.py                    # workflow 分发入口
│   ├── simulations/                          # transport 等可扩展模拟工作流
│   ├── gui/                                  # 可选 Qt 参数填写窗口
│   ├── runner.py                             # IPhreeqc 运行封装
│   └── cli.py                                # 命令行入口
├── tests/                                    # 不依赖 DLL 的单元测试
└── docs/                                     # 应用化说明和建模约定
```

## 3. 分阶段实施路线

### 阶段 A：稳定可测试的脚本生成

- 将 Notebook 中的硬编码参数迁移到 `ModelConfig`。
- 将阶段插值函数迁移到 `interpolation.py`，用单元测试覆盖 linear、exp、log 三种曲线。
- 将 PHREEQC 字符串拼接迁移到 `phreeqc_builder.py`，先验证脚本包含关键块，不要求本机安装 IPhreeqc。

### 阶段 B：模拟 workflow 注册与输出标准化

- 将 `TRANSPORT` 移到 `simulations/transport.py`，作为当前默认 workflow。
- 用 `simulation_kind` 和 registry 分发构建器；未来新增 `advection`、`equilibrium_batch`、`inverse_modeling` 时只注册新的 builder。
- 把 `SOLUTION`、`RATES`、`KINETICS` 等通用块放在 `phreeqc_blocks.py`，避免每个模拟类型重复拼接。

### 阶段 C：运行器与输出标准化

- 在 `runner.py` 中集中处理 `phreeqpy.iphreeqc.phreeqc_dll`，避免包导入时就要求本机有 DLL。
- 约定每次运行至少写出两个 artifact：`phreeqpyne_input.phr` 与 `selected_output.csv`。
- 对运行时错误增加结构化日志，例如数据库路径不存在、selected output 为空、PHREEQC 脚本执行失败。

### 阶段 D：后处理和绘图产品化

- 将 Notebook 的列名解析、归一化、stage range 计算迁移到 `postprocess.py`。
- 将绘图函数迁移到 `plots.py`，统一接收 DataFrame、输出目录和图形配置。
- 为每种图定义稳定文件名，方便工作流系统或 Web 服务直接引用。

### 阶段 E：多场景批处理、Qt 交互与应用接口

- 用 JSON/YAML 保存多个情景，CLI 支持 `phreeqpyne run --config scenario.json`。
- 增加批处理入口，例如 `phreeqpyne batch scenarios/*.json`。
- 用可选 `PySide6` 实现 Qt 参数填写窗口，先覆盖 DLL、数据库、阶段数、shift、温压 pH 和关键元素浓度，再逐步扩展到全部参数。
- 如果要做 Web 应用，可让后端调用同一个包接口，而不是复制 Notebook 代码。

## 4. 使用当前脚手架

生成默认配置：

```bash
phreeqpyne init-config --output scenario.json
```

列出当前可用模拟 workflow：

```bash
phreeqpyne list-simulations
```

打开 Qt 参数填写窗口：

```bash
python -m pip install -e .[gui]
phreeqpyne gui
```

只生成 PHREEQC 输入文件，不运行 DLL：

```bash
phreeqpyne build-script --config scenario.json --output scenario.phr
```

运行完整模拟并写出结果：

```bash
phreeqpyne run --config scenario.json
```

> 注意：`run` 需要本机的 IPhreeqc 动态库和数据库路径正确；`build-script` 与单元测试不需要。

## 5. Notebook 保留方式

Notebook 不应继续承担核心业务逻辑。推荐将它保留为：

- 原型探索和科学解释记录；
- 调用项目包的演示入口；
- 结果图和校核表的交互式展示。

核心计算应通过包函数、CLI 或服务接口触发，这样才能实现版本控制、测试、批处理和团队复用。
