"""One-shot repair, network, maintenance and security tasks.

These are the "fix it now" buttons: they run a scripted sequence, stream the
output to the log console and report success/failure per step.
"""

from __future__ import annotations

from ..core.model import MODERATE, RISKY, ActionDef, Command


def ps(script: str, label: str, timeout: int = 900) -> Command:
    return Command(kind="powershell", script=script, label=label, timeout=timeout)


# ==========================================================================
# REPAIR
# ==========================================================================
REPAIR: list[ActionDef] = [
    ActionDef(
        key="repair_sfc",
        name="System File Checker",
        description="Scans all protected system files and replaces corrupt ones with cached copies.",
        group="repair",
        admin=True,
        eta=420,
        steps=[ps("sfc /scannow", "sfc /scannow", timeout=1800)],
        note="Safe to run any time. Do not close the window while it is verifying.",
    ),
    ActionDef(
        key="repair_dism_scan",
        name="Check component store health",
        description="DISM ScanHealth — reports whether the Windows image is repairable.",
        group="repair",
        admin=True,
        eta=300,
        steps=[ps("DISM /Online /Cleanup-Image /ScanHealth", "DISM /Online /Cleanup-Image /ScanHealth", timeout=1800)],
    ),
    ActionDef(
        key="repair_dism_restore",
        name="Repair the Windows image (DISM)",
        description="DISM RestoreHealth — downloads clean components from Windows Update and repairs the image. Run this before SFC if SFC reports errors it cannot fix.",
        group="repair",
        admin=True,
        eta=1200,
        steps=[
            ps(
                "DISM /Online /Cleanup-Image /RestoreHealth /Source:WU",
                "DISM /Online /Cleanup-Image /RestoreHealth",
                timeout=3600,
            )
        ],
        note="Needs an internet connection. Can take 10–20 minutes.",
    ),
    ActionDef(
        key="repair_full_stack",
        name="Full repair: DISM → SFC → reboot check",
        description="The complete cure for a misbehaving Windows: repair the image, then verify system files.",
        group="repair",
        admin=True,
        eta=1800,
        steps=[
            ps("DISM /Online /Cleanup-Image /ScanHealth", "DISM ScanHealth", timeout=1800),
            ps("DISM /Online /Cleanup-Image /RestoreHealth /Source:WU", "DISM RestoreHealth", timeout=3600),
            ps("sfc /scannow", "sfc /scannow", timeout=1800),
        ],
    ),
    ActionDef(
        key="repair_component_cleanup",
        name="Clean the component store",
        description="DISM StartComponentCleanup — removes superseded versions of components (WinSxS bloat).",
        group="repair",
        admin=True,
        eta=600,
        steps=[ps("DISM /Online /Cleanup-Image /StartComponentCleanup", "DISM StartComponentCleanup", timeout=1800)],
    ),
    ActionDef(
        key="repair_reset_base",
        name="Aggressive WinSxS cleanup (ResetBase)",
        description="Removes every superseded component. Saves the most space but you can no longer uninstall installed updates.",
        group="repair",
        admin=True,
        risk=RISKY,
        eta=900,
        steps=[ps("DISM /Online /Cleanup-Image /StartComponentCleanup /ResetBase", "DISM StartComponentCleanup /ResetBase", timeout=2400)],
        note="Point of no return for update uninstallation.",
    ),
    ActionDef(
        key="repair_chkdsk_scan",
        name="Scan the system disk",
        description="Online chkdsk scan — reports file system errors without taking the volume offline.",
        group="repair",
        admin=True,
        eta=300,
        steps=[ps("chkdsk C: /scan", "chkdsk C: /scan", timeout=1800)],
    ),
    ActionDef(
        key="repair_chkdsk_fix",
        name="Schedule a full disk repair",
        description="chkdsk /F /R on the next reboot — finds bad sectors and recovers readable data.",
        group="repair",
        admin=True,
        risk=RISKY,
        eta=60,
        steps=[ps("echo N | chkdsk C: /F /R", "chkdsk C: /F /R (scheduled at next boot)", timeout=600)],
        note="Your PC will take a long time to start next boot. Do not power off during the check.",
    ),
    ActionDef(
        key="repair_wu_reset",
        name="Reset Windows Update",
        description="Stops the update services, clears SoftwareDistribution and Catroot2, then restarts them. Fixes stuck/failed updates.",
        group="repair",
        admin=True,
        risk=MODERATE,
        eta=240,
        steps=[
            ps(
                "$s=@('wuauserv','bits','cryptsvc','msiserver','usosvc'); "
                "foreach($x in $s){ Stop-Service -Name $x -Force -ErrorAction SilentlyContinue }; "
                "Rename-Item -Path $env:SystemRoot\\SoftwareDistribution -NewName SoftwareDistribution.old -ErrorAction SilentlyContinue; "
                "Rename-Item -Path $env:SystemRoot\\System32\\catroot2 -NewName catroot2.old -ErrorAction SilentlyContinue; "
                "foreach($x in $s){ Start-Service -Name $x -ErrorAction SilentlyContinue }; "
                "'Windows Update components reset'",
                "reset Windows Update components",
                timeout=900,
            )
        ],
        note="Update history will be cleared and updates re-detected on the next scan.",
    ),
    ActionDef(
        key="repair_store_reset",
        name="Reset the Microsoft Store cache",
        description="Runs wsreset.exe to clear the Store cache — fixes Store apps failing to install or update.",
        group="repair",
        eta=120,
        steps=[ps("Start-Process wsreset.exe -Wait", "wsreset.exe", timeout=600)],
    ),
    ActionDef(
        key="repair_reregister_apps",
        name="Re-register all built-in apps",
        description="Re-registers every AppX package. Fixes Start menu, Calculator, Photos, Settings and Store failures.",
        group="repair",
        admin=True,
        risk=MODERATE,
        eta=600,
        steps=[
            ps(
                "Get-AppxPackage -AllUsers | ForEach-Object { "
                "Add-AppxPackage -DisableDevelopmentMode -Register "
                "\"$($_.InstallLocation)\\AppXManifest.xml\" -ErrorAction SilentlyContinue }; "
                "'Re-registration complete'",
                "re-register AppX packages",
                timeout=1800,
            )
        ],
    ),
    ActionDef(
        key="repair_icon_cache",
        name="Rebuild icon & thumbnail cache",
        description="Clears Explorer's icon and thumbnail databases and restarts the shell. Fixes wrong/blank icons.",
        group="repair",
        eta=90,
        steps=[
            ps(
                "$ErrorActionPreference='SilentlyContinue'; "
                "Stop-Process -Name explorer -Force; "
                "Remove-Item \"$env:LOCALAPPDATA\\Microsoft\\Windows\\Explorer\\iconcache_*\" -Force; "
                "Remove-Item \"$env:LOCALAPPDATA\\Microsoft\\Windows\\Explorer\\thumbcache_*\" -Force; "
                "Start-Sleep -Seconds 2; Start-Process explorer; "
                "'Icon cache rebuilt'",
                "rebuild icon + thumbnail cache",
                timeout=600,
            )
        ],
    ),
    ActionDef(
        key="repair_search_index",
        name="Rebuild the search index",
        description="Deletes and re-creates the Windows Search index. Fixes empty or slow Start search.",
        group="repair",
        admin=True,
        risk=MODERATE,
        eta=600,
        steps=[
            ps(
                "Stop-Service WSearch -Force -ErrorAction SilentlyContinue; "
                "Remove-Item \"$env:ProgramData\\Microsoft\\Search\\Data\\Applications\\Windows\\Windows.edb\" -Force -ErrorAction SilentlyContinue; "
                "Start-Service WSearch -ErrorAction SilentlyContinue; "
                "'Search index will rebuild in the background'",
                "rebuild search index",
                timeout=900,
            )
        ],
    ),
    ActionDef(
        key="repair_time_sync",
        name="Fix the system clock",
        description="Restarts the time service and forces a resync. Fixes certificate/login errors caused by clock drift.",
        group="repair",
        admin=True,
        eta=90,
        steps=[
            ps("net stop w32time; net start w32time; w32tm /resync /force", "w32tm /resync /force", timeout=600)
        ],
    ),
    ActionDef(
        key="repair_hosts_reset",
        name="Restore the default hosts file",
        description="Replaces C:\\Windows\\System32\\drivers\\etc\\hosts with the Windows default.",
        group="repair",
        admin=True,
        risk=MODERATE,
        eta=60,
        steps=[
            ps(
                "$h = \"$env:SystemRoot\\System32\\drivers\\etc\\hosts\"; "
                "Copy-Item $h \"$h.winx.bak\" -Force -ErrorAction SilentlyContinue; "
                "Set-Content -Path $h -Value '# WinX: default hosts file', '# 127.0.0.1 localhost', '# ::1 localhost' -Force -ErrorAction Stop; "
                "'hosts file reset (backup saved as hosts.winx.bak)'",
                "reset hosts file",
                timeout=300,
            )
        ],
        note="A backup is kept next to the original as hosts.winx.bak.",
    ),
    ActionDef(
        key="repair_gpu_driver_clean",
        name="Clean-reinstall graphics driver (DDU-style prep)",
        description="Stops graphics services and removes the NVIDIA/AMD/Intel driver packages from the driver store so you can install a clean one.",
        group="repair",
        admin=True,
        risk=RISKY,
        eta=600,
        steps=[
            ps(
                "pnputil /enum-drivers | Select-String -Pattern 'oem\\d+\\.inf' -Context 6,0 | "
                "Out-String | Write-Output; "
                "'Review the list above, then use Driver Store Explorer or pnputil /delete-driver <oemXX.inf> /uninstall /force'",
                "list driver store packages",
                timeout=600,
            )
        ],
        note="Listing only — deleting the wrong driver can leave you without a display. Use the Drivers page to back up first.",
    ),
    ActionDef(
        key="repair_health_report",
        name="Generate a system health report",
        description="Runs powercfg /energy and perfmon /report, then opens the resulting HTML reports.",
        group="repair",
        admin=True,
        eta=180,
        steps=[
            ps("powercfg /energy /output \"$env:USERPROFILE\\Desktop\\winx-energy-report.html\" /duration 60", "powercfg /energy (60s)", timeout=600),
            ps("perfmon /report", "perfmon /report", timeout=900),
        ],
    ),
]

