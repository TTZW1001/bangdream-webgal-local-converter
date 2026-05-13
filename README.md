# bangdream-webgal-local-converter

`bangdream-webgal-local-converter` 是一个面向 **BanG Dream! / 邦邦相关中文文本** 的本地转换工具，用于将小说、同人文、对话稿等内容整理为 **WebGAL 可读取的初稿脚本**。

## 项目初衷

本项目的设计目标，是在**尽可能不将原始文本提交给 AI 服务**的前提下，采用**本地规则驱动**的方式完成初步转换工作，为后续人工校订提供可直接编辑的 WebGAL 脚本基础。

项目关注的重点包括：

- 旁白与对白的拆分
- 说话人的归属判断
- 常见场景的识别与切换
- WebGAL 脚本结构的组织与输出

本项目定位于**初稿生成与人工校订辅助工具**，而非完全自动化的最终脚本生成器。

## 功能概览

- 支持本地运行，不依赖联网大模型
- 同时提供图形界面与命令行入口
- 支持常见学校、生活地点、演出场景的识别
- 支持多人对话、动作插入句、部分不规范引号写法的容错
- 支持对说话人进行人工修正
- 支持将误判对白改为旁白
- 支持将漏识别内容手动改为对白
- 支持立绘资源来源切换（系统默认内置 / 自定义 `figure` 目录）
- 支持外部 `figure` 目录扫描、角色映射与立绘资源微调
- 支持打包为 Windows EXE

## 当前适用范围

当前版本更适合处理以下类型的文本：

- 邦邦相关角色对话
- 校园场景，如教室、活动室、学生会室等
- 常见角色生活地点，如房间、客厅、门口等
- 常见演出场景，如前台、后台、休息室、舞台等
- 对话中夹杂动作描写的段落

## 局限性说明

以下情况仍可能需要人工复核或修正：

- 较长的多人连续接话
- 大段心理活动中的引用性引号
- 叙述句中嵌套“转述性对白”或“假设性对白”
- 主语省略较多、叙述跳跃较强的文本
- 立绘表情、动作等细粒度演出控制

因此，建议将本项目视为 **WebGAL 初稿生成工具**，用于减少基础整理工作量，而非直接替代最终脚本校订流程。

## 项目结构

```text
project/
├─ app.py
├─ build_exe.bat
├─ build_exe.ps1
├─ prepare_build_icon.py
├─ verify_exe_icon.py
├─ icon.png
├─ icon.ico
├─ config/
├─ src/
├─ tests/
└─ samples/
```

主要模块说明：

- `app.py`：项目入口，支持 GUI 与 CLI 两种模式
- `src/parser.py`：文本拆分、对白识别与基础容错
- `src/speaker_resolver.py`：说话人归属推断
- `src/scene_detector.py`：场景识别与场景映射
- `src/webgal_generator.py`：WebGAL 脚本生成
- `src/tk_main_window.py`：Tkinter 图形界面
- `config/`：角色、别名、场景等配置数据

## 运行环境

- Windows
- Python 3.12 推荐

基础依赖：

```txt
pytest>=8.0
```

若需打包为 EXE，请额外安装：

```powershell
python -m pip install pyinstaller pillow
```

## 本地运行

进入项目目录后执行：

```powershell
python app.py
```

该命令将启动图形界面。

## 命令行用法

```powershell
python app.py input.txt -o scene.txt
```

可选参数：

- `--mode auto|31|generic`
- `--school auto|花咲川|羽丘|月之森`
- `--scene-lock <关键词或背景路径>`
- `--config <配置目录>`

示例：

```powershell
python app.py .\samples\input.txt -o .\samples\scene.txt --mode auto --school 花咲川
```

## 图形界面使用说明

推荐通过图形界面完成实际转换与校正工作。

基本流程如下：

1. 导入原文
2. 点击“生成脚本”
3. 查看右侧输出结果
4. 通过“待确认项”或“对白修正”进行必要的人工修正
5. 导出脚本

当前界面支持的人工修正方式包括：

- 指定说话人
- 标记为旁白
- 将输出中的某行改为对白
- 清空人工修正后重新生成

当前版本新增的立绘资源相关功能包括：

- 可在“立绘资源设置”中选择使用系统默认内置资源，或切换到用户自定义 `figure` 目录
- 自定义 `figure` 目录支持角色资源扫描与角色映射修正
- 当启用自定义 `figure` 目录时，立绘微调窗口会优先读取对应模型实际存在的动作与表情
- 外部资源可用于默认立绘生成，也可用于单行立绘微调

## EXE 打包

项目提供以下打包脚本：

- `build_exe.bat`
- `build_exe.ps1`

可直接双击：

```text
build_exe.bat
```

或手动执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

默认行为：

- 打包为单文件 EXE
- 输出到 `output/`
- 默认文件名为 `邦邦WebGAL转化器.exe`

如目标 EXE 正被系统占用，脚本可能退避输出为：

- `邦邦WebGAL转化器-new.exe`

## 测试

运行全部测试：

```powershell
pytest
```

运行主要测试文件：

```powershell
pytest tests/test_mvp.py
```

## 技术路线

本项目当前采用**规则驱动**而非生成式模型驱动的处理方式。整体流程如下：

```text
原始文本
-> parser
-> speaker_resolver
-> scene_detector / webgal_generator
-> WebGAL 初稿脚本
```

后续优化通常集中于以下方向：

- parser 容错增强
- 说话人归属规则优化
- 场景配置与别名体系扩展
- 图形界面的人工校正体验提升
- 外部 `figure` 资源与内置资源的进一步统一管理
