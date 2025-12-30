; Pytron NSIS Installer Script (polished)
; - Expects BUILD_DIR to be defined when invoking makensis
; - Uses assets found in the same directory as this script

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinMessages.nsh"

; ---------------------
; ---------------------
; Configurable values
; ---------------------
!ifndef NAME
  !define NAME "Pytron"
!endif
!ifndef VERSION
  !define VERSION "1.0"
!endif
!ifndef COMPANY
  !define COMPANY "Pytron User"
!endif
!ifndef DESCRIPTION
  !define DESCRIPTION "${NAME} Installer"
!endif
!ifndef COPYRIGHT
  !define COPYRIGHT "Copyright © 2025 ${COMPANY}"
!endif
!ifndef BUILD_DIR
  !error "BUILD_DIR must be defined"
!endif
!ifndef MAIN_EXE_NAME
  !define MAIN_EXE_NAME "Pytron.exe"
!endif
!ifndef OUT_DIR
  !define OUT_DIR "$EXEDIR"
!endif

Name "${NAME}"
OutFile "${OUT_DIR}\${NAME}_Installer_${VERSION}.exe"
InstallDir "$PROGRAMFILES\\${NAME}"
InstallDirRegKey HKLM "Software\\${NAME}" "Install_Dir"
RequestExecutionLevel admin

; Version Info for the Installer EXE
VIProductVersion "${VERSION}.0.0"
VIAddVersionKey "ProductName" "${NAME}"
VIAddVersionKey "CompanyName" "${COMPANY}"
VIAddVersionKey "LegalCopyright" "${COPYRIGHT}"
VIAddVersionKey "FileDescription" "${DESCRIPTION}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"

; Use ZLIB compression for better AV compatibility (LZMA often flagged)
SetCompressor /SOLID zlib
; SetCompressorDictSize 32 ; Not applicable for zlib usually, or default is fine

; Welcome/Finish Page Image (Left side)
!define MUI_WELCOMEFINISHPAGE_BITMAP "sidebar.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "sidebar.bmp"

; Finish Page options
!define MUI_FINISHPAGE_RUN "$INSTDIR\${MAIN_EXE_NAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Run ${NAME}"
!define MUI_FINISHPAGE_LINK "Built with Pytron"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/Ghua8088/pytron"

; ---------------------
; Detect Existing Install
; ---------------------
Var IS_UPDATE

Function .onInit
    ReadRegStr $R0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "UninstallString"
    ${If} $R0 != ""
        StrCpy $IS_UPDATE "1"
    ${Else}
        StrCpy $IS_UPDATE "0"
    ${EndIf}
FunctionEnd

; ---------------------
; Pages
; ---------------------
!define MUI_PAGE_CUSTOMFUNCTION_SHOW WelcomeShow
!insertmacro MUI_PAGE_WELCOME

Function WelcomeShow
    ${If} $IS_UPDATE == "1"
        ; MUI2 Welcome/Finish pages are special child dialogs (#32770)
        FindWindow $1 "#32770" "" $HWNDPARENT
        ; 1000 is the title control, 1001 is the text control
        GetDlgItem $0 $1 1000
        SendMessage $0 ${WM_SETTEXT} 0 "STR:Welcome to the ${NAME} Update/Repair Wizard"
        GetDlgItem $0 $1 1001
        SendMessage $0 ${WM_SETTEXT} 0 "STR:This wizard will guide you through updating or fixing your existing installation of ${NAME}.$\r$\n$\r$\nClick Next to continue."
    ${EndIf}
FunctionEnd

; !insertmacro MUI_PAGE_LICENSE "${BUILD_DIR}\\LICENSE.txt" ; Uncomment if you have a license
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_PAGE_CUSTOMFUNCTION_SHOW FinishShow
!insertmacro MUI_PAGE_FINISH

Function FinishShow
    ${If} $IS_UPDATE == "1"
        FindWindow $1 "#32770" "" $HWNDPARENT
        GetDlgItem $0 $1 1000
        SendMessage $0 ${WM_SETTEXT} 0 "STR:Update/Repair Complete"
    ${EndIf}
FunctionEnd

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; ---------------------
; Installation section
; ---------------------
Section "Install"
    ; Ensure the install directory exists and copy all built files
    SetOutPath "$INSTDIR"
    SetOverwrite on
    File /r "${BUILD_DIR}\*.*"

    ; Write useful uninstall registry entries
    WriteRegStr HKLM "Software\${NAME}" "Install_Dir" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "DisplayName" "${NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "Publisher" "${COMPANY}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "UninstallString" "$INSTDIR\\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "DisplayIcon" "$INSTDIR\${MAIN_EXE_NAME}"

    WriteUninstaller "$INSTDIR\\uninstall.exe"

    ; Shortcuts
    CreateDirectory "$SMPROGRAMS\${NAME}"
    CreateShortCut "$SMPROGRAMS\${NAME}\${NAME}.lnk" "$INSTDIR\${MAIN_EXE_NAME}" "" "$INSTDIR\${MAIN_EXE_NAME}" 0
    CreateShortCut "$DESKTOP\${NAME}.lnk" "$INSTDIR\${MAIN_EXE_NAME}" "" "$INSTDIR\${MAIN_EXE_NAME}" 0
SectionEnd

; ---------------------
; Uninstaller
; ---------------------
Section "Uninstall"
    ; Avoid locking the installation directory
    SetOutPath "$TEMP"

    ; Remove shortcuts first
    Delete "$DESKTOP\${NAME}.lnk"
    Delete "$SMPROGRAMS\${NAME}\${NAME}.lnk"
    RMDir "$SMPROGRAMS\${NAME}"

    ; Remove files and install directory
    RMDir /r "$INSTDIR"

    ; Clean up registry
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}"
    DeleteRegKey HKLM "Software\\${NAME}"
SectionEnd

; EOF