# ==========================================================================
# NETWORK
# ==========================================================================
NETWORK_ACTIONS: list[ActionDef] = [
    ActionDef(
        key="net_flush_dns",
        name="Flush DNS cache",
        description="Clears cached DNS lookups. Fixes 'site won't load after the server moved' problems.",
        group="network",
        eta=15,
        steps=[ps("ipconfig /flushdns", "ipconfig /flushdns", timeout=300)],
    ),
    ActionDef(
        key="net_renew_ip",
        name="Release & renew IP address",
        description="Drops the DHCP lease and asks for a new one. Fixes IP conflicts and dead connections.",
        group="network",
        eta=60,
        steps=[
            ps("ipconfig /release", "ipconfig /release", timeout=300),
            ps("ipconfig /renew", "ipconfig /renew", timeout=600),
        ],
    ),
    ActionDef(
        key="net_winsock_reset",
        name="Reset Winsock catalog",
        description="Rebuilds the Winsock catalogue. Fixes broken sockets caused by VPN clients, firewalls and malware.",
        group="network",
        admin=True,
        risk=MODERATE,
        eta=60,
        steps=[ps("netsh winsock reset", "netsh winsock reset", timeout=600)],
        note="Restart the PC afterwards.",
    ),
    ActionDef(
        key="net_tcpip_reset",
        name="Reset TCP/IP stack",
        description="Rewrites the TCP/IP registry keys back to defaults. Fixes 'no internet' with a connected adapter.",
        group="network",
        admin=True,
        risk=MODERATE,
        eta=60,
        steps=[ps("netsh int ip reset", "netsh int ip reset", timeout=600)],
        note="Restart the PC afterwards.",
    ),
    ActionDef(
        key="net_full_reset",
        name="Full network reset",
        description="The nuclear option: Winsock + TCP/IP + firewall + DNS + proxy, all back to defaults.",
        group="network",
        admin=True,
        risk=RISKY,
        eta=180,
        steps=[
            ps("netsh winsock reset", "netsh winsock reset", timeout=600),
            ps("netsh int ip reset", "netsh int ip reset", timeout=600),
            ps("ipconfig /release", "ipconfig /release", timeout=300),
            ps("ipconfig /renew", "ipconfig /renew", timeout=600),
            ps("ipconfig /flushdns", "ipconfig /flushdns", timeout=300),
            ps("netsh advfirewall reset", "netsh advfirewall reset", timeout=600),
            ps("netsh winhttp reset proxy", "netsh winhttp reset proxy", timeout=300),
        ],
        note="You will lose Wi-Fi profiles? No — but you will need to re-enter VPN and proxy settings. Restart afterwards.",
    ),
    ActionDef(
        key="net_reset_proxy",
        name="Clear proxy settings",
        description="Removes system and WinHTTP proxy configuration that can silently block all browsing.",
        group="network",
        admin=True,
        eta=45,
        steps=[
            ps("netsh winhttp reset proxy", "netsh winhttp reset proxy", timeout=300),
            ps(
                "Set-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' "
                "-Name ProxyEnable -Value 0 -ErrorAction SilentlyContinue; "
                "Set-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' "
                "-Name ProxyServer -Value '' -ErrorAction SilentlyContinue; "
                "'proxy cleared'",
                "clear Internet Options proxy",
                timeout=300,
            ),
        ],
    ),
    ActionDef(
        key="net_firewall_reset",
        name="Reset Windows Firewall",
        description="Restores all firewall rules to their defaults. Fixes 'no internet' caused by an over-zealous rule set.",
        group="network",
        admin=True,
        risk=MODERATE,
        eta=60,
        steps=[ps("netsh advfirewall reset", "netsh advfirewall reset", timeout=600)],
        note="Third-party firewall rules you added will be removed.",
    ),
    ActionDef(
        key="net_dns_cloudflare",
        name="Use Cloudflare DNS (1.1.1.1)",
        description="Sets 1.1.1.1 / 1.0.0.1 on every active adapter. Fast and privacy-focused.",
        group="network",
        admin=True,
        eta=45,
        steps=[
            ps(
                "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | "
                "ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex "
                "-ServerAddresses ('1.1.1.1','1.0.0.1') -ErrorAction SilentlyContinue }; 'DNS set to Cloudflare'",
                "Set-DnsClientServerAddress → 1.1.1.1, 1.0.0.1",
                timeout=300,
            ),
            ps("ipconfig /flushdns", "ipconfig /flushdns", timeout=300),
        ],
    ),
    ActionDef(
        key="net_dns_google",
        name="Use Google DNS (8.8.8.8)",
        description="Sets 8.8.8.8 / 8.8.4.4 on every active adapter.",
        group="network",
        admin=True,
        eta=45,
        steps=[
            ps(
                "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | "
                "ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex "
                "-ServerAddresses ('8.8.8.8','8.8.4.4') -ErrorAction SilentlyContinue }; 'DNS set to Google'",
                "Set-DnsClientServerAddress → 8.8.8.8, 8.8.4.4",
                timeout=300,
            ),
            ps("ipconfig /flushdns", "ipconfig /flushdns", timeout=300),
        ],
    ),
    ActionDef(
        key="net_dns_adguard",
        name="Use AdGuard DNS (ad blocking)",
        description="Sets 94.140.14.14 / 94.140.15.15 — blocks ads and trackers at the DNS level for the whole PC.",
        group="network",
        admin=True,
        eta=45,
        steps=[
            ps(
                "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | "
                "ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex "
                "-ServerAddresses ('94.140.14.14','94.140.15.15') -ErrorAction SilentlyContinue }; 'DNS set to AdGuard'",
                "Set-DnsClientServerAddress → 94.140.14.14, 94.140.15.15",
                timeout=300,
            ),
            ps("ipconfig /flushdns", "ipconfig /flushdns", timeout=300),
        ],
    ),
    ActionDef(
        key="net_dns_dhcp",
        name="Automatic DNS (DHCP)",
        description="Hands DNS back to your router — the normal, default behaviour.",
        group="network",
        admin=True,
        eta=45,
        steps=[
            ps(
                "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | "
                "ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex "
                "-ResetServerAddresses -ErrorAction SilentlyContinue }; 'DNS set to automatic'",
                "Set-DnsClientServerAddress -ResetServerAddresses",
                timeout=300,
            ),
            ps("ipconfig /flushdns", "ipconfig /flushdns", timeout=300),
        ],
    ),
    ActionDef(
        key="net_arp_clear",
        name="Clear the ARP cache",
        description="Forgets cached MAC-to-IP mappings. Useful after replacing a router.",
        group="network",
        admin=True,
        eta=30,
        steps=[ps("netsh interface ip delete arpcache", "netsh interface ip delete arpcache", timeout=300)],
    ),
    ActionDef(
        key="net_adapter_restart",
        name="Restart network adapters",
        description="Disables and re-enables every physical adapter — the quickest cure for a stuck connection.",
        group="network",
        admin=True,
        risk=MODERATE,
        eta=90,
        steps=[
            ps(
                "Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object { "
                "Restart-NetAdapter -Name $_.Name -Confirm:$false -ErrorAction SilentlyContinue }; "
                "'adapters restarted'",
                "Restart-NetAdapter (all physical adapters)",
                timeout=600,
            )
        ],
        note="You will be offline for a few seconds.",
    ),
]

