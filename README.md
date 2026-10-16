# excel-api-calls-using-azure-microsoft-access-token-sample

[![AppVeyor Build](https://ci.appveyor.com/api/projects/status/github/PasinduUmayanga/excel-api-calls-using-azure-microsoft-access-token-sample?branch=main&svg=true)](https://ci.appveyor.com/project/PasinduUmayanga/excel-api-calls-using-azure-microsoft-access-token-sample)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/UI-Tkinter-blue)
![PyInstaller](https://img.shields.io/badge/Packaging-PyInstaller-yellowgreen)
![AppVeyor](https://img.shields.io/badge/CI-AppVeyor-00B3E0?logo=appveyor&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)

## API Client UI

`api_client_ui.py` is a small desktop app for calling an API by URL and viewing the response. It uses only the Python standard library (Tkinter + `urllib`).

### Run

```
python api_client_ui.py
```

### Features

- Choose a method (GET, POST, PUT, PATCH, DELETE) and enter a URL
- Custom request headers (`Key: Value` per line) and request body
- Shows status code, response time and size
- Pretty-printed JSON response body and response headers
- Requests run in the background so the UI stays responsive

### CI build (AppVeyor)

`appveyor.yml` syntax-checks the script and packages it with PyInstaller into a single `ApiClient.exe`, published as a build artifact.
