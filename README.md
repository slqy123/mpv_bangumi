# mpv_bangumi

在mpv中使用dandanplay api加载弹幕，自动同步bangumi追番进度。

## 主要功能

- 自动识别番剧并加载弹幕
- 发送弹幕至dandanplay弹幕库（目前接口权限未开放，暂不可用）
- 自动同步bangumi追番进度
- [N站](https://www.nicovideo.jp)弹幕支持

其中弹幕播放功能参考[uosc_danmaku](https://github.com/Tony15246/uosc_danmaku)。
弹幕转换的功能主要基于DanmakuFactory原作者新写的[python版本](https://github.com/timerring/DanmakuConvert)修改。

## 安装

> [!NOTE]
> 最新版本重构了项目架构，改为使用IPC进行通信。目前还有很多小问题没修，windows支持未知，等稳定下来再测试。windows用户推荐还是使用[v1](https://github.com/slqy123/mpv_bangumi/tree/v1)分支。

本插件需要系统安装python环境，并手动安装依赖库。推荐python>=3.13，更低版本理论可以但未进行测试，windows用户若无python环境，在微软应用商店搜索安装最新版即可。

1. 下载本插件代码至mpv脚本目录（`~/.config/mpv/scripts/`）

```
git clone https://github.com/slqy123/mpv_bangumi.git ~/.config/mpv/scripts/
```

2. 安装依赖库

```shell
cd mpv_bangumi/bgm
python -m venv .venv

# 根据系统和shell环境选择合适的激活命令
source .venv/bin/activate  # for linux bash/zsh
source .venv/bin/activate.fish  # for linux fish
. .venv/Scripts/activate.ps1  # for windows powershell(pwsh)

pip install -e .
```

3. 初始化配置

运行`bgm`命令，将交互式生成初始配置文件。

## 使用
- `ALT-M`: 手动匹配番剧(自动匹配未成功时使用)
- `ALT-O`: 打开番剧对应的 bangumi.tv 词条页面
- `SHIFT-C`: 发送弹幕
- `ALT-.`: 显示/隐藏 弹幕
- `ALT-Z/ALT-X`: 调整弹幕延迟
- `ALT-N`: N站弹幕设置
