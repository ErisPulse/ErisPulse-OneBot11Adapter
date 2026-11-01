[English](README.en.md) | 简体中文 | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-OneBot11Adapter" />

# ErisPulse-OneBot11Adapter

**ErisPulse OneBot 11 アダプター — 任意の v11 実装に対応**

<p>
  <a href="https://pypi.org/project/ErisPulse-OneBot11Adapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-OneBot11Adapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-OneBot11Adapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## Overview

A **OneBot v11 protocol adapter** built on the [ErisPulse](https://github.com/ErisPulse/ErisPulse/) architecture — unified event handling, connection management, and both Server and Connect operating modes. Works with any OneBot v11 implementation.

```python
await onebot.Send.To("group", 123456).Text("Hello World!")
await onebot.Send.To("user", 123456).Image("http://example.com/image.jpg")
await onebot.Send.To("user", 123456).Voice("http://example.com/audio.mp3")
```

## Install

```bash
epsdk install OneBot11Adapter
```

## Links

- [ErisPulse main repo](https://github.com/ErisPulse/ErisPulse)
- [Module development guide](https://www.erisdev.com/#docs/developer-guide/README.md)

> The full documentation (configuration tables, event mappings, API reference) is in Chinese: switch to **简体中文** above.

## License

MIT
