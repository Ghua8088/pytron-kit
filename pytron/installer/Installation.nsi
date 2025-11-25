; Pytron NSIS Installer Script (polished)
; - Expects BUILD_DIR to be defined when invoking makensis
; - Uses assets found in the same directory as this script

!include "MUI2.nsh"

; ---------------------
; Configurable values
; ---------------------
!ifndef NAME
  !define NAME "Pytron"
!endif
!ifndef VERSION
  !define VERSION "1.0"
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

; Use LZMA compression for smaller installers
SetCompressor lzma
SetCompressorDictSize 32

; Welcome/Finish Page Image (Left side)
!define MUI_WELCOMEFINISHPAGE_BITMAP "sidebar.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "sidebar.bmp"

; Finish Page options
!define MUI_FINISHPAGE_RUN "$INSTDIR\${MAIN_EXE_NAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Run ${NAME}"
!define MUI_FINISHPAGE_LINK "Built with Pytron"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/Ghua8088/pytron"

; ---------------------
; Pages
; ---------------------
!insertmacro MUI_PAGE_WELCOME
; !insertmacro MUI_PAGE_LICENSE "${BUILD_DIR}\\LICENSE.txt" ; Uncomment if you have a license
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

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
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "DisplayName" "${NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}" "Publisher" "Pytron"
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