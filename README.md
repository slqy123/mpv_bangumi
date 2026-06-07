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

本插件需要系统安装python环境，并手动安装依赖库。推荐python>=3.13，更低版本理论可以但未进行测试，windows用户若无python环境，在微软应用商店搜索安装最新版即可。

1. 下载本插件代码至mpv脚本目录（`~/.config/mpv/scripts/`）

```
git clone https://github.com/slqy123/mpv_bangumi.git ~/.config/mpv/scripts/
```

2. 安装依赖库

```shell
cd mpv_bangumi/bgm
# 如果是微软商店安装的python，还需要在powershell中额外运行：
# $env:PATH = "$env:PATH;$HOME\AppData\Local\microsoft\windowsapps"
python -m venv .venv

# 根据系统和shell环境选择合适的激活命令
source .venv/bin/activate  # for linux bash/zsh
source .venv/bin/activate.fish  # for linux fish
. .venv/Scripts/activate.ps1  # for windows powershell(pwsh)

pip install -e .
```

3. 初始化配置

运行`bgm`命令，将交互式生成初始配置文件。

使用 `python -c "import appdirs; print(appdirs.user_config_dir('bgm'))"` 可查看配置文件夹位置。
可以在 `config.toml` 中修改弹幕样式：
```toml
[danmaku]
# 弹幕速度
scrolltime = 15
fixtime = 8
# 字体
fontname = "sans-serif"
# 大小
fontsize = 36
# 阴影
shadow = 1
# 粗体
bold = true
# 弹幕显示范围
displayarea = 0.5
# 描边
outline = 1.0
# 透明度
transparency = 0x30
```
`.env`中可以自定义API令牌
```shell
DANDANPLAY_APPID=...
DANDANPLAY_APPSECRET=...
BGM_ACCESS_TOKEN=...
DANDANPLAY_USERNAME=...
DANDANPLAY_PASSWORD=...
```

## 使用
- `ALT-M`: 手动匹配番剧(自动匹配未成功时使用)
- `ALT-O`: 打开番剧对应的 bangumi.tv 词条页面
- `SHIFT-C`: 发送弹幕
- `ALT-.`: 显示/隐藏 弹幕
- `ALT-Z/ALT-X`: 调整弹幕延迟
- `ALT-N`: N站弹幕设置

## 一些碎碎念

从项目名字就能看出，原本这个项目是只想做bangumi的自动同步功能的，但由于uosc_danmaku也会用到dandanplay的api，这会涉及到重复的API请求。

加上uosc_danmaku的功能太多架构太复杂，有很多我不需要的功能。（如dandanplay以外的其他弹幕源支持，uosc集成）
索性就把核心的弹幕渲染功能拿出来重写了一下，后续自己想添加其他的功能也更方便。

那为什么选Python呢？那当然是因为~~Python是世界上最好的编程语言。~~

好吧我也觉得这样依赖第三方程序调用的实现有点不优雅，不过最新版换成了IPC实现，整个mpv的生命周期内只会有一次Python调用，算是能接受的overhead了。

其实一开始尝试过使用embedded python做一个lua C 拓展，参考[luapython](https://github.com/imitoy/luapython)的实现，但原项目有很多功能还不太完善。
缺少`venv`和多线程的支持，在被GIL各种奇奇怪怪的死锁折腾得死去活来之后，我放弃了这个方案，也不知道mpv的官方python支持要等到猴年马月╮(╯_╰)╭。
