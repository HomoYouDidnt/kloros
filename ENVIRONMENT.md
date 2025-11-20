# Environment Data
Collected: 2025-09-18T22:22:15


## uname -a

'uname' is not recognized as an internal or external command,
operable program or batch file.

## cat /etc/os-release

'cat' is not recognized as an internal or external command,
operable program or batch file.

## lscpu | sed -n "1,20p"

'lscpu' is not recognized as an internal or external command,
operable program or batch file.

## nvidia-smi -q -x | sed -n "1,120p"

'sed' is not recognized as an internal or external command,
operable program or batch file.

## nvidia-smi

Thu Sep 18 22:23:02 2025       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 581.29                 Driver Version: 581.29         CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                  Driver-Model | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 3060      WDDM  |   00000000:01:00.0  On |                  N/A |
|  0%   49C    P5             26W /  170W |    2749MiB /  12288MiB |     33%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|    0   N/A  N/A            2332    C+G   ...ato\StreamDeck\StreamDeck.exe      N/A      |
|    0   N/A  N/A            2896    C+G   ...UI3Apps\PowerToys.Peek.UI.exe      N/A      |
|    0   N/A  N/A            5384    C+G   ....0.3485.66\msedgewebview2.exe      N/A      |
|    0   N/A  N/A            9008    C+G   ...ef.win7x64\steamwebhelper.exe      N/A      |
|    0   N/A  N/A            9972    C+G   ...ntrolCenter\ControlCenter.exe      N/A      |
|    0   N/A  N/A           12828    C+G   ...lpaper_engine\wallpaper32.exe      N/A      |
|    0   N/A  N/A           14776    C+G   C:\Windows\explorer.exe               N/A      |
|    0   N/A  N/A           14820    C+G   ...2p2nqsd0c76g0\app\ChatGPT.exe      N/A      |
|    0   N/A  N/A           14984    C+G   ...indows\System32\ShellHost.exe      N/A      |
|    0   N/A  N/A           15316    C+G   ...2txyewy\CrossDeviceResume.exe      N/A      |
|    0   N/A  N/A           17124    C+G   ..._cw5n1h2txyewy\SearchHost.exe      N/A      |
|    0   N/A  N/A           17148    C+G   ...y\StartMenuExperienceHost.exe      N/A      |
|    0   N/A  N/A           18548    C+G   ...cord\app-1.0.9209\Discord.exe      N/A      |
|    0   N/A  N/A           19248    C+G   ....0.3485.66\msedgewebview2.exe      N/A      |
|    0   N/A  N/A           21520    C+G   ...s\PowerToys.PowerLauncher.exe      N/A      |
|    0   N/A  N/A           22356    C+G   ...8bbwe\PhoneExperienceHost.exe      N/A      |
|    0   N/A  N/A           22712    C+G   ...crosoft\OneDrive\OneDrive.exe      N/A      |
|    0   N/A  N/A           23428    C+G   ...5n1h2txyewy\TextInputHost.exe      N/A      |
|    0   N/A  N/A           25152    C+G   ...s\Win64\EpicGamesLauncher.exe      N/A      |
|    0   N/A  N/A           25772    C+G   ...aries\Win64\EpicWebHelper.exe      N/A      |
|    0   N/A  N/A           27684    C+G   ...Toys\PowerToys.FancyZones.exe      N/A      |
|    0   N/A  N/A           28040    C+G   ...rograms\wowup-cf\WowUp-CF.exe      N/A      |
|    0   N/A  N/A           28372    C+G   ...grams\LM Studio\LM Studio.exe      N/A      |
|    0   N/A  N/A           28956    C+G   C:\Windows\explorer.exe               N/A      |
|    0   N/A  N/A           29340      C   ...grams\LM Studio\LM Studio.exe      N/A      |
|    0   N/A  N/A           30656    C+G   ...2p2nqsd0c76g0\app\ChatGPT.exe      N/A      |
|    0   N/A  N/A           30716    C+G   ...m\114.0.1.0\GoogleDriveFS.exe      N/A      |
|    0   N/A  N/A           31204    C+G   ...xyewy\ShellExperienceHost.exe      N/A      |
|    0   N/A  N/A           31668    C+G   ...AcrobatNotificationClient.exe      N/A      |
|    0   N/A  N/A           33376    C+G   ...t\Edge\Application\msedge.exe      N/A      |
|    0   N/A  N/A           35200    C+G   ...I3Apps\PowerToys.Settings.exe      N/A      |
|    0   N/A  N/A           35328    C+G   ...adeonsoftware\AMDRSSrcExt.exe      N/A      |
|    0   N/A  N/A           36448    C+G   ...8bbwe\WsaClient\WsaClient.exe      N/A      |
|    0   N/A  N/A           37800      C   ...al\Programs\Ollama\ollama.exe      N/A      |
|    0   N/A  N/A           44528    C+G   ...Chrome\Application\chrome.exe      N/A      |
|    0   N/A  N/A           46008    C+G   ...Files\Notepad++\notepad++.exe      N/A      |
|    0   N/A  N/A           47656    C+G   ...s\PowerToys.ColorPickerUI.exe      N/A      |
|    0   N/A  N/A           51708    C+G   ...8bbwe\Microsoft.CmdPal.UI.exe      N/A      |
|    0   N/A  N/A           54960    C+G   ...s\PowerToys.AdvancedPaste.exe      N/A      |
|    0   N/A  N/A           56952    C+G   ...ms\Microsoft VS Code\Code.exe      N/A      |
+-----------------------------------------------------------------------------------------+

