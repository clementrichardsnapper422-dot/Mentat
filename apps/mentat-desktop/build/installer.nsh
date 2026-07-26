!macro customInstall
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\resources\mentat-installer\install-runtime.ps1" -PayloadRoot "$INSTDIR\resources\mentat-runtime"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Mentat runtime installation failed with exit code $0."
    Abort
  ${EndIf}
!macroend

!macro customUnInstall
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\resources\mentat-installer\install-runtime.ps1" -Uninstall'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Mentat runtime cleanup failed with exit code $0. Your configuration and local state were preserved."
  ${EndIf}
!macroend
