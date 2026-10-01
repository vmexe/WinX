"""The tweak catalogue.

Every entry is a :class:`~winx.core.model.TweakDef`: a named, reversible,
risk-rated change.  Adding a capability here automatically gives it a switch in
the right page, a state check, a backup/undo path and a preview — no UI code.
"""

from __future__ import annotations

from ..core.model import (
    MODERATE,
    RISKY,
    Command,
    RegSet,
    ServiceSet,
    TweakDef,
)

HKCU = "HKCU"
HKLM = "HKLM"

EXPLORER_ADV = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
EXPLORER_MAIN = r"Software\Microsoft\Windows\CurrentVersion\Explorer"
VISUAL = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
POLICIES_SYSTEM = r"SOFTWARE\Policies\Microsoft\Windows\System"
CURRENT_POLICIES = r"Software\Microsoft\Windows\CurrentVersion\Policies"


def _t(*args, **kwargs) -> TweakDef:
    return TweakDef(*args, **kwargs)


# ==========================================================================
# PERFORMANCE
# ==========================================================================
PERFORMANCE: list[TweakDef] = [
    _t(
        key="perf_visual_best",
        name="Adjust for best performance",
        description="Turns off animations, shadows and transparency system-wide. Biggest single win on older hardware.",
        category="performance",
        risk=MODERATE,
        sets=[RegSet(HKCU, VISUAL, "VisualFXSetting", 2, off_value=1)],
    ),
    _t(
        key="perf_menu_speed",
        name="Instant menus",
        description="Removes the menu show delay so right-click and Start menus open instantly.",
        category="performance",
        sets=[RegSet(HKCU, r"Control Panel\Desktop", "MenuShowDelay", "0", off_value="400")],
    ),
    _t(
        key="perf_no_animations",
        name="Disable window animations",
        description="Stops minimise/maximise animation. Makes the desktop feel snappier.",
        category="performance",
        sets=[RegSet(HKCU, r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0", off_value="1")],
        restart="explorer",
    ),
    _t(
        key="perf_no_transparency",
        name="Disable transparency effects",
        description="Turns off acrylic/transparent surfaces, freeing GPU work on the shell.",
        category="performance",
        sets=[RegSet(HKCU, PERSONALIZE, "EnableTransparency", 0, off_value=1)],
    ),
    _t(
        key="perf_background_apps",
        name="Stop background apps",
        description="Prevents Store apps from running when you are not using them. Frees RAM and CPU.",
        category="performance",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 1, off_value=0)],
    ),
    _t(
        key="perf_startup_delay",
        name="Remove 10s startup delay",
        description="Removes the artificial delay Windows adds before launching logon apps.",
        category="performance",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize", "StartupDelayInMSec", 0)],
    ),
    _t(
        key="perf_kill_hung_apps",
        name="Auto-close hung apps",
        description="Ends non-responding applications automatically instead of waiting.",
        category="performance",
        risk=MODERATE,
        sets=[
            RegSet(HKCU, r"Control Panel\Desktop", "AutoEndTasks", "1", off_value="0"),
            RegSet(HKCU, r"Control Panel\Desktop", "WaitToKillAppTimeout", "2000", off_value="20000"),
            RegSet(HKCU, r"Control Panel\Desktop", "HungAppTimeout", "1000", off_value="5000"),
        ],
    ),
    _t(
        key="perf_sysmain_off",
        name="Disable SysMain (Superfetch)",
        description="Usually helps on SSDs: stops the prefetcher from loading RAM aggressively. Turn back on if you use an HDD.",
        category="performance",
        risk=MODERATE,
        admin=True,
        services=[ServiceSet("SysMain", start="disabled", running=False, off_start="auto")],
        sets=[
            RegSet(HKLM, r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters", "EnableSuperfetch", 0, off_value=3),
            RegSet(HKLM, r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters", "EnablePrefetcher", 0, off_value=3),
        ],
    ),
    _t(
        key="perf_search_off",
        name="Disable Windows Search indexing",
        description="Frees a lot of disk/CPU time on mechanical drives. Makes Start/Explorer search slower.",
        category="performance",
        risk=MODERATE,
        admin=True,
        services=[ServiceSet("WSearch", start="disabled", running=False, off_start="delayed-auto")],
    ),
    _t(
        key="perf_no_hibernate",
        name="Turn off hibernation",
        description="Deletes hiberfil.sys (several GB) and disables hibernation. Fast Startup stops working too.",
        category="performance",
        risk=MODERATE,
        admin=True,
        apply_cmds=[Command(kind="powershell", script="powercfg -h off", label="powercfg -h off")],
        revert_cmds=[Command(kind="powershell", script="powercfg -h on", label="powercfg -h on")],
    ),
    _t(
        key="perf_no_fast_startup",
        name="Disable Fast Startup",
        description="Fixes drivers that misbehave across boots (Wi-Fi, GPU). Shutdown takes a little longer.",
        category="performance",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled", 0, off_value=1)],
    ),
    _t(
        key="perf_no_last_access",
        name="Disable NTFS last-access timestamps",
        description="Stops Windows writing a timestamp on every file read. Noticeable on large libraries.",
        category="performance",
        admin=True,
        apply_cmds=[Command(kind="proc", args=["fsutil", "behavior", "set", "disablelastaccess", "1"], label="fsutil behavior set disablelastaccess 1")],
        revert_cmds=[Command(kind="proc", args=["fsutil", "behavior", "set", "disablelastaccess", "2"], label="fsutil behavior set disablelastaccess 2")],
    ),
    _t(
        key="perf_multimedia_responsive",
        name="Prioritise foreground apps",
        description="Sets the multimedia scheduler to reserve nothing for background work (SystemResponsiveness = 0).",
        category="performance",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "SystemResponsiveness", 0, off_value=20)],
    ),
    _t(
        key="perf_no_network_throttle",
        name="Remove network throttling",
        description="Disables the multimedia class scheduler's network throttling (helps streaming and gaming).",
        category="performance",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile", "NetworkThrottlingIndex", 0xFFFFFFFF, off_value=10)],
    ),
    _t(
        key="perf_gpu_scheduling",
        name="Hardware-accelerated GPU scheduling",
        description="Lets the GPU manage its own video memory. Requires a reboot and a supported GPU.",
        category="performance",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2, off_value=1)],
        restart="pc",
    ),
    _t(
        key="perf_storage_sense",
        name="Enable Storage Sense",
        description="Lets Windows automatically delete temp files and empty the Recycle Bin.",
        category="performance",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy", "01", 1, off_value=0)],
    ),
    _t(
        key="perf_mouse_no_accel",
        name="Disable mouse acceleration",
        description="1:1 pointer movement — preferred for gaming and precise work.",
        category="performance",
        sets=[
            RegSet(HKCU, r"Control Panel\Mouse", "MouseSpeed", "0", off_value="1"),
            RegSet(HKCU, r"Control Panel\Mouse", "MouseThreshold1", "0", off_value="6"),
            RegSet(HKCU, r"Control Panel\Mouse", "MouseThreshold2", "0", off_value="10"),
        ],
    ),
    _t(
        key="perf_no_sticky_keys",
        name="Disable Sticky Keys prompt",
        description="Stops the Sticky Keys dialog appearing when Shift is pressed five times.",
        category="performance",
        sets=[RegSet(HKCU, r"Control Panel\Accessibility\StickyKeys", "Flags", "506", off_value="510")],
    ),
    _t(
        key="perf_delivery_optimisation_off",
        name="Disable peer-to-peer update sharing",
        description="Stops your PC uploading updates to other machines on the network/internet.",
        category="performance",
        admin=True,
        services=[ServiceSet("DoSvc", start="disabled", running=False, off_start="delayed-auto")],
    ),
    _t(
        key="perf_print_spooler_off",
        name="Disable Print Spooler",
        description="Skip if you print. Spooler is a common background resource user (and an attack surface).",
        category="performance",
        risk=MODERATE,
        admin=True,
        services=[ServiceSet("Spooler", start="disabled", running=False, off_start="auto")],
    ),
    _t(
        key="perf_fax_off",
        name="Disable Fax service",
        description="Nobody faxes. One less auto-starting service.",
        category="performance",
        admin=True,
        services=[ServiceSet("Fax", start="disabled", running=False, off_start="manual")],
    ),
    _t(
        key="perf_retail_demo_off",
        name="Disable Retail Demo service",
        description="Background service used only by store display machines.",
        category="performance",
        admin=True,
        services=[ServiceSet("RetailDemo", start="disabled", running=False, off_start="manual")],
    ),
    _t(
        key="perf_maps_off",
        name="Disable Downloaded Maps Manager",
        description="Stops automatic map updates in the background.",
        category="performance",
        admin=True,
        services=[ServiceSet("MapsBroker", start="disabled", running=False, off_start="delayed-auto")],
    ),
]