## nvcc --version

'nvcc' is not recognized as an internal or external command,
operable program or batch file.

## ldconfig -p | grep -i cuda

'ldconfig' is not recognized as an internal or external command,
operable program or batch file.

## python3 --version

Python 3.13.7

## pyenv versions

'pyenv' is not recognized as an internal or external command,
operable program or batch file.

## uv --version

uv 0.8.17 (10960bc13 2025-09-10)

## pip --version

pip 25.2 from C:\Users\morga\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\local-packages\Python313\site-packages\pip (python 3.13)


## node --version

'node' is not recognized as an internal or external command,
operable program or batch file.

## npm --version

'npm' is not recognized as an internal or external command,
operable program or batch file.

## pnpm --version

'pnpm' is not recognized as an internal or external command,
operable program or batch file.

## yarn --version

'yarn' is not recognized as an internal or external command,
operable program or batch file.

## tsc --version

'tsc' is not recognized as an internal or external command,
operable program or batch file.

## ffmpeg -version | head -1

'ffmpeg' is not recognized as an internal or external command,
operable program or batch file.

## convert -version | head -1

'head' is not recognized as an internal or external command,
operable program or batch file.

## systemctl list-units --type=service --state=running | sed -n "1,120p"

'systemctl' is not recognized as an internal or external command,
operable program or batch file.

## systemctl list-unit-files --type=service | grep -E 'ollama|tailscale|nginx|caddy|rtmp|obs|docker|podman|redis|postgres|mongodb|minio|autostart'

'systemctl' is not recognized as an internal or external command,
operable program or batch file.

## ss -tulpn | sed -n "1,200p"

'ss' is not recognized as an internal or external command,
operable program or batch file.

## nginx -v 2>&1

'nginx' is not recognized as an internal or external command,
operable program or batch file.

## caddy version

'caddy' is not recognized as an internal or external command,
operable program or batch file.

## apt list --upgradable | head -100

'apt' is not recognized as an internal or external command,
operable program or batch file.

## grep -hE "^(deb|deb-src)" /etc/apt/sources.list /etc/apt/sources.list.d/*.list

'grep' is not recognized as an internal or external command,
operable program or batch file.

## docker ps --format '{{.Image}} {{.Names}}'

docker: 'docker ps' accepts no arguments
System.Management.Automation.RemoteException
Usage:  docker ps [OPTIONS]
System.Management.Automation.RemoteException
Run 'docker ps --help' for more information

## docker images --digests

error during connect: Head "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/_ping": open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.

## podman ps --format "{{.Image}} {{.Names}}"

'podman' is not recognized as an internal or external command,
operable program or batch file.

## podman images --digests

'podman' is not recognized as an internal or external command,
operable program or batch file.
