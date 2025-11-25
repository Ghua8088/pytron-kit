; Pytron NSIS Installer Script (polished)
; - Expects BUILD_DIR to be defined when invoking makensis
; - Optionally provide a `pytron.ico` in the build dir for installer icons

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

Name "${NAME} ${VERSION}"
OutFile "${OUT_DIR}\${NAME}_Installer_${VERSION}.exe"
InstallDir "$PROGRAMFILES\\${NAME}"
InstallDirRegKey HKLM "Software\\${NAME}" "Install_Dir"
RequestExecutionLevel admin

; Use LZMA compression for smaller installers
SetCompressor lzma
SetCompressorDictSize 32

; Optional icons (provide `pytron.ico` in BUILD_DIR to enable)
!define MUI_ICON "${BUILD_DIR}\pytron.ico"
!define MUI_UNICON "${BUILD_DIR}\pytron.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${BUILD_DIR}\\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

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

    WriteUninstaller "$INSTDIR\\uninstall.exe"

    ; Shortcuts
    CreateDirectory "$SMPROGRAMS\${NAME}"
    CreateShortCut "$SMPROGRAMS\${NAME}\${NAME}.lnk" "$INSTDIR\${MAIN_EXE_NAME}" "" "$INSTDIR\${MAIN_EXE_NAME}"
    CreateShortCut "$DESKTOP\${NAME}.lnk" "$INSTDIR\${MAIN_EXE_NAME}"
SectionEnd

; ---------------------
; Uninstaller
; ---------------------
Section "Uninstall"
    ; Remove shortcuts first
    Delete "$DESKTOP\${NAME}.lnk"
    Delete "$SMPROGRAMS\${NAME}\${NAME}.lnk"

    ; Remove files and install directory
    RMDir /r "$INSTDIR"

    ; Clean up registry
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${NAME}"
SectionEnd

; EOF