# ==========================================================================
# SECURITY / DEFENDER
# ==========================================================================
SECURITY_ACTIONS: list[ActionDef] = [
    ActionDef(
        key="sec_defender_quick",
        name="Quick virus scan",
        description="Runs a Microsoft Defender quick scan of the usual malware haunts.",
        group="security",
        admin=True,
        eta=300,
        steps=[
            ps(
                "$p = \"$env:ProgramFiles\\Windows Defender\\MpCmdRun.exe\"; "
                "if (Test-Path $p) { & $p -Scan -ScanType 1 } else { Start-MpScan -ScanType QuickScan }",
                "Defender quick scan",
                timeout=1800,
            )
        ],
    ),
    ActionDef(
        key="sec_defender_full",
        name="Full virus scan",
        description="Scans every file on every drive. Slow but thorough — leave it running in the background.",
        group="security",
        admin=True,
        eta=3600,
        steps=[
            ps(
                "$p = \"$env:ProgramFiles\\Windows Defender\\MpCmdRun.exe\"; "
                "if (Test-Path $p) { & $p -Scan -ScanType 2 } else { Start-MpScan -ScanType FullScan }",
                "Defender full scan",
                timeout=7200,
            )
        ],
    ),
    ActionDef(
        key="sec_defender_update",
        name="Update virus definitions",
        description="Forces a signature update so scans know about the latest threats.",
        group="security",
        admin=True,
        eta=120,
        steps=[
            ps(
                "$p = \"$env:ProgramFiles\\Windows Defender\\MpCmdRun.exe\"; "
                "if (Test-Path $p) { & $p -SignatureUpdate } else { Update-MpSignature }",
                "Defender signature update",
                timeout=900,
            )
        ],
    ),
    ActionDef(
        key="sec_firewall_on",
        name="Turn the firewall on",
        description="Enables the Windows Firewall for domain, private and public profiles.",
        group="security",
        admin=True,
        eta=30,
        steps=[ps("netsh advfirewall set allprofiles state on", "netsh advfirewall set allprofiles state on", timeout=300)],
    ),
    ActionDef(
        key="sec_defender_offline",
        name="Schedule an offline scan",
        description="Runs Defender outside Windows at the next boot, where rootkits cannot hide.",
        group="security",
        admin=True,
        risk=MODERATE,
        eta=60,
        steps=[ps("Start-MpWDOScan -ErrorAction SilentlyContinue; 'offline scan scheduled'", "Start-MpWDOScan", timeout=600)],
        note="Your PC will restart and scan before loading Windows.",
    ),
    ActionDef(
        key="sec_activation",
        name="Check Windows activation",
        description="Runs slmgr /xpr to show whether Windows is permanently activated.",
        group="security",
        eta=30,
        steps=[ps("slmgr /xpr", "slmgr /xpr", timeout=300)],
    ),
    ActionDef(
        key="sec_bitlocker",
        name="BitLocker status",
        description="Shows the encryption state of every volume.",
        group="security",
        admin=True,
        eta=30,
        steps=[ps("manage-bde -status", "manage-bde -status", timeout=300)],
    ),
    ActionDef(
        key="sec_update_status",
        name="Windows Update status",
        description="Shows the last successful update scan and install dates.",
        group="security",
        eta=60,
        steps=[
            ps(
                "$s = New-Object -ComObject Microsoft.Update.Session; "
                "$i = $s.CreateUpdateSearcher().Search('IsInstalled=1').Updates; "
                "if ($i.Count) { $last = ($i | Sort-Object LastDeploymentChangeTime -Descending | Select-Object -First 1); "
                "\"Last installed update: $($last.LastDeploymentChangeTime) — $($last.Title)\" } else { 'No update history' }",
                "query Windows Update history",
                timeout=600,
            )
        ],
    ),
]