# ==========================================================================
# POWER PLANS (command based)
# ==========================================================================
POWER_PLANS: list[TweakDef] = [
    _t(
        key="power_ultimate",
        name="Ultimate Performance",
        description="Unlocks and activates the hidden 'Ultimate Performance' plan. Maximum clocks, highest draw.",
        category="performance",
        risk=MODERATE,
        admin=True,
        apply_cmds=[
            Command(kind="powershell", script="powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03bd147049be", label="powercfg -duplicatescheme (ultimate)"),
            Command(kind="powershell", script="powercfg -setactive e9a42b02-d5df-448d-aa00-03bd147049be", label="powercfg -setactive (ultimate)"),
        ],
        revert_cmds=[Command(kind="powershell", script="powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e", label="powercfg -setactive (balanced)")],
        tags=("power",),
    ),
    _t(
        key="power_high",
        name="High Performance",
        description="Activates the built-in High Performance plan: no core parking, no aggressive downclocking.",
        category="performance",
        admin=True,
        apply_cmds=[Command(kind="powershell", script="powercfg -setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c", label="powercfg -setactive (high performance)")],
        revert_cmds=[Command(kind="powershell", script="powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e", label="powercfg -setactive (balanced)")],
        tags=("power",),
    ),
    _t(
        key="power_balanced",
        name="Balanced (Windows default)",
        description="Restores the Balanced power plan — the recommended setting for laptops.",
        category="performance",
        admin=True,
        apply_cmds=[Command(kind="powershell", script="powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e", label="powercfg -setactive (balanced)")],
        tags=("power",),
    ),
    _t(
        key="power_saver",
        name="Power saver",
        description="Activates the Power saver plan for maximum battery life.",
        category="performance",
        admin=True,
        apply_cmds=[Command(kind="powershell", script="powercfg -setactive a1841308-3541-4fab-bc81-f71556f20b4a", label="powercfg -setactive (power saver)")],
        revert_cmds=[Command(kind="powershell", script="powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e", label="powercfg -setactive (balanced)")],
        tags=("power",),
    ),
    _t(
        key="power_usb_selective_suspend_off",
        name="Keep USB devices awake",
        description="Disables USB selective suspend, fixing mice/keyboards/audio interfaces that randomly drop out.",
        category="performance",
        admin=True,
        apply_cmds=[
            Command(
                kind="powershell",
                script=(
                    "powercfg -setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0; "
                    "powercfg -setdcvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0; "
                    "powercfg -setactive SCHEME_CURRENT"
                ),
                label="powercfg: disable USB selective suspend (AC + DC)",
            )
        ],
    ),
]

