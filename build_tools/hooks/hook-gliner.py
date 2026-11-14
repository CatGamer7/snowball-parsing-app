from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# GLiNER и Transformers используют отложенные импорты и доступ к исходникам.
datas = collect_data_files("gliner")
hiddenimports = collect_submodules("gliner", on_error="warn once")
module_collection_mode = {"gliner": "pyz+py", "transformers": "pyz+py"}