# ==========================================================================
# MAINTENANCE / TOOLS
# ==========================================================================
MAINTENANCE: list[ActionDef] = [
    ActionDef(
        key="maint_optimize_drives",
        name="Optimise & defragment drives",
        description="Runs the correct optimisation for each drive: TRIM for SSDs, defrag for HDDs.",
        group="maintenance",
        admin=True,
        eta=900,
        steps=[
            ps(
                "Get-Volume | Where-Object { $_.DriveLetter } | ForEach-Object { "
                "$m = (Get-PhysicalDisk | Where-Object { $_.DeviceID -eq (Get-Partition -DriveLetter $_.DriveLetter).DiskNumber }).MediaType; "
                "if ($m -eq 'SSD') { Optimize-Volume -DriveLetter $_.DriveLetter -ReTrim -Verbose } "
                "else { Optimize-Volume -DriveLetter $_.DriveLetter -Defrag -Verbose } }; 'drives optimised'",
                "Optimize-Volume (TRIM / defrag)",
                timeout=3600,
            )
        ],
    ),
    ActionDef(
        key="maint_disk_cleanup",
        name="Run Windows Disk Cleanup",
        description="Opens cleanmgr with every category pre-selected — hands-off deep cleaning.",
        group="maintenance",
        admin=True,
        eta=600,
        steps=[
            ps(
                "$k='HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VolumeCaches\\'; "
                "Get-ChildItem $k | ForEach-Object { Set-ItemProperty -Path $_.PSPath -Name StateFlags0001 -Value 2 -Type DWord }; "
                "Start-Process cleanmgr -ArgumentList '/sagerun:1' -Wait; 'disk cleanup finished'",
                "cleanmgr /sagerun:1",
                timeout=3600,
            )
        ],
    ),
    ActionDef(
        key="maint_restart_explorer",
        name="Restart File Explorer",
        description="Restarts explorer.exe without a reboot — applies shell tweaks and frees stuck handles.",
        group="maintenance",
        eta=20,
        steps=[
            ps(
                "Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue; Start-Sleep 1; "
                "if (-not (Get-Process explorer -ErrorAction SilentlyContinue)) { Start-Process explorer }; 'explorer restarted'",
                "restart explorer.exe",
                timeout=300,
            )
        ],
    ),
    ActionDef(
        key="maint_energy_report",
        name="Battery / energy report",
        description="Generates a battery health and power-efficiency report on your desktop.",
        group="maintenance",
        admin=True,
        eta=120,
        steps=[ps("powercfg /batteryreport /output \"$env:USERPROFILE\\Desktop\\winx-battery-report.html\"; powercfg /batteryreport /output \"$env:USERPROFILE\\Desktop\\winx-battery-report.html\" /duration 14", "powercfg /batteryreport", timeout=600)],
    ),
    ActionDef(
        key="maint_sleep_study",
        name="Sleep study report",
        description="Shows what has been keeping your PC awake (drains battery overnight).",
        group="maintenance",
        admin=True,
        eta=120,
        steps=[ps("powercfg /sleepstudy /output \"$env:USERPROFILE\\Desktop\\winx-sleepstudy.html\"", "powercfg /sleepstudy", timeout=600)],
    ),
]