# ==========================================================================
# PRIVACY
# ==========================================================================
PRIVACY: list[TweakDef] = [
    _t(
        key="priv_telemetry_off",
        name="Disable diagnostic telemetry",
        description="Sets telemetry to the minimum level (0) and disables the DiagTrack service.",
        category="privacy",
        risk=MODERATE,
        admin=True,
        sets=[
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0, off_value=1),
            RegSet(HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection", "AllowTelemetry", 0, off_value=1),
            RegSet(HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection", "MaxTelemetryAllowed", 0, off_value=3),
        ],
        services=[ServiceSet("DiagTrack", start="disabled", running=False, off_start="auto")],
    ),
    _t(
        key="priv_advertising_id_off",
        name="Disable advertising ID",
        description="Stops apps from using a per-user advertising identifier for profiling.",
        category="privacy",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0, off_value=1)],
    ),
    _t(
        key="priv_activity_history_off",
        name="Disable activity history",
        description="Stops Windows collecting your app/file usage history and sending it to Microsoft.",
        category="privacy",
        admin=True,
        sets=[
            RegSet(HKLM, POLICIES_SYSTEM, "EnableActivityFeed", 0, off_value=1),
            RegSet(HKLM, POLICIES_SYSTEM, "PublishUserActivities", 0, off_value=1),
            RegSet(HKLM, POLICIES_SYSTEM, "UploadUserActivities", 0, off_value=1),
        ],
    ),
    _t(
        key="priv_location_off",
        name="Disable location tracking",
        description="Turns off the location service and denies apps access to your position.",
        category="privacy",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors", "DisableLocation", 1, off_value=0)],
        services=[ServiceSet("lfsvc", start="disabled", running=False, off_start="demand")],
    ),
    _t(
        key="priv_feedback_off",
        name="Stop feedback requests",
        description="Sets 'Windows should ask for my feedback' to never.",
        category="privacy",
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", 0),
            RegSet(HKCU, r"Software\Microsoft\Siuf\Rules", "PeriodInNanoSeconds", 0),
        ],
    ),
    _t(
        key="priv_tailored_experiences_off",
        name="Disable tailored experiences",
        description="Stops Windows using diagnostic data to personalise tips and ads.",
        category="privacy",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0, off_value=1)],
    ),
    _t(
        key="priv_web_search_off",
        name="Disable web search in Start",
        description="Keeps Start menu searches local — no Bing results, no query upload.",
        category="privacy",
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Search", "CortanaConsent", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Search", "AllowSearchToUseLocation", 0, off_value=1),
        ],
    ),
    _t(
        key="priv_cortana_off",
        name="Disable Cortana",
        description="Turns Cortana off through policy and hides it from the taskbar.",
        category="privacy",
        risk=MODERATE,
        admin=True,
        sets=[
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\Windows Search", "AllowCortana", 0, off_value=1),
            RegSet(HKCU, EXPLORER_ADV, "ShowCortanaButton", 0, off_value=1),
        ],
    ),
    _t(
        key="priv_typing_personalisation_off",
        name="Disable typing & inking personalisation",
        description="Stops the collection of what you type and write for the personal dictionary.",
        category="privacy",
        sets=[
            RegSet(HKCU, r"Software\Microsoft\InputPersonalization", "RestrictImplicitTextCollection", 1, off_value=0),
            RegSet(HKCU, r"Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 1, off_value=0),
            RegSet(HKCU, r"Software\Microsoft\Personalization\Settings", "AcceptedPrivacyPolicy", 0, off_value=1),
        ],
    ),
    _t(
        key="priv_wifi_sense_off",
        name="Disable Wi-Fi Sense",
        description="Stops sharing Wi-Fi credentials with your contacts and auto-connecting to open hotspots.",
        category="privacy",
        admin=True,
        sets=[
            RegSet(HKLM, r"SOFTWARE\Microsoft\WcmSvc\wifinetworkmanager\config", "AutoConnectAllowedOEM", 0, off_value=1),
            RegSet(HKLM, r"SOFTWARE\Microsoft\WcmSvc\wifinetworkmanager\config", "WiFISenseAllowed", 0, off_value=1),
        ],
    ),
    _t(
        key="priv_app_diagnostics_off",
        name="Block app diagnostics access",
        description="Denies apps permission to read diagnostic information about other apps.",
        category="privacy",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\appDiagnostics", "Value", "Deny", off_value="Allow")],
    ),
    _t(
        key="priv_camera_access_off",
        name="Block camera for Store apps",
        description="Denies all Store apps access to the camera. Hardware buttons still override per-app later.",
        category="privacy",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsAccessCamera", 2, off_value=0)],
    ),
    _t(
        key="priv_mic_access_off",
        name="Block microphone for Store apps",
        description="Denies all Store apps access to the microphone.",
        category="privacy",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsAccessMicrophone", 2, off_value=0)],
    ),
    _t(
        key="priv_copilot_off",
        name="Disable Windows Copilot",
        description="Turns the Copilot sidebar off through policy (Windows 11).",
        category="privacy",
        sets=[
            RegSet(HKCU, r"Software\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1, off_value=0),
            RegSet(HKCU, EXPLORER_ADV, "ShowCopilotButton", 0, off_value=1),
        ],
    ),
    _t(
        key="priv_recall_off",
        name="Disable Recall / AI snapshots",
        description="Stops Windows taking periodic screen snapshots for AI search.",
        category="privacy",
        risk=MODERATE,
        admin=True,
        sets=[
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI", "DisableAIDataAnalysis", 1, off_value=0),
            RegSet(HKCU, r"Software\Policies\Microsoft\Windows\WindowsAI", "DisableAIDataAnalysis", 1, off_value=0),
        ],
    ),
    _t(
        key="priv_telemetry_tasks_off",
        name="Disable telemetry scheduled tasks",
        description="Disables the Compatibility Appraiser, Customer Experience and DiskDiagnosticDataCollector tasks.",
        category="privacy",
        risk=MODERATE,
        admin=True,
        apply_cmds=[
            Command(
                kind="powershell",
                script=(
                    "$t = @('\\Microsoft\\Windows\\Application Experience\\Microsoft Compatibility Appraiser',"
                    "'\\Microsoft\\Windows\\Application Experience\\ProgramDataUpdater',"
                    "'\\Microsoft\\Windows\\Application Experience\\StartupAppTask',"
                    "'\\Microsoft\\Windows\\Customer Experience Improvement Program\\Consolidator',"
                    "'\\Microsoft\\Windows\\Customer Experience Improvement Program\\UsbCeip',"
                    "'\\Microsoft\\Windows\\DiskDiagnostic\\Microsoft-Windows-DiskDiagnosticDataCollector'); "
                    "foreach ($i in $t) { schtasks /Change /TN $i /Disable }"
                ),
                label="schtasks /Disable (6 telemetry tasks)",
            )
        ],
        revert_cmds=[
            Command(
                kind="powershell",
                script=(
                    "$t = @('\\Microsoft\\Windows\\Application Experience\\Microsoft Compatibility Appraiser',"
                    "'\\Microsoft\\Windows\\Application Experience\\ProgramDataUpdater',"
                    "'\\Microsoft\\Windows\\Application Experience\\StartupAppTask',"
                    "'\\Microsoft\\Windows\\Customer Experience Improvement Program\\Consolidator',"
                    "'\\Microsoft\\Windows\\Customer Experience Improvement Program\\UsbCeip',"
                    "'\\Microsoft\\Windows\\DiskDiagnostic\\Microsoft-Windows-DiskDiagnosticDataCollector'); "
                    "foreach ($i in $t) { schtasks /Change /TN $i /Enable }"
                ),
                label="schtasks /Enable (6 telemetry tasks)",
            )
        ],
    ),
    _t(
        key="priv_cloud_clipboard_off",
        name="Disable cloud clipboard sync",
        description="Stops clipboard history syncing to your Microsoft account.",
        category="privacy",
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Clipboard", "EnableClipboardHistory", 0, off_value=1),
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\System", "AllowClipboardHistory", 0, off_value=1),
        ],
    ),
    _t(
        key="priv_voice_activation_off",
        name="Disable voice activation",
        description="Stops apps listening for a spoken wake word while the device is locked.",
        category="privacy",
        admin=True,
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted", 0, off_value=1),
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsActivateWithVoice", 2, off_value=0),
        ],
    ),
    _t(
        key="priv_recent_docs_off",
        name="Stop tracking recent documents",
        description="Clears and disables Recent Items / Jump Lists in Start and Explorer.",
        category="privacy",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoRecentDocsHistory", 1, off_value=0)],
        restart="explorer",
    ),
]

