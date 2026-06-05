local py = require("luapython")

py.load_prefix("../bgm/.venv")
-- py.ensure_gil()

print(py.import("requests").__file__)
print(py.import("this"))