#: quick launchers for classic Windows applets
TOOLS: list[ActionDef] = [
    ActionDef(key="tool_services", name="Services", description="services.msc — manage every Windows service.", group="tools", eta=5,
              steps=[ps("Start-Process services.msc", "services.msc", timeout=60)]),
    ActionDef(key="tool_devmgmt", name="Device Manager", description="devmgmt.msc — drivers and hardware.", group="tools", eta=5,
              steps=[ps("Start-Process devmgmt.msc", "devmgmt.msc", timeout=60)]),
    ActionDef(key="tool_diskmgmt", name="Disk Management", description="diskmgmt.msc — partitions and volumes.", group="tools", eta=5,
              steps=[ps("Start-Process diskmgmt.msc", "diskmgmt.msc", timeout=60)]),
    ActionDef(key="tool_msconfig", name="System Configuration", description="msconfig — boot options and selective startup.", group="tools", eta=5,
              steps=[ps("Start-Process msconfig", "msconfig", timeout=60)]),
    ActionDef(key="tool_taskschd", name="Task Scheduler", description="taskschd.msc — scheduled tasks.", group="tools", eta=5,
              steps=[ps("Start-Process taskschd.msc", "taskschd.msc", timeout=60)]),
    ActionDef(key="tool_eventvwr", name="Event Viewer", description="eventvwr.msc — system and application logs.", group="tools", eta=5,
              steps=[ps("Start-Process eventvwr.msc", "eventvwr.msc", timeout=60)]),
    ActionDef(key="tool_msinfo32", name="System Information", description="msinfo32 — full hardware and software inventory.", group="tools", eta=10,
              steps=[ps("Start-Process msinfo32", "msinfo32", timeout=120)]),
    ActionDef(key="tool_resmon", name="Resource Monitor", description="resmon — live CPU, disk, network and memory detail.", group="tools", eta=10,
              steps=[ps("Start-Process resmon", "resmon", timeout=120)]),
    ActionDef(key="tool_optionalfeatures", name="Windows Features", description="optionalfeatures — turn Windows components on or off.", group="tools", eta=10,
              steps=[ps("Start-Process optionalfeatures", "optionalfeatures", timeout=120)]),
    ActionDef(key="tool_rstrui", name="System Restore", description="rstrui — roll the system back to a restore point.", group="tools", eta=10,
              steps=[ps("Start-Process rstrui", "rstrui", timeout=120)]),
    ActionDef(key="tool_dxdiag", name="DirectX diagnostics", description="dxdiag — display, sound and input diagnostics.", group="tools", eta=15,
              steps=[ps("Start-Process dxdiag", "dxdiag", timeout=180)]),
    ActionDef(key="tool_sysdm", name="Advanced system properties", description="sysdm.cpl — environment variables, performance options, profiles.", group="tools", eta=10,
              steps=[ps("Start-Process sysdm.cpl", "sysdm.cpl", timeout=120)]),
    ActionDef(key="tool_appwiz", name="Programs and Features", description="appwiz.cpl — the classic uninstall dialog.", group="tools", eta=10,
              steps=[ps("Start-Process appwiz.cpl", "appwiz.cpl", timeout=120)]),
    ActionDef(key="tool_firewall_cpl", name="Windows Firewall", description="firewall.cpl — firewall and advanced security.", group="tools", eta=10,
              steps=[ps("Start-Process firewall.cpl", "firewall.cpl", timeout=120)]),
    ActionDef(key="tool_ncpa", name="Network Connections", description="ncpa.cpl — adapters, IP settings and Wi-Fi.", group="tools", eta=10,
              steps=[ps("Start-Process ncpa.cpl", "ncpa.cpl", timeout=120)]),
    ActionDef(key="tool_powercfg_cpl", name="Power options", description="powercfg.cpl — plan settings and sleep timers.", group="tools", eta=10,
              steps=[ps("Start-Process powercfg.cpl", "powercfg.cpl", timeout=120)]),
]


ALL_ACTIONS: list[ActionDef] = [*REPAIR, *NETWORK_ACTIONS, *SECURITY_ACTIONS, *MAINTENANCE, *TOOLS]

ACTION_GROUPS: dict[str, list[ActionDef]] = {
    "repair": REPAIR,
    "network": NETWORK_ACTIONS,
    "security": SECURITY_ACTIONS,
    "maintenance": MAINTENANCE,
    "tools": TOOLS,
}


def by_group(group: str) -> list[ActionDef]:
    return list(ACTION_GROUPS.get(group, []))


def action_by_key(key: str) -> ActionDef | None:
    for a in ALL_ACTIONS:
        if a.key == key:
            return a
    return None