# ==========================================================================
# SECURITY
# ==========================================================================
SECURITY: list[TweakDef] = [
    _t(
        key="sec_smartscreen_on",
        name="Force SmartScreen on",
        description="Enables SmartScreen for apps, files and the web through policy (cannot be turned off in Settings).",
        category="security",
        admin=True,
        sets=[
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\System", "EnableSmartScreen", 1),
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\System", "ShellSmartScreenLevel", "Block"),
        ],
    ),
    _t(
        key="sec_rdp_off",
        name="Disable Remote Desktop",
        description="Refuses incoming Remote Desktop connections. Essential on home machines.",
        category="security",
        admin=True,
        sets=[RegSet(HKLM, r"SYSTEM\CurrentControlSet\Control\Terminal Server", "fDenyTSConnections", 1, off_value=0)],
    ),
    _t(
        key="sec_remote_registry_off",
        name="Disable Remote Registry",
        description="No other machine can read or edit your registry over the network.",
        category="security",
        admin=True,
        services=[ServiceSet("RemoteRegistry", start="disabled", running=False, off_start="demand")],
    ),
    _t(
        key="sec_autoplay_off",
        name="Disable AutoPlay / AutoRun",
        description="Stops USB sticks and optical media launching code automatically.",
        category="security",
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers", "DisableAutoplay", 1, off_value=0),
            RegSet(HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer", "NoDriveTypeAutoRun", 255, off_value=145),
        ],
    ),
    _t(
        key="sec_smb1_off",
        name="Disable SMBv1",
        description="Removes the legacy SMBv1 protocol abused by WannaCry-style worms.",
        category="security",
        risk=MODERATE,
        admin=True,
        apply_cmds=[Command(kind="powershell", script="Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart -ErrorAction SilentlyContinue", label="Disable-WindowsOptionalFeature SMB1Protocol")],
        revert_cmds=[Command(kind="powershell", script="Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart -ErrorAction SilentlyContinue", label="Enable-WindowsOptionalFeature SMB1Protocol")],
        restart="pc",
    ),
    _t(
        key="sec_llmnr_off",
        name="Disable LLMNR & mDNS spoofing vectors",
        description="Turns off Link-Local Multicast Name Resolution (Responder/relay attack surface).",
        category="security",
        risk=MODERATE,
        admin=True,
        sets=[
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient", "EnableMulticast", 0, off_value=1),
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows NT\DNSClient", "EnableMDNS", 0, off_value=1),
        ],
    ),
    _t(
        key="sec_lsa_protection",
        name="Enable LSA protection (RunAsPPL)",
        description="Runs the Local Security Authority as a protected process, blocking credential theft tools.",
        category="security",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SYSTEM\CurrentControlSet\Control\Lsa", "RunAsPPL", 1, off_value=0)],
        restart="pc",
    ),
    _t(
        key="sec_uac_secure_desktop",
        name="UAC on secure desktop",
        description="Prompts appear on a locked desktop so malware cannot fake them.",
        category="security",
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "PromptOnSecureDesktop", 1, off_value=0)],
    ),
    _t(
        key="sec_hide_last_user",
        name="Don't show last signed-in user",
        description="Forces a full username entry at the lock screen instead of revealing the last account.",
        category="security",
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "dontdisplaylastusername", 1, off_value=0)],
    ),
    _t(
        key="sec_guest_off",
        name="Disable the Guest account",
        description="Ensures the built-in Guest account is deactivated.",
        category="security",
        admin=True,
        apply_cmds=[Command(kind="powershell", script="net user guest /active:no", label="net user guest /active:no")],
        revert_cmds=[Command(kind="powershell", script="net user guest /active:yes", label="net user guest /active:yes")],
    ),
    _t(
        key="sec_defender_tamper",
        name="Enable Defender tamper protection",
        description="Blocks other software (including malware) from disabling Defender.",
        category="security",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Microsoft\Windows Defender\Features", "TamperProtection", 5, off_value=4)],
    ),
    _t(
        key="sec_wsh_off",
        name="Disable Windows Script Host",
        description="Blocks .vbs/.js files from running directly — a very common malware delivery route. Breaks some legacy scripts.",
        category="security",
        risk=RISKY,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Microsoft\Windows Script Host\Settings", "Enabled", 0, off_value=1)],
    ),
    _t(
        key="sec_powershell_logging",
        name="Enable PowerShell script block logging",
        description="Records PowerShell activity in the event log so attacks leave traces.",
        category="security",
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging", "EnableScriptBlockLogging", 1, off_value=0)],
    ),
]

