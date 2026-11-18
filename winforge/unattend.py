"""Generate autounattend.xml and SetupComplete.cmd from a profile.

Element order follows the autounattend.xml that NTLite wrote for the kiosk builds, which
installed cleanly on the target machine.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

NS = 'xmlns="urn:schemas-microsoft-com:unattend" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"'
ATTR = 'processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS"'


def _cmd(command: str) -> str:
    return f"cmd.exe /c {command}"


def _specialize_commands(p: dict) -> list[str]:
    acct = p["account"]
    cmds: list[str] = []
    if acct["enable_builtin_admin"]:
        full = (acct["display_name"] or acct["name"]).replace('"', "")
        cmds += ["net user Administrator /active:Yes", f'net user Administrator /fullname:"{full}"']
    return cmds + list(p["scripts"]["specialize"])


def build_unattend(p: dict) -> str:
    acct = p["account"]
    region = p["region"]
    name = escape(acct["name"])
    display = escape(acct["display_name"] or acct["name"])
    pw = escape(acct["password"])
    locale = escape(region["locale"])
    input_locale = escape(region["input"])
    lines = ['<?xml version="1.0" encoding="utf-8"?>', f"<unattend {NS}>"]

    specialize = _specialize_commands(p)
    if specialize:
        lines += [
            '  <settings pass="specialize">',
            f'    <component name="Microsoft-Windows-Deployment" {ATTR}>',
            "      <RunSynchronous>",
        ]
        for i, cmd in enumerate(specialize, 1):
            lines.append(
                f'        <RunSynchronousCommand wcm:action="add"><Order>{i}</Order>'
                f"<Path>{escape(_cmd(cmd))}</Path><Description>WinForge specialize {i}</Description>"
                "</RunSynchronousCommand>"
            )
        lines += ["      </RunSynchronous>", "    </component>", "  </settings>"]

    lines += [
        '  <settings pass="oobeSystem">',
        f'    <component name="Microsoft-Windows-International-Core" {ATTR}>',
        f"      <InputLocale>{input_locale}</InputLocale>",
        f"      <SystemLocale>{locale}</SystemLocale>",
        f"      <UserLocale>{locale}</UserLocale>",
        "    </component>",
        f'    <component name="Microsoft-Windows-Shell-Setup" {ATTR}>',
    ]
    if region["timezone"]:
        lines.append(f"      <TimeZone>{escape(region['timezone'])}</TimeZone>")
    if acct["autologon"]:
        lines.append(
            f"      <AutoLogon><Enabled>true</Enabled><Username>{name}</Username>"
            f"<Password><Value>{pw}</Value><PlainText>true</PlainText></Password></AutoLogon>"
        )
    if acct["skip_oobe"]:
        lines += [
            "      <OOBE>",
            "        <HideEULAPage>true</HideEULAPage>",
            "        <HideLocalAccountScreen>true</HideLocalAccountScreen>",
            "        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>",
            "        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>",
            "        <ProtectYourPC>3</ProtectYourPC>",
            "        <SkipMachineOOBE>true</SkipMachineOOBE>",
            "        <SkipUserOOBE>true</SkipUserOOBE>",
            "      </OOBE>",
        ]
    lines += [
        "      <UserAccounts><LocalAccounts>",
        f'        <LocalAccount wcm:action="add"><DisplayName>{display}</DisplayName>'
        f"<Group>Administrators</Group><Name>{name}</Name>"
        f"<Password><Value>{pw}</Value><PlainText>true</PlainText></Password></LocalAccount>",
        "      </LocalAccounts></UserAccounts>",
    ]
    first = p["scripts"]["firstlogon"]
    if first:
        lines.append("      <FirstLogonCommands>")
        for i, cmd in enumerate(first, 1):
            lines.append(
                f'        <SynchronousCommand wcm:action="add"><Order>{i}</Order>'
                f"<CommandLine>{escape(_cmd(cmd))}</CommandLine>"
                f"<Description>WinForge firstlogon {i}</Description>"
                "<RequiresUserInput>false</RequiresUserInput></SynchronousCommand>"
            )
        lines.append("      </FirstLogonCommands>")
    lines += ["    </component>", "  </settings>"]

    # Setup questions. The image is exported with only the chosen edition, so it is always index 1.
    lines += [
        '  <settings pass="windowsPE">',
        f'    <component name="Microsoft-Windows-International-Core-WinPE" {ATTR}>',
        f"      <InputLocale>{input_locale}</InputLocale>",
        f"      <SystemLocale>{locale}</SystemLocale>",
        f"      <UserLocale>{locale}</UserLocale>",
        "    </component>",
        f'    <component name="Microsoft-Windows-Setup" {ATTR}>',
        "      <Diagnostics><OptIn>false</OptIn></Diagnostics>",
        "      <DynamicUpdate><Enable>false</Enable><WillShowUI>OnError</WillShowUI></DynamicUpdate>",
        "      <ImageInstall><OSImage><WillShowUI>OnError</WillShowUI><InstallFrom>"
        '<MetaData wcm:action="add"><Key>/IMAGE/INDEX</Key><Value>1</Value></MetaData>'
        "</InstallFrom></OSImage></ImageInstall>",
        "      <UserData><AcceptEula>true</AcceptEula><ProductKey><Key></Key></ProductKey></UserData>",
        "    </component>",
        "  </settings>",
    ]
    lines.append("</unattend>")
    return "\n".join(lines) + "\n"


def build_setupcomplete(p: dict) -> str | None:
    cmds = p["scripts"]["setupcomplete"]
    if not cmds:
        return None
    lines = [
        "@echo off",
        "REM Generated by WinForge. Runs as SYSTEM after setup, before first logon.",
        *cmds,
    ]
    return "\r\n".join(lines) + "\r\n"