# ==========================================================================
# NETWORK
# ==========================================================================
NETWORK_TWEAKS: list[TweakDef] = [
    _t(
        key="net_no_ipv6",
        name="Disable IPv6",
        description="Prefer IPv4 only. Can fix some VPN and DNS issues; may break some corporate networks.",
        category="network",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters", "DisabledComponents", 0xFF, off_value=0)],
        restart="pc",
    ),
    _t(
        key="net_no_nagle",
        name="Disable Nagle's algorithm",
        description="Sends small packets immediately — lower latency for gaming and remote desktop.",
        category="network",
        risk=MODERATE,
        admin=True,
        sets=[
            RegSet(HKLM, r"SOFTWARE\Microsoft\MSMQ\Parameters", "TCPNoDelay", 1, off_value=0),
            RegSet(HKLM, r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "TcpAckFrequency", 1, off_value=2),
        ],
        restart="pc",
    ),
    _t(
        key="net_qos_off",
        name="Remove QoS bandwidth reservation",
        description="Stops Windows reserving up to 20% of bandwidth for QoS-aware traffic.",
        category="network",
        risk=MODERATE,
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\Psched", "NonBestEffortLimit", 0, off_value=20)],
    ),
    _t(
        key="net_no_auto_tuning",
        name="Disable TCP auto-tuning",
        description="Sometimes fixes slow throughput on old routers or exotic VPNs. Try it only if speeds are bad.",
        category="network",
        risk=MODERATE,
        admin=True,
        apply_cmds=[Command(kind="powershell", script="netsh int tcp set global autotuninglevel=disabled", label="netsh int tcp set global autotuninglevel=disabled")],
        revert_cmds=[Command(kind="powershell", script="netsh int tcp set global autotuninglevel=normal", label="netsh int tcp set global autotuninglevel=normal")],
    ),
    _t(
        key="net_no_wifi_sense",
        name="Disable hotspot auto-join",
        description="Stops the device auto-connecting to suggested open hotspots.",
        category="network",
        sets=[RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings\Wi-Fi Sense", "WiFiSenseAllowed", 0, off_value=1)],
    ),
]

# ==========================================================================
# INTERFACE
# ==========================================================================
INTERFACE: list[TweakDef] = [
    _t(
        key="ui_dark_mode",
        name="Dark mode",
        description="Switches apps and system surfaces to the dark theme.",
        category="interface",
        sets=[
            RegSet(HKCU, PERSONALIZE, "AppsUseLightTheme", 0, off_value=1),
            RegSet(HKCU, PERSONALIZE, "SystemUsesLightTheme", 0, off_value=1),
        ],
    ),
    _t(
        key="ui_file_extensions",
        name="Show file extensions",
        description="Reveals the real type of every file instead of hiding it behind a friendly name.",
        category="interface",
        sets=[RegSet(HKCU, EXPLORER_ADV, "HideFileExt", 0, off_value=1)],
        restart="explorer",
    ),
    _t(
        key="ui_hidden_files",
        name="Show hidden & system files",
        description="Makes hidden and protected operating system files visible in Explorer.",
        category="interface",
        sets=[
            RegSet(HKCU, EXPLORER_ADV, "Hidden", 1, off_value=2),
            RegSet(HKCU, EXPLORER_ADV, "ShowSuperHidden", 1, off_value=0),
        ],
        restart="explorer",
    ),
    _t(
        key="ui_this_pc",
        name="Open Explorer at This PC",
        description="File Explorer opens on This PC instead of the Home/Quick access page.",
        category="interface",
        sets=[RegSet(HKCU, EXPLORER_ADV, "LaunchTo", 1, off_value=2)],
    ),
    _t(
        key="ui_taskbar_left",
        name="Align taskbar to the left",
        description="Moves Start and taskbar icons back to the left (Windows 11).",
        category="interface",
        sets=[RegSet(HKCU, EXPLORER_ADV, "TaskbarAl", 0, off_value=1)],
        restart="explorer",
    ),
    _t(
        key="ui_taskbar_small",
        name="Small taskbar buttons",
        description="Uses the compact taskbar and never combines labels.",
        category="interface",
        sets=[
            RegSet(HKCU, EXPLORER_ADV, "TaskbarSmallIcons", 1, off_value=0),
            RegSet(HKCU, EXPLORER_ADV, "TaskbarGlomLevel", 2, off_value=0),
        ],
        restart="explorer",
    ),
    _t(
        key="ui_no_widgets",
        name="Hide Widgets from the taskbar",
        description="Removes the Widgets/News button and its background news feed.",
        category="interface",
        sets=[RegSet(HKCU, EXPLORER_ADV, "TaskbarDa", 0, off_value=1)],
        restart="explorer",
    ),
    _t(
        key="ui_no_chat",
        name="Hide Chat from the taskbar",
        description="Removes the Teams/Chat icon from the taskbar.",
        category="interface",
        sets=[RegSet(HKCU, EXPLORER_ADV, "TaskbarMn", 0, off_value=2)],
        restart="explorer",
    ),
    _t(
        key="ui_no_taskview",
        name="Hide Task View button",
        description="Removes the Task View / virtual desktop button from the taskbar.",
        category="interface",
        sets=[RegSet(HKCU, EXPLORER_ADV, "ShowTaskViewButton", 0, off_value=1)],
        restart="explorer",
    ),
    _t(
        key="ui_classic_context_menu",
        name="Classic right-click menu",
        description="Restores the full Windows 10 context menu without the 'Show more options' step.",
        category="interface",
        risk=MODERATE,
        sets=[RegSet(HKCU, r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32", "", "", off_value="")],
        restart="explorer",
    ),
    _t(
        key="ui_no_recommended",
        name="Hide Recommended in Start",
        description="Removes the Recommended files/apps section from the Start menu.",
        category="interface",
        sets=[
            RegSet(HKCU, EXPLORER_ADV, "Start_IrisRecommendations", 0, off_value=1),
            RegSet(HKCU, EXPLORER_ADV, "Start_AccountNotifications", 0, off_value=1),
        ],
        restart="explorer",
    ),
    _t(
        key="ui_seconds_in_clock",
        name="Show seconds in the clock",
        description="Adds seconds to the taskbar clock. Slightly more CPU wake-ups.",
        category="interface",
        sets=[RegSet(HKCU, EXPLORER_ADV, "ShowSecondsInSystemClock", 1, off_value=0)],
        restart="explorer",
    ),
    _t(
        key="ui_no_ads_explorer",
        name="Turn off Explorer ads & suggestions",
        description="Removes 'sync provider' notifications, OneDrive promos and tips inside File Explorer.",
        category="interface",
        sets=[
            RegSet(HKCU, EXPLORER_ADV, "ShowSyncProviderNotifications", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Explorer\SyncRootManager", "ShowSyncProviderPromotions", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SilentInstalledAppsEnabled", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SystemPaneSuggestionsEnabled", 0, off_value=1),
        ],
        restart="explorer",
    ),
    _t(
        key="ui_no_lock_screen_tips",
        name="Disable lock screen tips & ads",
        description="Stops rotating 'fun facts' and suggestions on the lock screen.",
        category="interface",
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "RotatingLockScreenEnabled", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "RotatingLockScreenOverlayEnabled", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-338387Enabled", 0, off_value=1),
        ],
    ),
]

# ==========================================================================
# GAMING
# ==========================================================================
GAMING: list[TweakDef] = [
    _t(
        key="game_mode_on",
        name="Enable Game Mode",
        description="Prioritises games for CPU/GPU resources and suspends background installs.",
        category="gaming",
        sets=[RegSet(HKCU, r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1, off_value=0)],
    ),
    _t(
        key="game_dvr_off",
        name="Disable Game DVR & background recording",
        description="Stops the shadow recorder that costs 5–10% FPS even when you never record.",
        category="gaming",
        risk=MODERATE,
        admin=True,
        sets=[
            RegSet(HKCU, r"System\GameConfigStore", "GameDVR_Enabled", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0, off_value=1),
            RegSet(HKLM, r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", 0, off_value=1),
        ],
    ),
    _t(
        key="game_bar_off",
        name="Disable Xbox Game Bar overlay",
        description="Turns off the Win+G overlay and its background hooks.",
        category="gaming",
        risk=MODERATE,
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "GameDVR_Enabled", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\GameBar", "ShowStartupPanel", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\GameBar", "UseNexusForGameBarEnabled", 0, off_value=1),
        ],
    ),
    _t(
        key="game_fullscreen_opts_off",
        name="Disable fullscreen optimisations",
        description="Forces true exclusive fullscreen, which some older titles and overlays need.",
        category="gaming",
        risk=MODERATE,
        sets=[RegSet(HKCU, r"System\GameConfigStore", "GameDVR_FSEBehaviorMode", 2, off_value=0)],
    ),
    _t(
        key="game_no_power_throttle",
        name="Disable game power throttling",
        description="Stops Windows capping frame rates to save power on battery.",
        category="gaming",
        admin=True,
        sets=[RegSet(HKLM, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games", "GPU Priority", 8, off_value=0)],
    ),
    _t(
        key="game_no_notifications",
        name="Turn off notifications while gaming",
        description="Suppresses toast notifications and Windows Update prompts during fullscreen apps.",
        category="gaming",
        sets=[
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings", "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0, off_value=1),
            RegSet(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings", "NOC_GLOBAL_SETTING_ALLOW_NOTIFICATION_SOUND", 0, off_value=1),
        ],
    ),
]


ALL_TWEAKS: list[TweakDef] = [
    *PERFORMANCE,
    *POWER_PLANS,
    *PRIVACY,
    *SECURITY,
    *NETWORK_TWEAKS,
    *INTERFACE,
    *GAMING,
]

CATEGORIES: dict[str, list[TweakDef]] = {
    "performance": PERFORMANCE + POWER_PLANS,
    "privacy": PRIVACY,
    "security": SECURITY,
    "network": NETWORK_TWEAKS,
    "interface": INTERFACE,
    "gaming": GAMING,
}


def by_category(category: str) -> list[TweakDef]:
    return list(CATEGORIES.get(category, []))


def by_key(key: str) -> TweakDef | None:
    for t in ALL_TWEAKS:
        if t.key == key:
            return t
    return None


def search(text: str) -> list[TweakDef]:
    needle = text.strip().lower()
    if not needle:
        return []
    return [
        t
        for t in ALL_TWEAKS
        if needle in t.name.lower()
        or needle in t.description.lower()
        or needle in t.key.lower()
        or any(needle in tag for tag in t.tags)
    ]
